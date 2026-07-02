from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError


class ConfigError(RuntimeError):
    """Raised when server configuration cannot be loaded."""


class Defaults(BaseModel):
    max_rows: int = Field(default=500, ge=1, le=10_000)
    query_timeout_seconds: int = Field(default=30, ge=1, le=600)
    sample_rows: int = Field(default=20, ge=1, le=1_000)


class DbProfile(BaseModel):
    description: str | None = None
    user: str
    password: str
    dsn: str
    default_owner: str | None = None
    config_dir: str | None = None
    wallet_location: str | None = None
    wallet_password: str | None = None
    thick_mode: bool = False
    max_rows: int | None = Field(default=None, ge=1, le=10_000)
    query_timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    sample_rows: int | None = Field(default=None, ge=1, le=1_000)

    def effective_max_rows(self, defaults: Defaults) -> int:
        return self.max_rows or defaults.max_rows

    def effective_timeout_seconds(self, defaults: Defaults) -> int:
        return self.query_timeout_seconds or defaults.query_timeout_seconds

    def effective_sample_rows(self, defaults: Defaults) -> int:
        return self.sample_rows or defaults.sample_rows


class AppConfig(BaseModel):
    defaults: Defaults = Field(default_factory=Defaults)
    profiles: dict[str, DbProfile]


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")
PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def resolve_config_path(path: str | None = None) -> Path:
    raw_path = path or os.environ.get("ORACLE_MCP_CONFIG") or "profiles.yaml"
    return Path(raw_path).expanduser().resolve()


def load_config(path: str | None = None) -> AppConfig:
    load_dotenv()
    config_path = resolve_config_path(path)
    load_dotenv(config_path.with_name(".env"), override=False)
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            "Set ORACLE_MCP_CONFIG or copy profiles.example.yaml to profiles.yaml."
        )

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc

    expanded = expand_env(raw)
    try:
        config = AppConfig.model_validate(expanded)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config in {config_path}: {exc}") from exc

    invalid_names = [
        name for name in config.profiles if not PROFILE_NAME_PATTERN.fullmatch(name)
    ]
    if invalid_names:
        raise ConfigError(
            "Invalid profile name(s): "
            + ", ".join(invalid_names)
            + ". Use letters, numbers, dot, underscore, or hyphen."
        )

    return config


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return expand_env_string(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def expand_env_string(value: str) -> str:
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        fallback = match.group(2)
        env_value = os.environ.get(env_name)
        if env_value is not None:
            return env_value
        if fallback is not None:
            return fallback
        missing.append(env_name)
        return match.group(0)

    expanded = ENV_PATTERN.sub(replace, value)
    if missing:
        raise ConfigError(
            "Missing environment variable(s): "
            + ", ".join(sorted(set(missing)))
            + f" while expanding value {value!r}."
        )
    return expanded
