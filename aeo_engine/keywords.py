"""Keyword sources and prioritisation."""
from __future__ import annotations

import base64
import csv
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

INTENT_WEIGHT = {"transactional": 1.6, "commercial": 1.3, "informational": 1.0, "navigational": 0.4}


@dataclass
class Keyword:
    keyword: str
    volume: int
    difficulty: int
    intent: str

    @property
    def priority(self) -> float:
        # value per unit of difficulty; tuned for sites with modest authority
        return round(self.volume * INTENT_WEIGHT.get(self.intent, 1.0) / (self.difficulty + 10), 1)


class CsvKeywordProvider:
    """Reads an export from Ahrefs/Semrush/Keyword Planner with keyword, volume, difficulty, intent."""

    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> list[Keyword]:
        with open(self.path, newline="", encoding="utf-8") as fh:
            return [Keyword(r["keyword"].strip().lower(), int(r["monthly_volume"]), int(r["difficulty"]),
                            r.get("intent", "informational").strip()) for r in csv.DictReader(fh)]


class DataForSEOProvider:
    """Keyword ideas from DataForSEO Labs (live endpoint)."""

    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live"

    def __init__(self, login: str, password: str, seeds: list[str], location_code: int = 2840, language_code: str = "en"):
        self.auth = base64.b64encode(f"{login}:{password}".encode()).decode()
        self.seeds, self.location_code, self.language_code = seeds, location_code, language_code

    def fetch(self) -> list[Keyword]:
        payload = [{"keywords": self.seeds, "location_code": self.location_code, "language_code": self.language_code, "limit": 200}]
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": f"Basic {self.auth}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        out = []
        for task in data.get("tasks", []):
            for res in task.get("result") or []:
                for it in res.get("items", []):
                    info = it.get("keyword_info") or {}
                    props = it.get("keyword_properties") or {}
                    intent = ((it.get("search_intent_info") or {}).get("main_intent") or "informational")
                    out.append(Keyword(it["keyword"], int(info.get("search_volume") or 0),
                                       int(props.get("keyword_difficulty") or 50), intent))
        return out


def prioritise(keywords: list[Keyword], already_targeted: set[str], limit: int) -> list[Keyword]:
    seen, ranked = set(), []
    for k in sorted(keywords, key=lambda k: k.priority, reverse=True):
        if k.keyword in already_targeted or k.keyword in seen:
            continue
        seen.add(k.keyword)
        ranked.append(k)
    return ranked[:limit]


def keyword_table(keywords: list[Keyword]) -> str:
    return "\n".join(f"{k.keyword} | {k.volume} | {k.difficulty} | {k.intent} | {k.priority}" for k in keywords)
