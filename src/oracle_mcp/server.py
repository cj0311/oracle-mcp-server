from __future__ import annotations

import argparse
import ipaddress
import logging
import sys
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from .config import ConfigError, load_config
from .db import (
    describe_table as db_describe_table,
    describe_procedure as db_describe_procedure,
    get_object_source as db_get_object_source,
    get_view_definition as db_get_view_definition,
    list_tables as db_list_tables,
    list_procedures as db_list_procedures,
    list_views as db_list_views,
    profile_summary,
    run_select_query as db_run_select_query,
    sample_rows as db_sample_rows,
    test_connection as db_test_connection,
)


logger = logging.getLogger(__name__)


def build_server(
    config_path: str | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    log_level: str = "INFO",
) -> FastMCP:
    config = load_config(config_path)
    mcp = FastMCP(
        "Oracle DB MCP Server",
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
        json_response=True,
        log_level=log_level,  # type: ignore[arg-type]
    )

    @mcp.tool()
    def list_profiles() -> dict[str, Any]:
        """List configured Oracle DB profiles without exposing credentials."""
        return ok(
            profiles=profile_summary(config),
            defaults=config.defaults.model_dump(),
        )

    @mcp.tool()
    def test_connection(profile_name: str) -> dict[str, Any]:
        """Verify that a configured Oracle DB profile can connect."""
        return safe_tool(lambda: db_test_connection(config, profile_name))

    @mcp.tool()
    def list_tables(
        profile_name: str,
        owner: str | None = None,
        name_like: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List accessible Oracle tables and views for a profile.

        Args:
            profile_name: Configured DB profile name.
            owner: Optional schema owner. Defaults to the profile default_owner.
            name_like: Optional table name pattern. Plain text becomes %TEXT%.
            limit: Optional result limit capped by the profile max_rows.
        """
        return safe_tool(
            lambda: db_list_tables(
                config=config,
                profile_name=profile_name,
                owner=owner,
                name_like=name_like,
                limit=limit,
            )
        )

    @mcp.tool()
    def list_views(
        profile_name: str,
        owner: str | None = None,
        name_like: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List accessible Oracle views for a profile.

        Args:
            profile_name: Configured DB profile name.
            owner: Optional schema owner. Defaults to the profile default_owner.
            name_like: Optional view name pattern. Plain text becomes %TEXT%.
            limit: Optional result limit capped by the profile max_rows.
        """
        return safe_tool(
            lambda: db_list_views(
                config=config,
                profile_name=profile_name,
                owner=owner,
                name_like=name_like,
                limit=limit,
            )
        )

    @mcp.tool()
    def describe_table(
        profile_name: str,
        table_name: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Describe columns and primary keys for an Oracle table or view.

        Args:
            profile_name: Configured DB profile name.
            table_name: Table name, or owner.table_name.
            owner: Optional schema owner if table_name is not owner-qualified.
        """
        return safe_tool(
            lambda: db_describe_table(
                config=config,
                profile_name=profile_name,
                table_name=table_name,
                owner=owner,
            )
        )

    @mcp.tool()
    def describe_view(
        profile_name: str,
        view_name: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Describe columns for an Oracle view.

        Args:
            profile_name: Configured DB profile name.
            view_name: View name, or owner.view_name.
            owner: Optional schema owner if view_name is not owner-qualified.
        """
        return safe_tool(
            lambda: db_describe_table(
                config=config,
                profile_name=profile_name,
                table_name=view_name,
                owner=owner,
            )
        )

    @mcp.tool()
    def get_view_definition(
        profile_name: str,
        view_name: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Fetch the SQL text for an Oracle view from ALL_VIEWS.

        Args:
            profile_name: Configured DB profile name.
            view_name: View name, or owner.view_name.
            owner: Optional schema owner if view_name is not owner-qualified.
        """
        return safe_tool(
            lambda: db_get_view_definition(
                config=config,
                profile_name=profile_name,
                view_name=view_name,
                owner=owner,
            )
        )

    @mcp.tool()
    def sample_rows(
        profile_name: str,
        table_name: str,
        owner: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Fetch sample rows from a table or view using a capped row limit.

        Args:
            profile_name: Configured DB profile name.
            table_name: Table name, or owner.table_name.
            owner: Optional schema owner if table_name is not owner-qualified.
            limit: Optional sample size capped by the profile max_rows.
        """
        return safe_tool(
            lambda: db_sample_rows(
                config=config,
                profile_name=profile_name,
                table_name=table_name,
                owner=owner,
                limit=limit,
            )
        )

    @mcp.tool()
    def list_procedures(
        profile_name: str,
        owner: str | None = None,
        name_like: str | None = None,
        include_package_members: bool = True,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List accessible Oracle procedures, functions, packages, and package members.

        Args:
            profile_name: Configured DB profile name.
            owner: Optional schema owner. Defaults to the profile default_owner.
            name_like: Optional routine/package name pattern. Plain text becomes %TEXT%.
            include_package_members: Include package procedures/functions when true.
            limit: Optional result limit capped by the profile max_rows.
        """
        return safe_tool(
            lambda: db_list_procedures(
                config=config,
                profile_name=profile_name,
                owner=owner,
                name_like=name_like,
                include_package_members=include_package_members,
                limit=limit,
            )
        )

    @mcp.tool()
    def describe_procedure(
        profile_name: str,
        procedure_name: str,
        owner: str | None = None,
        package_name: str | None = None,
    ) -> dict[str, Any]:
        """Describe an Oracle procedure/function signature from ALL_ARGUMENTS.

        Args:
            profile_name: Configured DB profile name.
            procedure_name: Procedure/function name. Use package.procedure for package members.
            owner: Optional schema owner. Defaults to the profile default_owner.
            package_name: Optional package name if procedure_name is only the member name.
        """
        return safe_tool(
            lambda: db_describe_procedure(
                config=config,
                profile_name=profile_name,
                procedure_name=procedure_name,
                owner=owner,
                package_name=package_name,
            )
        )

    @mcp.tool()
    def get_object_source(
        profile_name: str,
        object_name: str,
        owner: str | None = None,
        object_type: str | None = None,
        limit_lines: int | None = None,
    ) -> dict[str, Any]:
        """Fetch PL/SQL source text from ALL_SOURCE.

        This is for source-bearing objects such as PROCEDURE, FUNCTION, PACKAGE,
        PACKAGE BODY, TRIGGER, TYPE, and TYPE BODY. Use get_view_definition for views.

        Args:
            profile_name: Configured DB profile name.
            object_name: Object name, or owner.object_name.
            owner: Optional schema owner if object_name is not owner-qualified.
            object_type: Optional source type, such as PROCEDURE or PACKAGE BODY.
            limit_lines: Optional source line cap, limited by the profile max_rows.
        """
        return safe_tool(
            lambda: db_get_object_source(
                config=config,
                profile_name=profile_name,
                object_name=object_name,
                owner=owner,
                object_type=object_type,
                limit_lines=limit_lines,
            )
        )

    @mcp.tool()
    def run_select_query(
        profile_name: str,
        sql: str,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Run a read-only SELECT/WITH query and return JSON-friendly rows.

        The server rejects DML/DDL, PL/SQL blocks, multiple statements, and
        SELECT FOR UPDATE. Use read-only DB accounts in addition to this guard.

        Args:
            profile_name: Configured DB profile name.
            sql: SELECT or WITH SQL statement.
            max_rows: Optional result cap, limited by the profile max_rows.
        """
        return safe_tool(
            lambda: db_run_select_query(
                config=config,
                profile_name=profile_name,
                sql=sql,
                max_rows=max_rows,
            )
        )

    return mcp


def safe_tool(callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = callback()
        if "ok" not in result:
            result = {"ok": True, **result}
        return result
    except Exception as exc:  # MCP tools should return readable failures.
        logger.exception("Tool failed")
        return {
            "ok": False,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }


def ok(**values: Any) -> dict[str, Any]:
    return {"ok": True, **values}


class IpAllowListMiddleware:
    """ASGI middleware that rejects HTTP requests from non-allowed client IPs."""

    def __init__(self, app: Any, allowed_ips: list[str]) -> None:
        self.app = app
        self.allowed_networks = compile_ip_allow_list(allowed_ips)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else None
        if not client_host or not is_ip_allowed(client_host, self.allowed_networks):
            logger.warning(
                "Rejected MCP HTTP request from %s", client_host or "unknown"
            )
            body = b"Forbidden"
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)


def compile_ip_allow_list(
    allowed_ips: list[str],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in allowed_ips:
        for part in value.split(","):
            spec = part.strip()
            if not spec:
                continue
            networks.append(ipaddress.ip_network(spec, strict=False))
    return tuple(networks)


def is_ip_allowed(
    client_host: str,
    allowed_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    if not allowed_networks:
        return True

    try:
        address = ipaddress.ip_address(client_host)
    except ValueError:
        return False

    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [address]
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        candidates.append(address.ipv4_mapped)

    return any(
        candidate in network
        for candidate in candidates
        for network in allowed_networks
    )


def normalize_http_path(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        raise ValueError("HTTP path must not be empty.")
    if any(char.isspace() for char in normalized):
        raise ValueError("HTTP path must not contain whitespace.")
    if "?" in normalized or "#" in normalized:
        raise ValueError("HTTP path must not contain query strings or fragments.")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized


def run_streamable_http_server(mcp: FastMCP, allowed_ips: list[str]) -> None:
    if not allowed_ips:
        logger.warning(
            "MCP HTTP server is running without --allow-ip. "
            "Restrict access with a host firewall or pass --allow-ip."
        )
        mcp.run(transport="streamable-http")
        return

    import uvicorn

    app = mcp.streamable_http_app()
    app.add_middleware(IpAllowListMiddleware, allowed_ips=allowed_ips)
    uvicorn.run(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Oracle DB MCP server for AI agents."
    )
    parser.add_argument(
        "--config",
        help="Path to profiles.yaml. Defaults to ORACLE_MCP_CONFIG or profiles.yaml.",
    )
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http"],
        help="MCP transport. Use stdio for local agent integration.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host/IP to bind for streamable-http. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        default=8000,
        type=int,
        help="Port to bind for streamable-http. Defaults to 8000.",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="HTTP path for streamable-http. Defaults to /mcp.",
    )
    parser.add_argument(
        "--allow-ip",
        dest="allowed_ips",
        action="append",
        default=[],
        help=(
            "Allowed client IP or CIDR for streamable-http. "
            "Repeat or comma-separate values. If omitted, all client IPs are allowed."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    try:
        args.path = normalize_http_path(args.path)
        compile_ip_allow_list(args.allowed_ips)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        mcp = build_server(
            args.config,
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
            log_level=args.log_level,
        )
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(2) from exc

    if args.transport == "streamable-http":
        run_streamable_http_server(mcp, args.allowed_ips)
        return

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
