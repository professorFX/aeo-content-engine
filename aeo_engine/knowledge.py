"""Shared marketing repository: brand rules and the site's existing pages."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Page:
    url: str
    title: str
    target_keyword: str
    topics: list[str] = field(default_factory=list)


@dataclass
class Knowledge:
    brand: dict
    pages: list[Page]

    @classmethod
    def load(cls, folder: Path) -> "Knowledge":
        brand = yaml.safe_load((folder / "brand.yaml").read_text(encoding="utf-8"))
        pages = [Page(**p) for p in yaml.safe_load((folder / "site_pages.yaml").read_text(encoding="utf-8"))]
        return cls(brand=brand, pages=pages)

    def page_urls(self) -> set[str]:
        return {p.url for p in self.pages}

    def pages_table(self) -> str:
        return "\n".join(f"- {p.url} | {p.title} | targets: {p.target_keyword}" for p in self.pages)

    def template_vars(self) -> dict[str, str]:
        b = self.brand
        return {
            "brand": b["brand"],
            "audience": b["audience"],
            "voice": "\n".join(f"- {v}" for v in b.get("voice", [])),
            "avoid_phrases": ", ".join(b.get("avoid_phrases", [])),
            "product_facts": "; ".join(b.get("product_facts", [])),
            "existing_pages": self.pages_table(),
        }

    def add_published(self, url: str, title: str, keyword: str) -> None:
        """Newly published articles become link targets and duplicate guards for the next run."""
        self.pages.append(Page(url=url, title=title, target_keyword=keyword))
