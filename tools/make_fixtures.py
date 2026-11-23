"""Writes the offline fixtures used by --offline runs and the tests.

They stand in for model output so the whole pipeline (validation, repair, review, publish)
can be demonstrated without API keys. The second draft deliberately fails the quality gate on
its first attempt so the auto-repair path is exercised.
"""
import json
from pathlib import Path

F = Path(__file__).resolve().parent.parent / "fixtures"


def dump(rel, data):
    p = F / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


dump("keyword_plan/plan.json", {"articles": [
    {"topic": "What answer engine optimization is and how to do it", "primary_keyword": "answer engine optimization",
     "secondary_keywords": ["what is answer engine optimization", "aeo vs seo", "how to optimize for ai answers"],
     "intent": "informational", "content_type": "explainer",
     "rationale": "Highest priority score in the set and no existing page targets it."},
    {"topic": "What an agentic website is and why B2B teams need one", "primary_keyword": "agentic website",
     "secondary_keywords": ["what is an agentic website", "agentic web", "ai agent ready website"],
     "intent": "informational", "content_type": "explainer",
     "rationale": "Low difficulty, close to the product, and the cluster includes a commercial modifier."},
]})

dump("content_brief/answer-engine-optimization.json", {
    "working_title": "Answer Engine Optimization: What It Is and How to Do It",
    "slug": "answer-engine-optimization",
    "search_intent": "Understand AEO, how it differs from SEO, and the first concrete steps.",
    "target_words": 900,
    "direct_answer": "AEO is the practice of structuring content so AI assistants and search features can lift it as the answer.",
    "outline": [
        {"h2": "How is AEO different from SEO?", "points": ["Same foundations", "Different unit: the answer, not the page"]},
        {"h2": "What do answer engines look for?", "points": ["Direct answers", "Clear structure", "Trust signals", "Structured data"]},
        {"h2": "How to optimize a page for AI answers", "points": ["Answer first", "Question headings", "FAQ with schema", "Internal links"]},
        {"h2": "How to measure AEO", "points": ["AI citations", "Featured snippets", "Branded search"]},
    ],
    "faq_questions": ["Is AEO replacing SEO?", "Does schema markup help AI answers?", "How long does AEO take to show results?"],
    "internal_links": ["/blog/how-ai-assistants-choose-sources", "/blog/faq-pages-that-rank", "/blog/schema-markup-for-b2b-saas"],
    "schema_types": ["Article", "FAQPage"],
})

dump("content_brief/agentic-website.json", {
    "working_title": "What Is an Agentic Website? A Guide for B2B Teams",
    "slug": "agentic-website",
    "search_intent": "Define an agentic website and judge whether it matters for a B2B site now.",
    "target_words": 900,
    "direct_answer": "An agentic website is built so AI agents can read it and complete tasks on it, not just display pages to people.",
    "outline": [
        {"h2": "What makes a website agentic?", "points": ["Machine-readable content", "Actions agents can call", "Clear permissions"]},
        {"h2": "Why it matters for B2B buyers", "points": ["Research through assistants", "Fewer form fills"]},
        {"h2": "How to make your site agent-ready", "points": ["Structured data", "Action endpoints", "Answer-first content"]},
        {"h2": "What to measure", "points": ["Agent sessions", "Actions completed", "Pipeline from agents"]},
    ],
    "faq_questions": ["Do agentic websites replace normal websites?", "Is an agentic website secure?", "Do I need to rebuild my site?"],
    "internal_links": ["/features/actions", "/blog/schema-markup-for-b2b-saas", "/blog/how-ai-assistants-choose-sources"],
    "schema_types": ["Article", "FAQPage"],
})

