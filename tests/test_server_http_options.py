import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oracle_mcp.server import (  # noqa: E402
    compile_ip_allow_list,
    is_ip_allowed,
    parse_args,
)


class ServerHttpOptionsTest(unittest.TestCase):
    def test_parse_streamable_http_options(self) -> None:
        args = parse_args(
            [
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
                "--port",
                "9000",
                "--path",
                "oracle-mcp",
                "--allow-ip",
                "10.0.0.10",
                "--allow-ip",
                "192.168.10.0/24,127.0.0.1",
            ]
        )

        self.assertEqual(args.transport, "streamable-http")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.path, "/oracle-mcp")
        self.assertEqual(
            args.allowed_ips,
            ["10.0.0.10", "192.168.10.0/24,127.0.0.1"],
        )

    def test_ip_allow_list_supports_exact_cidr_and_ipv4_mapped_ipv6(self) -> None:
        networks = compile_ip_allow_list(["10.0.0.10", "192.168.10.0/24"])

        self.assertTrue(is_ip_allowed("10.0.0.10", networks))
        self.assertTrue(is_ip_allowed("192.168.10.55", networks))
        self.assertTrue(is_ip_allowed("::ffff:10.0.0.10", networks))
        self.assertFalse(is_ip_allowed("10.0.0.11", networks))

    def test_invalid_allow_ip_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(
                    ["--transport", "streamable-http", "--allow-ip", "not-an-ip"]
                )

    def test_invalid_port_is_rejected(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args(["--transport", "streamable-http", "--port", "70000"])


if __name__ == "__main__":
    unittest.main()
