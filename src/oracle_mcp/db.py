from __future__ import annotations

import base64
import datetime as dt
import decimal
import time
from contextlib import contextmanager
from threading import Lock
from typing import Any, Iterator

import oracledb

from .config import AppConfig, DbProfile
from .sql_guard import (
    SqlGuardError,
    clamp_limit,
    qualified_name,
    split_table_name,
    validate_identifier,
    validate_readonly_sql,
)


class ProfileNotFoundError(KeyError):
    """Raised when a requested DB profile is not configured."""


MAX_CELL_CHARS = 4_000
MAX_BINARY_BYTES = 256
SOURCE_TYPES = {
    "FUNCTION",
    "PACKAGE",
    "PACKAGE BODY",
    "PROCEDURE",
    "TRIGGER",
    "TYPE",
    "TYPE BODY",
}
_oracle_client_lock = Lock()
_oracle_client_initialized = False


def get_profile(config: AppConfig, profile_name: str) -> DbProfile:
    try:
        return config.profiles[profile_name]
    except KeyError as exc:
        raise ProfileNotFoundError(f"Unknown profile: {profile_name}") from exc


def profile_summary(config: AppConfig) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for name, profile in sorted(config.profiles.items()):
        summaries.append(
            {
                "name": name,
                "description": profile.description,
                "dsn": profile.dsn,
                "default_owner": profile.default_owner,
                "max_rows": profile.effective_max_rows(config.defaults),
                "query_timeout_seconds": profile.effective_timeout_seconds(
                    config.defaults
                ),
                "sample_rows": profile.effective_sample_rows(config.defaults),
                "thick_mode": profile.thick_mode,
            }
        )
    return summaries


@contextmanager
def connect(config: AppConfig, profile_name: str) -> Iterator[oracledb.Connection]:
    profile = get_profile(config, profile_name)
    maybe_init_oracle_client(profile)

    connect_kwargs: dict[str, Any] = {
        "user": profile.user,
        "password": profile.password,
        "dsn": profile.dsn,
    }
    if profile.config_dir:
        connect_kwargs["config_dir"] = profile.config_dir
    if profile.wallet_location:
        connect_kwargs["wallet_location"] = profile.wallet_location
    if profile.wallet_password:
        connect_kwargs["wallet_password"] = profile.wallet_password

    connection = oracledb.connect(**connect_kwargs)
    connection.call_timeout = profile.effective_timeout_seconds(config.defaults) * 1000
    try:
        yield connection
    finally:
        connection.close()


def maybe_init_oracle_client(profile: DbProfile) -> None:
    global _oracle_client_initialized
    if not profile.thick_mode:
        return

    with _oracle_client_lock:
        if _oracle_client_initialized:
            return
        init_kwargs: dict[str, Any] = {}
        if profile.config_dir:
            init_kwargs["config_dir"] = profile.config_dir
        oracledb.init_oracle_client(**init_kwargs)
        _oracle_client_initialized = True


def test_connection(config: AppConfig, profile_name: str) -> dict[str, Any]:
    result = execute_query(
        config=config,
        profile_name=profile_name,
        sql="SELECT 1 AS ok FROM dual",
        binds={},
        limit=1,
        validate_sql=False,
    )
    return {
        "profile": profile_name,
        "ok": bool(result["rows"] and result["rows"][0].get("ok") == 1),
        "elapsed_ms": result["elapsed_ms"],
        "thin_mode": oracledb.is_thin_mode(),
    }


