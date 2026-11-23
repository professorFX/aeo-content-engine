"""Orchestration: plan -> brief -> draft -> validate (+repair) -> review queue -> publish.

State is saved after every stage in runs/<run_id>/state.json, so a failed or interrupted run
resumes where it stopped. One item failing never stops the others.
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings, secret
from .keywords import CsvKeywordProvider, DataForSEOProvider, keyword_table, prioritise
from .knowledge import Knowledge
from .llm import AnthropicClient, FixtureClient
from .publish import publish
from .render import full_markdown, json_ld, preview_page, slugify
from .skills import SkillLibrary
from .validate import revision_notes, validate

STAGES = ["planned", "briefed", "drafted", "in_review", "approved", "published"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Run:
    def __init__(self, settings: Settings, run_id: str | None = None, llm=None):
        self.s = settings
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.dir = settings.path("runs") / self.run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "state.json"
        self.kb = Knowledge.load(settings.path("knowledge"))
        self.skills = SkillLibrary(settings.path("skills"))
        self.llm = llm or self._make_llm()
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {
            "run_id": self.run_id, "created": now(), "skill_versions": self.skills.versions(), "items": {}}

    def _make_llm(self):
        c = self.s["llm"]
        if c["provider"] == "fixtures":
            return FixtureClient(self.s.path("fixtures"))
        return AnthropicClient(secret(c["api_key_env"]), c["model"], c["max_retries"], c["schema_retries"], c["timeout_s"])

    # ---------- bookkeeping ----------
    def save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    def log(self, item: str, stage: str, status: str, **extra) -> None:
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": now(), "run": self.run_id, "item": item, "stage": stage, "status": status, **extra}) + "\n")

    def _stage(self, key: str, stage: str, fn) -> bool:
        item = self.state["items"][key]
        t0 = time.time()
        try:
            fn(item)
            item["history"].append({"stage": stage, "at": now()})
            self.log(key, stage, "ok", seconds=round(time.time() - t0, 2))
            return True
        except Exception as e:  # one item's failure must not stop the batch
            item["status"], item["error"] = "failed", f"{stage}: {e}"
            self.log(key, stage, "error", error=str(e), trace=traceback.format_exc()[-800:])
            return False
        finally:
            self.save()

    # ---------- stages ----------
    def plan(self) -> list[str]:
        if self.state["items"]:
            return list(self.state["items"])
        kc = self.s["keywords"]
        if kc["provider"] == "dataforseo":
            d = kc["dataforseo"]
            seeds = [p.target_keyword for p in self.kb.pages]
            provider = DataForSEOProvider(secret(d["login_env"]), secret(d["password_env"]), seeds, d["location_code"], d["language_code"])
        else:
            provider = CsvKeywordProvider(self.s.path(kc["csv_path"]))
        targeted = {p.target_keyword.lower() for p in self.kb.pages}
        ranked = prioritise(provider.fetch(), targeted, kc["max_keywords_to_plan"])
        vars_ = self.kb.template_vars() | {"keyword_table": keyword_table(ranked), "article_count": kc["articles_per_run"]}
        plan = self.llm.run_skill(self.skills.get("keyword_plan"), vars_, item="plan")
        for art in plan["articles"][: kc["articles_per_run"]]:
            key = slugify(art["primary_keyword"])
            if art["primary_keyword"].lower() in targeted:
                self.log(key, "plan", "skipped", reason="already targeted by an existing page")
                continue
            self.state["items"][key] = {"key": key, "status": "planned", "plan": art, "history": [{"stage": "planned", "at": now()}]}
            self.log(key, "plan", "ok", keyword=art["primary_keyword"])
        self.state["keywords_considered"] = len(ranked)
        self.save()
        return list(self.state["items"])

    def brief(self, key: str) -> bool:
        def fn(item):
            p = item["plan"]
            vars_ = self.kb.template_vars() | {k: p[k] for k in ("topic", "primary_keyword", "secondary_keywords", "intent", "content_type")}
            item["brief"] = self.llm.run_skill(self.skills.get("content_brief"), vars_, item=key)
            item["status"] = "briefed"
        return self._stage(key, "brief", fn)

    def draft(self, key: str) -> bool:
        rules = self.s["validation"]

        def fn(item):
            vars_ = self.kb.template_vars() | {"brief_json": json.dumps(item["brief"], indent=2), "revision_notes": ""}
            attempts = []
            for attempt in range(rules["max_repair_attempts"] + 1):
                draft = self.llm.run_skill(self.skills.get("article_draft"), vars_, item=key, attempt=attempt)
                ld = json_ld(draft, self.s["site"])
                report = validate(draft, item["brief"], item["plan"]["primary_keyword"], ld, self.kb, rules)
                attempts.append({"attempt": attempt, "score": report["score"], "errors": report["errors"]})
                self.log(key, "validate", "pass" if self._passes(report) else "fail", attempt=attempt, score=report["score"],
                         errors=[i["rule"] for i in report["issues"] if i["severity"] == "error"])
                if self._passes(report):
                    break
                vars_["revision_notes"] = revision_notes(report)
            item.update(draft=draft, json_ld=ld, report=report, attempts=attempts, status="drafted")
        return self._stage(key, "draft", fn)

    def _passes(self, report: dict) -> bool:
        return report["errors"] == 0 and report["score"] >= self.s["validation"]["min_score_for_review"]

    def queue_for_review(self, key: str) -> bool:
        def fn(item):
            review = self.dir / "review"
            review.mkdir(exist_ok=True)
            d, r = item["draft"], item["report"]
            flag = "READY FOR EDITOR" if self._passes(r) else "NEEDS EDITOR ATTENTION (failed quality gate after repair)"
            issues = "\n".join(f"- **{i['severity']}** `{i['rule']}`: {i['message']}" for i in r["issues"]) or "- none"
            packet = (f"# Review: {d['title']}\n\n**Status:** {flag}  \n**Score:** {r['score']}/100 · {r['words']} words · "
                      f"attempts: {len(item['attempts'])}  \n**Primary keyword:** {item['plan']['primary_keyword']}  \n"
                      f"**Slug:** /{d['slug']}  \n**Meta ({len(d['meta_description'])} chars):** {d['meta_description']}\n\n"
                      f"## Quality gate\n{issues}\n\n## Approve or reject\n"
                      f"`python -m aeo_engine review approve {self.run_id} {key} --by \"Your Name\"`  \n"
                      f"`python -m aeo_engine review reject {self.run_id} {key} --reason \"...\"`\n\n---\n\n"
                      f"# {d['title']}\n\n" + full_markdown(d) +
                      "\n\n---\n\n## JSON-LD\n\n```json\n" + json.dumps(item["json_ld"], indent=2) + "\n```\n")
            (review / f"{key}.md").write_text(packet, encoding="utf-8")
            (review / f"{key}.html").write_text(preview_page(d, item["json_ld"], r), encoding="utf-8")
            item["status"] = "in_review"
            item["review"] = {"flag": flag, "packet": f"review/{key}.md"}
        return self._stage(key, "review_queue", fn)

    def run(self) -> dict:
        keys = self.plan()
        for key in keys:
            item = self.state["items"][key]
            if item["status"] == "failed":
                item["status"] = item.get("last_good", "planned")  # resume after a fix
            order = [("planned", self.brief), ("briefed", self.draft), ("drafted", self.queue_for_review)]
            for needed, step in order:
                if self.state["items"][key]["status"] == needed:
                    self.state["items"][key]["last_good"] = needed
                    if not step(key):
                        break
        return self.summary()

    # ---------- human approval and publishing ----------
    def decide(self, key: str, approve: bool, by: str = "", reason: str = "") -> None:
        item = self.state["items"][key]
        if item["status"] != "in_review":
            raise ValueError(f"{key} is '{item['status']}', not in review")
        item["status"] = "approved" if approve else "rejected"
        item["decision"] = {"by": by, "reason": reason, "at": now()}
        item["history"].append({"stage": item["status"], "at": now(), "by": by})
        self.log(key, "review", item["status"], by=by, reason=reason)
        self.save()

    def publish_approved(self) -> dict:
        results = {}
        for key, item in self.state["items"].items():
            if item["status"] != "approved":
                continue
            def fn(it, key=key):
                it["publish"] = publish(it["draft"], self.s, self.dir)
                it["status"] = "published"
                self.kb.add_published(f"/blog/{it['draft']['slug']}", it["draft"]["title"], it["plan"]["primary_keyword"])
            self._stage(key, "publish", fn)
            results[key] = item.get("publish") or item.get("error")
        return results

    def summary(self) -> dict:
        items = self.state["items"]
        return {"run_id": self.run_id, "folder": str(self.dir), "items": {
            k: {"status": v["status"], "score": v.get("report", {}).get("score"), "attempts": len(v.get("attempts", [])),
                "title": v.get("draft", {}).get("title"), "error": v.get("error")} for k, v in items.items()}}