aeo = {
    "title": "Answer Engine Optimization: What It Is and How to Do It",
    "meta_description": "Answer engine optimization (AEO) shapes your content so AI assistants and search features quote it. Learn how it differs from SEO and how to start.",
    "slug": "answer-engine-optimization",
    "intro": "Answer engine optimization (AEO) is the practice of structuring your content so AI assistants, voice search and search features can lift it as the answer to a question. It builds on SEO, but the unit you optimize is the answer, not the whole page.",
    "body_markdown": """## How is AEO different from SEO?

SEO and AEO share the same foundations: crawlable pages, useful content and a site people trust. The difference is what gets rewarded. Classic SEO competes for a ranked link that a person clicks. AEO competes to be the sentence an assistant repeats, the snippet Google shows above the results, or the source an AI answer cites.

That changes how you write. A page can rank well and still never be quoted, because the answer is buried in the fourth paragraph or spread across a story. Answer engines prefer content where the question and its answer sit close together, in plain language, with nothing to untangle.

## What do answer engines look for?

Assistants and search features tend to favour four things:

- **A direct answer.** One or two sentences that answer the question without a preamble.
- **Clear structure.** Headings that match the questions people ask, short paragraphs and lists where the content is a list.
- **Trust signals.** A named author or organisation, consistent facts across your site, and sources other sites already cite. Our guide on [how AI assistants choose which sources to cite](/blog/how-ai-assistants-choose-sources) covers this in detail.
- **Machine-readable context.** Structured data that labels what each part of the page is, such as an article, a product or a list of questions.

None of these replace quality. They make good content easier to extract.

## How to optimize a page for AI answers

Start with pages that already rank or already answer common customer questions. Then work through these steps:

1. **Lead with the answer.** Put a 40 to 60 word answer directly under the title. Expand after it, not before it.
2. **Turn headings into questions** where it reads naturally, for example "How long does onboarding take?" instead of "Onboarding".
3. **Add an FAQ section** with the follow-up questions buyers actually ask. Keep each answer self-contained, because an assistant may quote it alone. See [FAQ pages that rank in search and AI answers](/blog/faq-pages-that-rank).
4. **Mark it up.** Add Article and FAQPage structured data so the page type and each question-answer pair are explicit. Our [schema markup guide for B2B SaaS](/blog/schema-markup-for-b2b-saas) shows the fields that matter.
5. **Keep facts consistent.** If your pricing page says one thing and a blog post says another, assistants may skip both.

## How to measure AEO

AEO results are harder to see than rankings, so track several signals together. Check whether AI assistants cite your pages for your target questions, and record the answer each week. Watch featured snippets and "People also ask" placements in Search Console. Branded search and direct traffic often rise when assistants mention you, even when they don't link.

Give changes six to eight weeks before judging them, and change one variable at a time so you know what worked.""",
    "faq": [
        {"question": "Is AEO replacing SEO?",
         "answer": "No. AEO builds on SEO rather than replacing it. Answer engines still rely on pages they can crawl and trust, so technical SEO and quality content remain the base. AEO adds a focus on clear, quotable answers and structured data on top of that base."},
        {"question": "Does schema markup help AI answers?",
         "answer": "Schema markup helps machines understand what each part of a page is, such as an article, a product or a question and its answer. It does not guarantee a citation, but it removes ambiguity, which makes accurate extraction more likely when your content is already the best answer."},
        {"question": "How long does AEO take to show results?",
         "answer": "Expect six to eight weeks for search features to reflect changes on pages that are already indexed. AI assistants can take longer because their sources refresh on their own schedules. Track citations and featured snippets weekly so you can see gradual movement instead of waiting for one big shift."},
    ],
    "key_takeaways": [
        "AEO optimizes the answer, not just the page.",
        "Lead with a 40 to 60 word answer, then expand.",
        "Question headings, FAQs and structured data make answers easy to extract.",
        "Measure citations and snippets, not only rankings.",
    ],
    "cta": "See how Relay structures your pages for AI answers. Book a 20-minute walkthrough.",
}
dump("article_draft/answer-engine-optimization.json", aeo)