def list_tables(
    config: AppConfig,
    profile_name: str,
    owner: str | None = None,
    name_like: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    effective_owner = owner or profile.default_owner
    normalized_owner = effective_owner.upper() if effective_owner else None
    pattern = normalize_like_pattern(name_like)
    max_rows = profile.effective_max_rows(config.defaults)
    effective_limit = clamp_limit(limit, default=min(200, max_rows), maximum=max_rows)

    sql = """
        SELECT owner, object_name AS table_name, object_type
        FROM (
            SELECT owner, object_name, object_type
            FROM all_objects
            WHERE object_type IN ('TABLE', 'VIEW')
              AND (:owner IS NULL OR owner = :owner)
              AND (:name_like IS NULL OR object_name LIKE :name_like)
            ORDER BY owner, object_type, object_name
        )
        WHERE ROWNUM <= :limit
    """
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={
            "owner": normalized_owner,
            "name_like": pattern,
            "limit": effective_limit,
        },
        limit=effective_limit,
        validate_sql=False,
    )


def list_views(
    config: AppConfig,
    profile_name: str,
    owner: str | None = None,
    name_like: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    effective_owner = owner or profile.default_owner
    normalized_owner = normalize_owner(effective_owner)
    pattern = normalize_like_pattern(name_like)
    max_rows = profile.effective_max_rows(config.defaults)
    effective_limit = clamp_limit(limit, default=min(200, max_rows), maximum=max_rows)

    sql = """
        SELECT owner, object_name AS view_name, object_type, status, created, last_ddl_time
        FROM (
            SELECT owner, object_name, object_type, status, created, last_ddl_time
            FROM all_objects
            WHERE object_type = 'VIEW'
              AND (:owner IS NULL OR owner = :owner)
              AND (:name_like IS NULL OR object_name LIKE :name_like)
            ORDER BY owner, object_name
        )
        WHERE ROWNUM <= :limit
    """
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={
            "owner": normalized_owner,
            "name_like": pattern,
            "limit": effective_limit,
        },
        limit=effective_limit,
        validate_sql=False,
    )


