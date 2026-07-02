from __future__ import annotations

import re


class SqlGuardError(ValueError):
    """Raised when a SQL statement is outside the read-only policy."""


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
START_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE | re.DOTALL)
DANGEROUS_TOKEN_PATTERN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|UPSERT|CREATE|ALTER|DROP|TRUNCATE|RENAME|"
    r"GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|LOCK|ANALYZE|EXPLAIN|"
    r"CALL|EXEC|EXECUTE|BEGIN|DECLARE|"
    r"DBMS_[A-Z0-9_]+|UTL_[A-Z0-9_]+"
    r")\b",
    re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    statement = sql.strip()
    if not statement:
        raise SqlGuardError("SQL is empty.")
    if "\x00" in statement:
        raise SqlGuardError("SQL contains a null byte.")

    normalized = strip_comments_and_literals(statement).strip()
    if not START_PATTERN.match(normalized):
        raise SqlGuardError("Only SELECT or WITH queries are allowed.")

    without_optional_trailing_semicolon = normalized[:-1] if normalized.endswith(";") else normalized
    if ";" in without_optional_trailing_semicolon:
        raise SqlGuardError("Multiple SQL statements are not allowed.")

    upper = collapse_whitespace(without_optional_trailing_semicolon).upper()
    if re.search(r"\bWITH\s+(FUNCTION|PROCEDURE)\b", upper):
        raise SqlGuardError("WITH FUNCTION/PROCEDURE is not allowed.")
    if re.search(r"\bFOR\s+UPDATE\b", upper):
        raise SqlGuardError("SELECT FOR UPDATE is not allowed.")

    match = DANGEROUS_TOKEN_PATTERN.search(upper)
    if match:
        raise SqlGuardError(f"Keyword or package is not allowed: {match.group(1)}.")

    return statement[:-1].strip() if statement.endswith(";") else statement


def validate_identifier(value: str, field_name: str = "identifier") -> str:
    identifier = value.strip()
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise SqlGuardError(
            f"Invalid {field_name}: {value!r}. "
            "Use an unquoted Oracle identifier: letters, numbers, _, $, #."
        )
    return identifier.upper()


def split_table_name(table_name: str, owner: str | None = None) -> tuple[str | None, str]:
    raw = table_name.strip()
    if "." in raw:
        if owner:
            raise SqlGuardError("Pass either owner or owner.table_name, not both.")
        parts = raw.split(".")
        if len(parts) != 2:
            raise SqlGuardError("Table name must be table_name or owner.table_name.")
        return (
            validate_identifier(parts[0], "owner"),
            validate_identifier(parts[1], "table_name"),
        )

    normalized_owner = validate_identifier(owner, "owner") if owner else None
    return normalized_owner, validate_identifier(raw, "table_name")


def qualified_name(owner: str | None, table_name: str) -> str:
    normalized_table = validate_identifier(table_name, "table_name")
    if not owner:
        return normalized_table
    return f"{validate_identifier(owner, 'owner')}.{normalized_table}"


def clamp_limit(value: int | None, default: int, maximum: int) -> int:
    if value is None:
        return default
    if value < 1:
        raise SqlGuardError("Limit must be greater than 0.")
    return min(value, maximum)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_comments_and_literals(sql: str) -> str:
    result: list[str] = []
    i = 0
    length = len(sql)
    while i < length:
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < length else ""

        if char == "-" and next_char == "-":
            result.append(" ")
            i += 2
            while i < length and sql[i] not in "\r\n":
                i += 1
            continue

        if char == "/" and next_char == "*":
            result.append(" ")
            i += 2
            while i + 1 < length and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = min(i + 2, length)
            continue

        if char in ("'", '"'):
            quote = char
            result.append(" ")
            i += 1
            while i < length:
                if sql[i] == quote:
                    if quote == "'" and i + 1 < length and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        result.append(char)
        i += 1

    return "".join(result)
