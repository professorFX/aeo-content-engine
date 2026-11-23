import json
import shutil
import urllib.error
from pathlib import Path

import pytest
import yaml

from aeo_engine import llm as llm_mod
from aeo_engine.config import load_settings
from aeo_engine.keywords import Keyword, prioritise
from aeo_engine.knowledge import Knowledge
from aeo_engine.llm import AnthropicClient, LLMError, extract_json
from aeo_engine.pipeline import Run
from aeo_engine.publish import ContentfulPublisher, MarkdownPublisher
from aeo_engine.render import json_ld
from aeo_engine.skills import SkillLibrary
from aeo_engine.validate import revision_notes, validate

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path):
    for d in ("config", "skills", "knowledge", "fixtures"):
        shutil.copytree(ROOT / d, tmp_path / d)
    s = load_settings(tmp_path)
    s.raw["llm"]["provider"] = "fixtures"
    return s


def fixture(rel):
    return json.loads((ROOT / "fixtures" / rel).read_text())


# ---------- skills ----------
def test_skill_library_loads_and_versions():
    lib = SkillLibrary(ROOT / "skills")
    assert set(lib.skills) == {"keyword_plan", "content_brief", "article_draft"}
    assert all(v.count(".") == 2 for v in lib.versions().values())


def test_skill_render_requires_every_variable():
    skill = SkillLibrary(ROOT / "skills").get("content_brief")
    with pytest.raises(KeyError, match="needs variable"):
        skill.render({"brand": "x"})


# ---------- validation ----------
def _check(draft, brief, kw, settings):
    kb = Knowledge.load(settings.path("knowledge"))
    return validate(draft, brief, kw, json_ld(draft, settings["site"]), kb, settings["validation"])


def test_good_draft_passes(project):
    r = _check(fixture("article_draft/answer-engine-optimization.json"),
               fixture("content_brief/answer-engine-optimization.json"), "answer engine optimization", project)
    assert r["errors"] == 0 and r["score"] == 100 and r["words"] >= 720


def test_bad_draft_is_caught_with_specific_rules(project):
    r = _check(fixture("article_draft/agentic-website.attempt0.json"),
               fixture("content_brief/agentic-website.json"), "agentic website", project)
    rules = {i["rule"] for i in r["issues"] if i["severity"] == "error"}
    assert {"meta_length", "answer_first", "internal_links_valid", "faq_question", "faq_answer_length", "banned_phrase"} <= rules
    notes = revision_notes(r)
    assert "REVISION REQUEST" in notes and "agentic-web-guide" in notes


def test_cannibalisation_and_duplicate_title(project):
    d = fixture("article_draft/answer-engine-optimization.json") | {"title": "FAQ Pages That Rank in Search and AI Answers"}
    r = _check(d, fixture("content_brief/answer-engine-optimization.json"), "faq page seo", project)
    rules = {i["rule"] for i in r["issues"]}
    assert {"duplicate_title", "cannibalisation"} <= rules


def test_h1_in_body_and_missing_schema_fields(project):
    d = fixture("article_draft/answer-engine-optimization.json")
    d = d | {"body_markdown": "# Second H1\n\n" + d["body_markdown"]}
    kb = Knowledge.load(project.path("knowledge"))
    ld = json_ld(d, project["site"])
    del ld[0]["publisher"]
    r = validate(d, fixture("content_brief/answer-engine-optimization.json"), "answer engine optimization", ld, kb, project["validation"])
    rules = {i["rule"] for i in r["issues"]}
    assert {"single_h1", "structured_data"} <= rules


def test_json_ld_shapes(project):
    ld = json_ld(fixture("article_draft/answer-engine-optimization.json"), project["site"])
    assert [b["@type"] for b in ld] == ["Article", "FAQPage", "BreadcrumbList"]
    assert len(ld[1]["mainEntity"]) == 3


