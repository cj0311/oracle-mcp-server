import contextlib
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oracle_mcp import db  # noqa: E402


class FakeLob:
    def __init__(self, lob_type, data, owner=None):
        self.type = lob_type
        self._data = data
        self._owner = owner

    def size(self):
        return len(self._data)

    def read(self, offset=1, amount=None):
        if self._owner is not None and self._owner.closed:
            raise RuntimeError("LOB read after connection close")
        start = max(offset - 1, 0)
        end = None if amount is None else start + amount
        return self._data[start:end]


class FakeColumn:
    def __init__(self, name):
        self.name = name


class FakeCursor:
    description = [FakeColumn("DOC")]

    def __init__(self, owner):
        self.owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, binds):
        return None

    def fetchmany(self, limit):
        return [(FakeLob(db.oracledb.DB_TYPE_CLOB, "hello", self.owner),)]


class FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class LobSerializationTests(unittest.TestCase):
    def test_clob_is_read_before_connection_closes(self) -> None:
        original_connect = db.connect
        original_lob_type = db.oracledb.LOB

        @contextlib.contextmanager
        def fake_connect(config, profile_name):
            connection = FakeConnection()
            try:
                yield connection
            finally:
                connection.close()

        try:
            db.connect = fake_connect
            db.oracledb.LOB = FakeLob
            result = db.execute_query(
                config=object(),
                profile_name="dev",
                sql="select doc from docs",
                binds={},
                limit=1,
                validate_sql=False,
            )
        finally:
            db.connect = original_connect
            db.oracledb.LOB = original_lob_type

        self.assertEqual(result["rows"], [{"doc": "hello"}])

    def test_large_clob_is_truncated_with_metadata(self) -> None:
        lob = FakeLob(db.oracledb.DB_TYPE_CLOB, "x" * (db.MAX_CELL_CHARS + 10))
        result = db.serialize_lob(lob)

        self.assertEqual(result["type"], "CLOB")
        self.assertEqual(len(result["value"]), db.MAX_CELL_CHARS)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["original_length"], db.MAX_CELL_CHARS + 10)

    def test_blob_returns_base64_prefix(self) -> None:
        lob = FakeLob(db.oracledb.DB_TYPE_BLOB, b"abcdef")
        result = db.serialize_lob(lob)

        self.assertEqual(result["type"], "BLOB")
        self.assertEqual(result["length"], 6)
        self.assertEqual(result["base64_prefix"], "YWJjZGVm")
        self.assertFalse(result["truncated"])


if __name__ == "__main__":
    unittest.main()
