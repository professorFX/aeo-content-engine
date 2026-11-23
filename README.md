# AEO Content Engine

A Python pipeline that turns a reusable library of AI marketing skills into an operational SEO/AEO content engine. It covers keyword research, planning, briefs, drafting, a quality gate, auto-repair, human approval and CMS publishing.

```
keywords ──▶ plan ──▶ brief ──▶ draft ──▶ validate ──pass──▶ review queue ──approve──▶ publish (Sanity / Contentful / MDX)
 (CSV or      (skill)   (skill)   (skill)     │                      │
 DataForSEO)                                  └─fail─▶ repair with validator notes (skill, max N) ─┘
```

## Why it's built this way

- **Skills are data, not code.** Each skill is a YAML file in `skills/` with a version, system prompt, prompt template and JSON Schema for its output. Porting an existing prompt library means writing YAML, not Python. Every run records the skill versions it used.
- **Structured outputs only.** Model output is parsed and validated against the skill's schema. Invalid output is sent back once with the error, then fails cleanly.
- **One shared knowledge repo.** `knowledge/brand.yaml` holds voice, audience, banned phrases and approved product facts. `knowledge/site_pages.yaml` lists existing pages. Every skill reads them, and published articles are appended to the page list, so later runs link to them and don't cannibalise them.
- **A quality gate before any human sees it.** 20+ SEO/AEO rules: title and meta length, keyword placement, one H1, question-shaped H2s, an answer-first opening of 60 words or fewer, length vs brief, internal links that must exist, anchor text, FAQ shape and answer length, banned phrases, duplicate titles, keyword cannibalisation, and JSON-LD validity (Article, FAQPage, BreadcrumbList).
- **Auto-repair.** A failed draft goes back to the drafting skill with the exact validator findings, up to `max_repair_attempts` times.
- **Human approval is mandatory.** Nothing reaches the CMS unless an editor approves it. Sanity publishes to `drafts.*` and Contentful creates draft entries, so final publication still happens in the CMS.
- **Operable.**
  - Every stage writes `runs/<id>/state.json` atomically and appends to `events.jsonl`, with timings, scores and errors.
  - One failing item never stops the batch.
  - `run --resume <id>` restarts exactly where an item failed.
  - HTTP calls retry with exponential backoff on 429/5xx.

## Quick start

```bash
pip install -e ".[dev]"

# Offline demo: replays saved model outputs, no API keys needed
python -m aeo_engine --offline run
python -m aeo_engine --offline review list <run_id>
python -m aeo_engine --offline review approve <run_id> answer-engine-optimization --by "Editor"
python -m aeo_engine --offline publish <run_id>          # dry-run: writes the CMS payload to runs/<id>/publish/

# Live
export ANTHROPIC_API_KEY=...
python -m aeo_engine run
```

Review packets land in `runs/<id>/review/` as Markdown (for Git or Slack review) plus an HTML preview with the quality report on top. See `docs/review-preview.png`.

## Layout

| Path | What it holds |
| --- | --- |
| `config/engine.yaml` | Site, model, keyword source, validation thresholds, publish target. Secrets come from env vars |
| `skills/*.yaml` | `keyword_plan`, `content_brief`, `article_draft` (also used for repairs) |
| `knowledge/` | Brand rules, existing pages, seed keyword export |
| `aeo_engine/llm.py` | Anthropic client (retries, schema re-ask, token usage) and a fixture client for offline runs |
| `aeo_engine/keywords.py` | CSV export or DataForSEO provider, plus priority scoring (volume × intent ÷ difficulty) |
| `aeo_engine/validate.py` | The quality gate |
| `aeo_engine/render.py` | Markdown to HTML, JSON-LD builder, review preview |
| `aeo_engine/publish.py` | Sanity (mutations API), Contentful (CMA, draft entries), MDX with front matter for Next.js |
| `aeo_engine/pipeline.py` | Orchestration, state, logging, approval, publishing |
| `fixtures/` | Saved outputs for offline runs and tests (`tools/make_fixtures.py` regenerates them) |
| `sample-run/` | Output of the offline demo: review packets, Sanity payload, event log |
| `tests/` | 15 pytest tests |

## Adding a skill from an existing library

1. Create `skills/<name>.yaml` with `name`, `version`, `description`, `system`, `prompt` (use `{{variables}}`) and `output_schema`.
2. Call it from a stage with `self.llm.run_skill(self.skills.get("<name>"), variables, item=key)`.
3. Add a fixture in `fixtures/<name>/` and a test.

Every schema is checked when the library loads.

## Connecting a CMS

| Target | Needs | What gets created |
| --- | --- | --- |
| Sanity | `SANITY_PROJECT_ID`, `SANITY_TOKEN` (Editor role) | `drafts.post-<slug>` with title, slug, SEO object, markdown and HTML body, FAQ items, key takeaways, JSON-LD |
| Contentful | `CONTENTFUL_SPACE_ID`, `CONTENTFUL_MANAGEMENT_TOKEN` | Draft `blogPost` entry with localised fields |
| Markdown | nothing | `content/posts/<slug>.mdx` with front matter (title, description, FAQ, JSON-LD) for Next.js |

Field names follow a typical blog schema. Align them with the website's actual content model before the first live publish (`SanityPublisher.payload` / `ContentfulPublisher.payload`).

## What's verified

- 15 tests pass. They cover:
  - skill loading and templating
  - the validator on good and broken drafts
  - cannibalisation, duplicate titles, H1 and schema checks
  - auto-repair
  - failure isolation and resume
  - approval rules
  - Sanity, Contentful and MDX payloads
  - schema re-ask and HTTP retry logic
- The offline demo runs the full path. The second article fails the gate with 6 errors on its first draft, is repaired and passes at 95/100.
- Not yet run against the live Claude, DataForSEO or CMS APIs from this environment. Those calls follow each provider's published API and are isolated behind small adapter classes.

## Moving to LangGraph or n8n

The stages are plain functions over a persisted state dict, so each maps to a LangGraph node: the repair loop becomes a conditional edge and the approval step an interrupt. Alternatively, n8n can call `python -m aeo_engine run` on a schedule and post review packets to Slack.
