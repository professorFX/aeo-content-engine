"""CMS publishers. Each builds a payload; dry-run writes it to disk instead of calling the CMS."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import Settings, secret
from .render import full_markdown, json_ld, to_html


def _request(url: str, payload: dict, headers: dict, method: str = "POST") -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CMS returned {e.code}: {e.read()[:300]!r}") from e


class SanityPublisher:
    name = "sanity"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def payload(self, draft: dict, ld: list[dict]) -> dict:
        prefix = "drafts." if self.cfg.get("as_draft", True) else ""
        doc = {
            "_id": f"{prefix}{self.cfg['document_type']}-{draft['slug']}",
            "_type": self.cfg["document_type"],
            "title": draft["title"],
            "slug": {"_type": "slug", "current": draft["slug"]},
            "excerpt": draft["meta_description"],
            "seo": {"_type": "seo", "metaTitle": draft["title"], "metaDescription": draft["meta_description"]},
            "bodyMarkdown": full_markdown(draft),
            "bodyHtml": to_html(draft),
            "faq": [{"_key": f"faq{i}", "_type": "faqItem", **q} for i, q in enumerate(draft["faq"])],
            "keyTakeaways": draft.get("key_takeaways", []),
            "jsonLd": json.dumps(ld),
            "publishedAt": datetime.now(timezone.utc).isoformat(),
        }
        return {"mutations": [{"createOrReplace": doc}]}

    def send(self, payload: dict) -> dict:
        project = secret(self.cfg["project_id_env"])
        url = f"https://{project}.api.sanity.io/{self.cfg['api_version']}/data/mutate/{self.cfg['dataset']}?returnIds=true"
        return _request(url, payload, {"Authorization": f"Bearer {secret(self.cfg['token_env'])}", "Content-Type": "application/json"})


class ContentfulPublisher:
    name = "contentful"

    def __init__(self, cfg: dict, locale: str = "en-US"):
        self.cfg, self.locale = cfg, locale

    def payload(self, draft: dict, ld: list[dict]) -> dict:
        L = self.locale
        return {"entry_id": f"post-{draft['slug']}"[:64], "fields": {
            "title": {L: draft["title"]}, "slug": {L: draft["slug"]},
            "metaDescription": {L: draft["meta_description"]}, "body": {L: full_markdown(draft)},
            "faq": {L: draft["faq"]}, "jsonLd": {L: ld}, "keyTakeaways": {L: draft.get("key_takeaways", [])},
        }}

    def send(self, payload: dict) -> dict:
        space = secret(self.cfg["space_env"])
        url = (f"https://api.contentful.com/spaces/{space}/environments/{self.cfg['environment']}"
               f"/entries/{payload['entry_id']}")
        # PUT creates or updates a draft entry; editors publish it in Contentful after review.
        return _request(url, {"fields": payload["fields"]}, {
            "Authorization": f"Bearer {secret(self.cfg['token_env'])}",
            "Content-Type": "application/vnd.contentful.management.v1+json",
            "X-Contentful-Content-Type": self.cfg["content_type"],
        }, method="PUT")


class MarkdownPublisher:
    """Writes MDX with front matter for Next.js sites that keep content in Git."""
    name = "markdown"

    def __init__(self, cfg: dict, root: Path):
        self.out = root / cfg["output_dir"]

    def payload(self, draft: dict, ld: list[dict]) -> dict:
        front = {"title": draft["title"], "description": draft["meta_description"], "slug": draft["slug"],
                 "date": datetime.now(timezone.utc).date().isoformat(), "faq": draft["faq"], "jsonLd": ld}
        return {"path": f"{draft['slug']}.mdx", "content": f"---\n{yaml.safe_dump(front, sort_keys=False, allow_unicode=True)}---\n\n{full_markdown(draft)}\n"}

    def send(self, payload: dict) -> dict:
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / payload["path"]).write_text(payload["content"], encoding="utf-8")
        return {"written": str(self.out / payload["path"])}


def get_publisher(settings: Settings):
    p = settings["publish"]
    if p["target"] == "sanity":
        return SanityPublisher(p["sanity"])
    if p["target"] == "contentful":
        return ContentfulPublisher(p["contentful"], settings["site"].get("locale", "en-US"))
    if p["target"] == "markdown":
        return MarkdownPublisher(p["markdown"], settings.root)
    raise ValueError(f"Unknown publish target {p['target']}")


def publish(draft: dict, settings: Settings, run_dir: Path) -> dict:
    pub = get_publisher(settings)
    ld = json_ld(draft, settings["site"])
    payload = pub.payload(draft, ld)
    out = run_dir / "publish"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{draft['slug']}.{pub.name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if settings["publish"].get("dry_run", True):
        return {"target": pub.name, "dry_run": True, "payload_file": str(out / f"{draft['slug']}.{pub.name}.json")}
    return {"target": pub.name, "dry_run": False, "response": pub.send(payload)}
