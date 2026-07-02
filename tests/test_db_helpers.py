import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oracle_mcp.db import normalize_source_type, parse_routine_reference  # noqa: E402
from oracle_mcp.sql_guard import SqlGuardError  # noqa: E402


class DbHelperTests(unittest.TestCase):
    def test_parse_standalone_procedure_with_default_owner(self) -> None:
        self.assertEqual(
            parse_routine_reference("do_work", default_owner="app"),
            ("APP", None, "DO_WORK"),
        )

    def test_parse_package_member(self) -> None:
        self.assertEqual(
            parse_routine_reference("pkg_jobs.run_job", default_owner="app"),
            ("APP", "PKG_JOBS", "RUN_JOB"),
        )

    def test_parse_owner_package_member(self) -> None:
        self.assertEqual(
            parse_routine_reference("app.pkg_jobs.run_job"),
            ("APP", "PKG_JOBS", "RUN_JOB"),
        )

    def test_rejects_conflicting_package_name(self) -> None:
        with self.assertRaises(SqlGuardError):
            parse_routine_reference("pkg_jobs.run_job", package_name="other_pkg")

    def test_normalize_source_type(self) -> None:
        self.assertEqual(normalize_source_type("package body"), "PACKAGE BODY")
        with self.assertRaises(SqlGuardError):
            normalize_source_type("VIEW")


if __name__ == "__main__":
    unittest.main()
