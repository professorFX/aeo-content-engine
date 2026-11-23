from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Settings:
    root: Path
    raw: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def path(self, rel: str) -> Path:
        return (self.root / rel).resolve()


def load_settings(root: str | Path = ".", config_file: str = "config/engine.yaml") -> Settings:
    root = Path(root).resolve()
    with open(root / config_file, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Settings(root=root, raw=raw)


def secret(env_name: str) -> str:
    value = os.environ.get(env_name, "")
    if not value:
        raise RuntimeError(f"Missing environment variable {env_name}")
    return value
