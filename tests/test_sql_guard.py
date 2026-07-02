import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oracle_mcp.sql_guard import (  # noqa: E402
    SqlGuardError,
    split_table_name,
    validate_identifier,
    validate_readonly_sql,
)


class SqlGuardTests(unittest.TestCase):
    def test_allows_select_and_with(self) -> None:
        self.assertEqual(validate_readonly_sql("select * from dual;"), "select * from dual")
        self.assertEqual(
            validate_readonly_sql("with q as (select 1 x from dual) select * from q"),
            "with q as (select 1 x from dual) select * from q",
        )

    def test_ignores_keywords_in_string_literals_and_comments(self) -> None:
        sql = "select 'delete' as word from dual -- drop table x"
        self.assertEqual(validate_readonly_sql(sql), sql)

    def test_rejects_non_select_sql(self) -> None:
        for sql in [
            "update t set x = 1",
            "delete from t",
            "begin null; end;",
            "select * from t for update",
            "select * from t; select * from y",
            "with function f return number is begin return 1; end; select f from dual",
        ]:
            with self.subTest(sql=sql):
                with self.assertRaises(SqlGuardError):
                    validate_readonly_sql(sql)

    def test_identifier_validation(self) -> None:
        self.assertEqual(validate_identifier("app_table"), "APP_TABLE")
        with self.assertRaises(SqlGuardError):
            validate_identifier("app.table")
        with self.assertRaises(SqlGuardError):
            validate_identifier("table-name")

    def test_split_table_name(self) -> None:
        self.assertEqual(split_table_name("hr.emp"), ("HR", "EMP"))
        self.assertEqual(split_table_name("emp", owner="hr"), ("HR", "EMP"))
        with self.assertRaises(SqlGuardError):
            split_table_name("hr.emp", owner="other")


if __name__ == "__main__":
    unittest.main()
