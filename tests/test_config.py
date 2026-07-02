import os
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oracle_mcp.config import ConfigError, load_config  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_load_config_expands_environment_variables(self) -> None:
        os.environ["UNIT_ORACLE_USER"] = "readonly"
        os.environ["UNIT_ORACLE_PASSWORD"] = "secret"
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "profiles.yaml"
            config_path.write_text(
                """
defaults:
  max_rows: 100
profiles:
  dev:
    user: "${UNIT_ORACLE_USER}"
    password: "${UNIT_ORACLE_PASSWORD}"
    dsn: "localhost:1521/XEPDB1"
""",
                encoding="utf-8",
            )
            config = load_config(str(config_path))

        self.assertEqual(config.defaults.max_rows, 100)
        self.assertEqual(config.profiles["dev"].user, "readonly")
        self.assertEqual(config.profiles["dev"].password, "secret")

    def test_missing_env_var_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "profiles.yaml"
            config_path.write_text(
                """
profiles:
  dev:
    user: "${MISSING_UNIT_USER}"
    password: "secret"
    dsn: "localhost:1521/XEPDB1"
""",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_config(str(config_path))


if __name__ == "__main__":
    unittest.main()