def describe_table(
    config: AppConfig,
    profile_name: str,
    table_name: str,
    owner: str | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    parsed_owner, parsed_table = split_table_name(table_name, owner)
    effective_owner = parsed_owner or profile.default_owner
    normalized_owner = effective_owner.upper() if effective_owner else None

    column_sql = """
        SELECT
            c.owner,
            c.table_name,
            c.column_id,
            c.column_name,
            c.data_type,
            c.data_length,
            c.data_precision,
            c.data_scale,
            c.nullable,
            cc.comments
        FROM all_tab_columns c
        LEFT JOIN all_col_comments cc
          ON cc.owner = c.owner
         AND cc.table_name = c.table_name
         AND cc.column_name = c.column_name
        WHERE c.table_name = :table_name
          AND (:owner IS NULL OR c.owner = :owner)
        ORDER BY c.owner, c.table_name, c.column_id
    """
    columns = execute_query(
        config=config,
        profile_name=profile_name,
        sql=column_sql,
        binds={"owner": normalized_owner, "table_name": parsed_table},
        limit=1_000,
        validate_sql=False,
    )

    pk_sql = """
        SELECT acc.owner, acc.table_name, acc.column_name, acc.position
        FROM all_constraints ac
        JOIN all_cons_columns acc
          ON acc.owner = ac.owner
         AND acc.constraint_name = ac.constraint_name
        WHERE ac.constraint_type = 'P'
          AND acc.table_name = :table_name
          AND (:owner IS NULL OR acc.owner = :owner)
        ORDER BY acc.owner, acc.table_name, acc.position
    """
    primary_keys = execute_query(
        config=config,
        profile_name=profile_name,
        sql=pk_sql,
        binds={"owner": normalized_owner, "table_name": parsed_table},
        limit=100,
        validate_sql=False,
    )

    return {
        "profile": profile_name,
        "owner_filter": normalized_owner,
        "table_name": parsed_table,
        "columns": columns["rows"],
        "primary_keys": primary_keys["rows"],
        "elapsed_ms": columns["elapsed_ms"] + primary_keys["elapsed_ms"],
    }


def get_view_definition(
    config: AppConfig,
    profile_name: str,
    view_name: str,
    owner: str | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    parsed_owner, parsed_view = split_table_name(view_name, owner)
    effective_owner = parsed_owner or profile.default_owner
    normalized_owner = normalize_owner(effective_owner)

    sql = """
        SELECT owner, view_name, text AS view_sql
        FROM all_views
        WHERE view_name = :view_name
          AND (:owner IS NULL OR owner = :owner)
        ORDER BY owner, view_name
    """
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={"owner": normalized_owner, "view_name": parsed_view},
        limit=20,
        validate_sql=False,
    )


def sample_rows(
    config: AppConfig,
    profile_name: str,
    table_name: str,
    owner: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    parsed_owner, parsed_table = split_table_name(table_name, owner)
    effective_owner = parsed_owner or profile.default_owner
    max_rows = profile.effective_max_rows(config.defaults)
    default_limit = min(profile.effective_sample_rows(config.defaults), max_rows)
    effective_limit = clamp_limit(limit, default=default_limit, maximum=max_rows)
    table_ref = qualified_name(effective_owner, parsed_table)
    sql = f"SELECT * FROM {table_ref} WHERE ROWNUM <= :limit"
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={"limit": effective_limit},
        limit=effective_limit,
        validate_sql=False,
    )


def list_procedures(
    config: AppConfig,
    profile_name: str,
    owner: str | None = None,
    name_like: str | None = None,
    include_package_members: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    effective_owner = owner or profile.default_owner
    normalized_owner = normalize_owner(effective_owner)
    pattern = normalize_like_pattern(name_like)
    max_rows = profile.effective_max_rows(config.defaults)
    effective_limit = clamp_limit(limit, default=min(200, max_rows), maximum=max_rows)

    sql = """
        SELECT
            owner,
            object_name,
            procedure_name,
            COALESCE(procedure_name, object_name) AS routine_name,
            object_type,
            overload,
            aggregate,
            pipelined
        FROM (
            SELECT
                owner,
                object_name,
                procedure_name,
                object_type,
                overload,
                aggregate,
                pipelined
            FROM all_procedures
            WHERE object_type IN ('PROCEDURE', 'FUNCTION', 'PACKAGE')
              AND (:owner IS NULL OR owner = :owner)
              AND (
                    :name_like IS NULL
                 OR object_name LIKE :name_like
                 OR procedure_name LIKE :name_like
              )
              AND (:include_members = 1 OR procedure_name IS NULL)
            ORDER BY owner, object_type, object_name, procedure_name, overload
        )
        WHERE ROWNUM <= :limit
    """
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={
            "owner": normalized_owner,
            "name_like": pattern,
            "include_members": 1 if include_package_members else 0,
            "limit": effective_limit,
        },
        limit=effective_limit,
        validate_sql=False,
    )


def describe_procedure(
    config: AppConfig,
    profile_name: str,
    procedure_name: str,
    owner: str | None = None,
    package_name: str | None = None,
) -> dict[str, Any]:
    resolved_owner, resolved_package, resolved_routine = parse_routine_reference(
        procedure_name=procedure_name,
        owner=owner,
        package_name=package_name,
        default_owner=get_profile(config, profile_name).default_owner,
    )

    metadata_sql = """
        SELECT
            owner,
            object_name,
            procedure_name,
            COALESCE(procedure_name, object_name) AS routine_name,
            object_type,
            overload,
            aggregate,
            pipelined
        FROM all_procedures
        WHERE (:owner IS NULL OR owner = :owner)
          AND (
                (:package_name IS NULL AND object_name = :routine_name AND procedure_name IS NULL)
             OR (:package_name IS NOT NULL AND object_name = :package_name AND procedure_name = :routine_name)
          )
        ORDER BY owner, object_type, object_name, procedure_name, overload
    """
    metadata = execute_query(
        config=config,
        profile_name=profile_name,
        sql=metadata_sql,
        binds={
            "owner": resolved_owner,
            "package_name": resolved_package,
            "routine_name": resolved_routine,
        },
        limit=100,
        validate_sql=False,
    )

    arguments_sql = """
        SELECT
            owner,
            package_name,
            object_name,
            overload,
            argument_name,
            position,
            sequence,
            data_level,
            in_out,
            data_type,
            data_length,
            data_precision,
            data_scale,
            type_owner,
            type_name,
            type_subname,
            defaulted
        FROM all_arguments
        WHERE (:owner IS NULL OR owner = :owner)
          AND (
                (:package_name IS NULL AND package_name IS NULL AND object_name = :routine_name)
             OR (:package_name IS NOT NULL AND package_name = :package_name AND object_name = :routine_name)
          )
        ORDER BY owner, package_name, object_name, overload, sequence
    """
    arguments = execute_query(
        config=config,
        profile_name=profile_name,
        sql=arguments_sql,
        binds={
            "owner": resolved_owner,
            "package_name": resolved_package,
            "routine_name": resolved_routine,
        },
        limit=1_000,
        validate_sql=False,
    )

    return {
        "profile": profile_name,
        "owner_filter": resolved_owner,
        "package_name": resolved_package,
        "routine_name": resolved_routine,
        "metadata": metadata["rows"],
        "arguments": arguments["rows"],
        "elapsed_ms": metadata["elapsed_ms"] + arguments["elapsed_ms"],
    }


def get_object_source(
    config: AppConfig,
    profile_name: str,
    object_name: str,
    owner: str | None = None,
    object_type: str | None = None,
    limit_lines: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    parsed_owner, parsed_object = split_table_name(object_name, owner)
    effective_owner = parsed_owner or profile.default_owner
    normalized_owner = normalize_owner(effective_owner)
    normalized_type = normalize_source_type(object_type)
    effective_limit = clamp_limit(
        limit_lines,
        default=min(500, profile.effective_max_rows(config.defaults)),
        maximum=profile.effective_max_rows(config.defaults),
    )

    sql = """
        SELECT owner, name, type, line, text
        FROM (
            SELECT owner, name, type, line, text
            FROM all_source
            WHERE name = :object_name
              AND (:owner IS NULL OR owner = :owner)
              AND (:object_type IS NULL OR type = :object_type)
            ORDER BY owner, type, name, line
        )
        WHERE ROWNUM <= :limit
    """
    row_result = execute_query(
        config=config,
        profile_name=profile_name,
        sql=sql,
        binds={
            "owner": normalized_owner,
            "object_name": parsed_object,
            "object_type": normalized_type,
            "limit": effective_limit + 1,
        },
        limit=effective_limit + 1,
        validate_sql=False,
    )

    sources: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in row_result["rows"][:effective_limit]:
        key = (row["owner"], row["type"], row["name"])
        sources.setdefault(key, []).append(row)

    return {
        "profile": profile_name,
        "owner_filter": normalized_owner,
        "object_name": parsed_object,
        "object_type": normalized_type,
        "sources": [
            {
                "owner": key[0],
                "type": key[1],
                "name": key[2],
                "line_count": len(lines),
                "source": "".join(str(line["text"]) for line in lines),
            }
            for key, lines in sources.items()
        ],
        "truncated": row_result["row_count"] > effective_limit,
        "limit_lines": effective_limit,
        "elapsed_ms": row_result["elapsed_ms"],
    }


def run_select_query(
    config: AppConfig,
    profile_name: str,
    sql: str,
    max_rows: int | None = None,
) -> dict[str, Any]:
    profile = get_profile(config, profile_name)
    effective_limit = clamp_limit(
        max_rows,
        default=profile.effective_max_rows(config.defaults),
        maximum=profile.effective_max_rows(config.defaults),
    )
    safe_sql = validate_readonly_sql(sql)
    return execute_query(
        config=config,
        profile_name=profile_name,
        sql=safe_sql,
        binds={},
        limit=effective_limit,
        validate_sql=False,
    )


def execute_query(
    config: AppConfig,
    profile_name: str,
    sql: str,
    binds: dict[str, Any] | None,
    limit: int,
    validate_sql: bool,
) -> dict[str, Any]:
    safe_sql = validate_readonly_sql(sql) if validate_sql else sql
    start = time.perf_counter()
    with connect(config, profile_name) as connection:
        with connection.cursor() as cursor:
            cursor.arraysize = min(max(limit, 1), 1_000)
            cursor.prefetchrows = min(max(limit, 1), 1_000)
            cursor.execute(safe_sql, binds or {})
            rows = cursor.fetchmany(limit + 1)
            columns = unique_column_names(cursor.description or [])

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    truncated = len(rows) > limit
    visible_rows = rows[:limit]
    return {
        "profile": profile_name,
        "columns": columns,
        "rows": [serialize_row(columns, row) for row in visible_rows],
        "row_count": len(visible_rows),
        "truncated": truncated,
        "limit": limit,
        "elapsed_ms": elapsed_ms,
    }


def unique_column_names(description: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    names: list[str] = []
    for column in description:
        raw_name = getattr(column, "name", None) or column[0]
        base_name = str(raw_name).lower()
        count = seen.get(base_name, 0) + 1
        seen[base_name] = count
        names.append(base_name if count == 1 else f"{base_name}_{count}")
    return names


def serialize_row(columns: list[str], row: Any) -> dict[str, Any]:
    return {
        column_name: serialize_value(value)
        for column_name, value in zip(columns, row, strict=False)
    }


def serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return truncate_string(value) if isinstance(value, str) else value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
            "base64_prefix": base64.b64encode(value[:MAX_BINARY_BYTES]).decode("ascii"),
            "truncated": len(value) > MAX_BINARY_BYTES,
        }
    if hasattr(value, "read"):
        return serialize_value(value.read())
    return truncate_string(str(value))


def truncate_string(value: str) -> str | dict[str, Any]:
    if len(value) <= MAX_CELL_CHARS:
        return value
    return {
        "type": "text",
        "value": value[:MAX_CELL_CHARS],
        "truncated": True,
        "original_length": len(value),
    }


def normalize_like_pattern(name_like: str | None) -> str | None:
    if not name_like:
        return None
    pattern = name_like.strip().upper()
    if "%" in pattern or "_" in pattern:
        return pattern
    return f"%{pattern}%"


def normalize_owner(owner: str | None) -> str | None:
    return validate_identifier(owner, "owner") if owner else None


def normalize_source_type(object_type: str | None) -> str | None:
    if object_type is None:
        return None
    normalized = object_type.strip().upper()
    if normalized not in SOURCE_TYPES:
        raise SqlGuardError(
            "Invalid object_type. Use one of: " + ", ".join(sorted(SOURCE_TYPES))
        )
    return normalized


def parse_routine_reference(
    procedure_name: str,
    owner: str | None = None,
    package_name: str | None = None,
    default_owner: str | None = None,
) -> tuple[str | None, str | None, str]:
    parts = [part.strip() for part in procedure_name.split(".") if part.strip()]
    if not parts or len(parts) > 3:
        raise SqlGuardError(
            "Procedure name must be procedure, package.procedure, "
            "or owner.package.procedure."
        )

    resolved_owner = owner or default_owner
    resolved_package = package_name
    resolved_routine: str

    if len(parts) == 1:
        resolved_routine = parts[0]
    elif len(parts) == 2:
        if package_name:
            raise SqlGuardError(
                "Pass either package.procedure or package_name, not both."
            )
        resolved_package, resolved_routine = parts
    else:
        if owner or package_name:
            raise SqlGuardError(
                "Pass either owner.package.procedure or separate owner/package_name, not both."
            )
        resolved_owner, resolved_package, resolved_routine = parts

    return (
        validate_identifier(resolved_owner, "owner") if resolved_owner else None,
        validate_identifier(resolved_package, "package_name")
        if resolved_package
        else None,
        validate_identifier(resolved_routine, "procedure_name"),
    )