# ---------- pipeline ----------
def test_offline_run_repairs_and_queues(project):
    out = Run(project, "t1").run()
    items = out["items"]
    assert items["answer-engine-optimization"] == {"status": "in_review", "score": 100, "attempts": 1,
                                                   "title": "Answer Engine Optimization: What It Is and How to Do It", "error": None}
    assert items["agentic-website"]["attempts"] == 2 and items["agentic-website"]["score"] >= 80
    packet = (project.path("runs") / "t1" / "review" / "agentic-website.md").read_text()
    assert "READY FOR EDITOR" in packet and '"@type": "FAQPage"' in packet
    events = [json.loads(l) for l in (project.path("runs") / "t1" / "events.jsonl").read_text().splitlines()]
    assert any(e["stage"] == "validate" and e["status"] == "fail" for e in events)


def test_failure_isolated_and_resumable(project):
    brief = project.path("fixtures") / "content_brief" / "agentic-website.json"
    hidden = brief.with_suffix(".bak")
    brief.rename(hidden)
    out = Run(project, "t2").run()
    assert out["items"]["agentic-website"]["status"] == "failed"
    assert out["items"]["answer-engine-optimization"]["status"] == "in_review"  # other item unaffected
    hidden.rename(brief)
    out = Run(project, "t2").run()  # resume the same run id
    assert out["items"]["agentic-website"]["status"] == "in_review"


def test_only_approved_items_publish(project):
    run = Run(project, "t3")
    run.run()
    run.decide("answer-engine-optimization", True, by="Editor")
    run.decide("agentic-website", False, by="Editor", reason="hold")
    results = run.publish_approved()
    assert list(results) == ["answer-engine-optimization"]
    payload = json.loads(Path(results["answer-engine-optimization"]["payload_file"]).read_text())
    doc = payload["mutations"][0]["createOrReplace"]
    assert doc["_id"].startswith("drafts.") and doc["slug"]["current"] == "answer-engine-optimization"
    with pytest.raises(ValueError):
        run.decide("agentic-website", True)


def test_markdown_and_contentful_payloads(project, tmp_path):
    d = fixture("article_draft/answer-engine-optimization.json")
    ld = json_ld(d, project["site"])
    mp = MarkdownPublisher({"output_dir": "content/posts"}, tmp_path)
    res = mp.send(mp.payload(d, ld))
    text = Path(res["written"]).read_text()
    front = yaml.safe_load(text.split("---")[1])
    assert front["slug"] == d["slug"] and front["jsonLd"][0]["@type"] == "Article"
    cp = ContentfulPublisher({"content_type": "blogPost"}).payload(d, ld)
    assert cp["fields"]["title"]["en-US"] == d["title"] and cp["entry_id"] == "post-answer-engine-optimization"


# ---------- LLM client ----------
def test_extract_json_from_prose():
    assert extract_json('Sure! {"a": 1} Thanks') == {"a": 1}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_schema_retry_then_success(monkeypatch):
    skill = SkillLibrary(ROOT / "skills").get("keyword_plan")
    replies = iter([
        {"content": [{"type": "text", "text": '{"articles": []}'}], "usage": {"input_tokens": 10, "output_tokens": 5}},
        {"content": [{"type": "text", "text": json.dumps(fixture("keyword_plan/plan.json"))}], "usage": {"input_tokens": 10, "output_tokens": 50}},
    ])
    client = AnthropicClient("k", "m", schema_retries=1)
    monkeypatch.setattr(client, "_post", lambda payload: next(replies))
    vars_ = {k: "x" for k in ("brand", "audience", "keyword_table", "existing_pages", "article_count")}
    out = client.run_skill(skill, vars_)
    assert len(out["articles"]) == 2 and client.usage["calls"] == 2


def test_http_retry_on_overload(monkeypatch):
    calls = {"n": 0}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"content": []}'

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(req.full_url, 529, "overloaded", {}, None)
        return Resp()

    monkeypatch.setattr(llm_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    assert AnthropicClient("k", "m", max_retries=4)._post({}) == {"content": []}
    assert calls["n"] == 3


# ---------- keywords ----------
def test_prioritise_skips_targeted_and_ranks():
    kws = [Keyword("a b", 1000, 50, "informational"), Keyword("c d", 500, 5, "commercial"), Keyword("faq page seo", 9000, 1, "informational")]
    ranked = prioritise(kws, {"faq page seo"}, 10)
    assert [k.keyword for k in ranked] == ["c d", "a b"]
