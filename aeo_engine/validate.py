"""SEO/AEO quality gate. Every rule returns errors (block review) or warnings (shown to the editor)."""
from __future__ import annotations

import difflib
import re

import jsonschema

from .knowledge import Knowledge
from .render import full_markdown, links

_ARTICLE_LD = {
    "type": "object",
    "required": ["@context", "@type", "headline", "datePublished", "author", "publisher", "mainEntityOfPage"],
    "properties": {"headline": {"type": "string", "maxLength": 110}},
}
_FAQ_LD = {
    "type": "object", "required": ["@type", "mainEntity"],
    "properties": {"mainEntity": {"type": "array", "minItems": 1, "items": {
        "type": "object", "required": ["@type", "name", "acceptedAnswer"],
        "properties": {"acceptedAnswer": {"type": "object", "required": ["@type", "text"]}}}}},
}
GENERIC_ANCHORS = {"here", "click here", "this", "read more", "link", "this article"}


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)))


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in {"the", "and", "for", "what", "how"}}


def _coverage(phrase: str, text: str) -> float:
    need = _tokens(phrase)
    return len(need & _tokens(text)) / len(need) if need else 1.0


def validate(draft: dict, brief: dict, primary_keyword: str, ld: list[dict], kb: Knowledge, rules: dict, self_url: str = "") -> dict:
    issues: list[dict] = []

    def add(severity: str, rule: str, message: str) -> None:
        issues.append({"severity": severity, "rule": rule, "message": message})

    title, meta, slug = draft["title"], draft["meta_description"], draft["slug"]
    lo, hi = rules["title_chars"]
    if not lo <= len(title) <= hi:
        add("error", "title_length", f"Title is {len(title)} chars; needs {lo}-{hi}.")
    if _coverage(primary_keyword, title) < 0.75:
        add("error", "title_keyword", f"Title should contain the primary keyword '{primary_keyword}'.")
    lo, hi = rules["meta_chars"]
    if not lo <= len(meta) <= hi:
        add("error", "meta_length", f"Meta description is {len(meta)} chars; needs {lo}-{hi}.")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or len(slug) > rules["slug_max_chars"]:
        add("error", "slug_format", f"Slug '{slug}' must be lowercase-hyphenated and at most {rules['slug_max_chars']} chars.")
    elif _coverage(primary_keyword, slug.replace("-", " ")) < 0.5:
        add("warn", "slug_keyword", "Slug carries little of the primary keyword.")

    body = draft["body_markdown"]
    if re.search(r"(?m)^#\s", body):
        add("error", "single_h1", "Body contains an H1; the title is the only H1.")
    h2 = re.findall(r"(?m)^##\s+(.+)$", body)
    if len(h2) < rules["min_h2"]:
        add("error", "h2_count", f"Only {len(h2)} H2 sections; need at least {rules['min_h2']}.")
    if h2 and not any(h.strip().endswith("?") for h in h2):
        add("warn", "question_headings", "No question-shaped H2. AI answers often lift question/answer pairs.")

    intro_words = _words(draft["intro"])
    if intro_words > rules["answer_first_max_words"]:
        add("error", "answer_first", f"Opening paragraph is {intro_words} words; the direct answer must fit in {rules['answer_first_max_words']}.")
    if _coverage(primary_keyword, draft["intro"]) < 0.75:
        add("warn", "intro_keyword", "Opening paragraph doesn't name the topic in the searcher's words.")

    text = full_markdown(draft)
    words = _words(text)
    target = int(brief.get("target_words", 1000))
    if words < 0.6 * target:
        add("error", "length", f"{words} words vs a {target}-word target.")
    elif words < 0.8 * target:
        add("warn", "length", f"{words} words vs a {target}-word target.")

    found = links(draft["intro"] + "\n" + body)
    internal = [(a, u) for a, u in found if u.startswith("/")]
    known = kb.page_urls()
    broken = [u for _, u in internal if u.split("#")[0] not in known]
    if broken:
        add("error", "internal_links_valid", f"Links to pages that don't exist: {', '.join(sorted(set(broken)))}.")
    valid = {u for _, u in internal if u.split("#")[0] in known and u != self_url}
    if len(valid) < rules["min_internal_links"]:
        add("error", "internal_links_count", f"{len(valid)} valid internal links; need {rules['min_internal_links']}.")
    weak = [a for a, _ in found if a.strip().lower() in GENERIC_ANCHORS]
    if weak:
        add("warn", "anchor_text", f"Generic anchor text: {', '.join(weak)}.")
    missing = [u for u in brief.get("internal_links", []) if u not in {x for _, x in internal}]
    if missing:
        add("warn", "brief_links", f"Brief asked for links not used: {', '.join(missing)}.")

    faq = draft.get("faq", [])
    lo, hi = rules["faq_count"]
    if not lo <= len(faq) <= hi:
        add("error", "faq_count", f"{len(faq)} FAQ items; need {lo}-{hi}.")
    alo, ahi = rules["faq_answer_words"]
    for q in faq:
        if not q["question"].strip().endswith("?"):
            add("error", "faq_question", f"FAQ question isn't a question: '{q['question'][:60]}'.")
        n = _words(q["answer"])
        if not alo <= n <= ahi:
            add("error", "faq_answer_length", f"Answer to '{q['question'][:50]}' is {n} words; needs {alo}-{ahi}.")

    lowered = text.lower() + " " + title.lower() + " " + meta.lower()
    for phrase in kb.brand.get("avoid_phrases", []):
        if phrase.lower() in lowered:
            add("error", "banned_phrase", f"Uses banned phrase '{phrase}'.")

    for page in kb.pages:
        if page.url == self_url:
            continue
        ratio = difflib.SequenceMatcher(None, title.lower(), page.title.lower()).ratio()
        if ratio >= rules["duplicate_title_ratio"]:
            add("error", "duplicate_title", f"Title is {round(ratio * 100)}% similar to {page.url}.")
        if page.target_keyword.strip().lower() == primary_keyword.strip().lower():
            add("error", "cannibalisation", f"{page.url} already targets '{primary_keyword}'.")

    for block in ld:
        try:
            if block["@type"] == "Article":
                jsonschema.validate(block, _ARTICLE_LD)
            elif block["@type"] == "FAQPage":
                jsonschema.validate(block, _FAQ_LD)
        except jsonschema.ValidationError as e:
            add("error", "structured_data", f"{block['@type']} JSON-LD invalid: {e.message}")

    errors = sum(1 for i in issues if i["severity"] == "error")
    warns = len(issues) - errors
    score = max(0, 100 - 15 * errors - 5 * warns)
    return {"score": score, "errors": errors, "warnings": warns, "words": words, "issues": issues}


def revision_notes(report: dict) -> str:
    lines = [f"- [{i['severity']}] {i['rule']}: {i['message']}" for i in report["issues"]]
    return ("REVISION REQUEST: the previous draft failed the quality gate. Fix every item below, "
            "keep everything else, and return the full JSON again.\n" + "\n".join(lines))