agentic_ok = {
    "title": "What Is an Agentic Website? A Guide for B2B Teams",
    "meta_description": "An agentic website lets AI agents read your pages and complete tasks like booking a demo. Learn what makes a site agentic and how to get B2B-ready.",
    "slug": "agentic-website",
    "intro": "An agentic website is built so AI agents can read it and complete tasks on it, such as comparing plans or booking a demo, not just display pages to people. For B2B teams, it means buyers' assistants can act on your site directly.",
    "body_markdown": """## What makes a website agentic?

Most websites are built for a person with a browser. An agentic website also serves software agents acting for that person. Three things set it apart.

First, the content is machine-readable. Pages use structured data and consistent naming, so an agent can tell a price from a feature list without guessing. Second, the site exposes actions: defined ways for an agent to request a quote, check availability or book a meeting, with clear inputs and responses. Third, it has clear permissions. The site states what an agent may do on a user's behalf and what still needs a human.

## Why does it matter for B2B buyers?

B2B buyers increasingly start research by asking an assistant to shortlist vendors, compare pricing models or summarise security documentation. If your site is hard for an agent to read, your product is harder to include in that shortlist. If it is easy to read but offers no way to act, the buyer's next step still means a form, an email and a wait.

Agentic sites shorten that path. An agent that can confirm your integrations, pull the right case study and book a call removes several steps from the buyer's journey. [Relay Actions](/features/actions) is one example of exposing those steps safely.

## How to make your site agent-ready

You don't need to rebuild your site to start. Work through these layers in order:

1. **Clean up structure.** Use one heading hierarchy, descriptive titles and consistent terms for products and plans.
2. **Add structured data.** Mark up your organisation, products, articles and FAQs. Our [schema markup guide for B2B SaaS](/blog/schema-markup-for-b2b-saas) covers the types that matter most.
3. **Write answer-first.** Agents and assistants quote short, direct answers. Put the answer at the top of each page and section. For how assistants pick what to quote, see [how AI assistants choose sources](/blog/how-ai-assistants-choose-sources).
4. **Expose a few safe actions.** Start with low-risk tasks such as booking a demo or requesting pricing, with rate limits and logging.
5. **Keep a human in the loop** for anything contractual, financial or irreversible.

## What should you measure?

Track agent activity separately from human traffic so you can see its value. Useful measures include sessions from known AI agents, the actions they complete, the share of demo requests that arrive through an agent, and the pipeline those requests create. Review failed actions too. They show where your content or action design confuses agents.""",
    "faq": [
        {"question": "Do agentic websites replace normal websites?",
         "answer": "No. An agentic website is a normal website with extra layers for software agents: structured content, defined actions and clear permissions. People still browse it as usual. The agent layer simply lets assistants read and act on the same pages without scraping or guessing."},
        {"question": "Is an agentic website secure?",
         "answer": "It can be, if actions are designed carefully. Start with low-risk actions, require authentication where data is involved, rate-limit requests and log every call. Keep anything contractual or financial behind a human approval step until you trust how agents use the site."},
        {"question": "Do I need to rebuild my site to make it agentic?",
         "answer": "Usually not. Most teams start by fixing structure, adding structured data and rewriting key pages answer-first. Actions can then be added one at a time, beginning with demo booking or pricing requests, without replacing the CMS or the design."},
    ],
    "key_takeaways": [
        "Agentic websites serve AI agents as well as people.",
        "Machine-readable content, actions and permissions are the three building blocks.",
        "Start with structure and schema, then add a few low-risk actions.",
        "Measure agent sessions, completed actions and pipeline.",
    ],
    "cta": "See how Relay structures your pages for AI answers. Book a 20-minute walkthrough.",
}
agentic_bad = dict(agentic_ok)
agentic_bad.update({
    "meta_description": "Agentic websites explained for B2B teams.",
    "intro": "Over the last few years, the way B2B buyers research software has changed a great deal, and this is a game-changer for marketers. "
             "Instead of only searching and clicking, buyers now ask assistants to do the work. An agentic website is built so AI agents can read it and complete tasks on it, such as comparing plans or booking a demo, not just display pages to people.",
    "body_markdown": agentic_ok["body_markdown"].replace("/features/actions", "/blog/agentic-web-guide"),
    "faq": agentic_ok["faq"][:2] + [{"question": "Do I need to rebuild my site", "answer": "Usually not."}],
})
dump("article_draft/agentic-website.attempt0.json", agentic_bad)
dump("article_draft/agentic-website.attempt1.json", agentic_ok)
print("fixtures written to", F)
