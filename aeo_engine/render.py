"""Turns a draft into HTML and schema.org JSON-LD."""
from __future__ import annotations

import html
import re
from datetime import date

import markdown as md

LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def full_markdown(draft: dict) -> str:
    faq = "\n\n".join(f"### {q['question']}\n\n{q['answer']}" for q in draft["faq"])
    takeaways = "\n".join(f"- {t}" for t in draft.get("key_takeaways", []))
    parts = [draft["intro"], draft["body_markdown"]]
    if takeaways:
        parts.append("## Key takeaways\n\n" + takeaways)
    if faq:
        parts.append("## Frequently asked questions\n\n" + faq)
    if draft.get("cta"):
        parts.append(draft["cta"])
    return "\n\n".join(parts)


def to_html(draft: dict) -> str:
    return md.markdown(full_markdown(draft), extensions=["extra"])


def links(text: str) -> list[tuple[str, str]]:
    return LINK.findall(text)


def json_ld(draft: dict, site: dict, published: str | None = None) -> list[dict]:
    url = f"{site['base_url'].rstrip('/')}/blog/{draft['slug']}"
    today = published or date.today().isoformat()
    org = {"@type": "Organization", "name": site["name"], "logo": {"@type": "ImageObject", "url": site["publisher_logo"]}}
    article = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": draft["title"][:110], "description": draft["meta_description"],
        "datePublished": today, "dateModified": today,
        "author": {"@type": "Organization", "name": site["author"]}, "publisher": org,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "inLanguage": site.get("locale", "en-US"),
    }
    blocks = [article]
    if draft.get("faq"):
        blocks.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q["question"],
                            "acceptedAnswer": {"@type": "Answer", "text": q["answer"]}} for q in draft["faq"]],
        })
    blocks.append({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Blog", "item": f"{site['base_url'].rstrip('/')}/blog"},
            {"@type": "ListItem", "position": 2, "name": draft["title"], "item": url},
        ],
    })
    return blocks


def preview_page(draft: dict, ld: list[dict], report: dict) -> str:
    import json
    issues = "".join(f"<li class='{i['severity']}'><b>{i['severity']}</b> {html.escape(i['rule'])}: {html.escape(i['message'])}</li>"
                     for i in report["issues"]) or "<li>No issues</li>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(draft['title'])}</title>
<meta name="description" content="{html.escape(draft['meta_description'])}">
<script type="application/ld+json">{json.dumps(ld)}</script>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1f2328}}
.review{{background:#f6f8fa;border:1px solid #d0d7de;border-radius:8px;padding:12px 16px;margin-bottom:28px;font-size:14px}}
.error{{color:#b42318}}.warn{{color:#9a6700}}code{{background:#f6f8fa}}</style></head><body>
<div class="review"><b>Review packet</b> · score {report['score']}/100 · {report['words']} words<br>
<b>Meta:</b> {html.escape(draft['meta_description'])} ({len(draft['meta_description'])} chars)<ul>{issues}</ul></div>
<h1>{html.escape(draft['title'])}</h1>{to_html(draft)}</body></html>"""
