"""Loads the reusable skill library (YAML prompt + output schema per skill)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import yaml

_VAR = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


@dataclass
class Skill:
    name: str
    version: str
    description: str
    system: str
    prompt: str
    output_schema: dict[str, Any]
    max_tokens: int = 2000

    def render(self, variables: dict[str, Any]) -> tuple[str, str]:
        def sub(text: str) -> str:
            def repl(m: re.Match) -> str:
                key = m.group(1)
                if key not in variables:
                    raise KeyError(f"Skill '{self.name}' needs variable '{key}'")
                value = variables[key]
                return ", ".join(value) if isinstance(value, list) else str(value)
            return _VAR.sub(repl, text)
        return sub(self.system), sub(self.prompt)

    def validate_output(self, data: Any) -> None:
        jsonschema.validate(instance=data, schema=self.output_schema)


class SkillLibrary:
    def __init__(self, folder: Path):
        self.folder = folder
        self.skills: dict[str, Skill] = {}
        for file in sorted(folder.glob("*.yaml")):
            spec = yaml.safe_load(file.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(spec["output_schema"])
            self.skills[spec["name"]] = Skill(
                name=spec["name"], version=str(spec["version"]), description=spec["description"],
                system=spec["system"], prompt=spec["prompt"], output_schema=spec["output_schema"],
                max_tokens=int(spec.get("max_tokens", 2000)),
            )

    def get(self, name: str) -> Skill:
        if name not in self.skills:
            raise KeyError(f"Unknown skill '{name}'. Available: {', '.join(self.skills)}")
        return self.skills[name]

    def versions(self) -> dict[str, str]:
        return {k: s.version for k, s in self.skills.items()}
