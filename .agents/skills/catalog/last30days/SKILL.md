---
name: last30days
description: Research what changed or mattered in the last 30 days using dated public sources. Use for recent-trend, current-discussion, release, adoption, or "what happened lately" questions where freshness and source dates matter. Do not use for timeless background research.
---

# Last 30 Days

Produce a concise, source-backed view of the rolling 30-day window without bypassing access controls or collecting browser credentials.

## Project-safe workflow

1. State the exact start and end dates for the window. If the user supplies an `as of` date, anchor the window to it.
2. Define the few source facets that can answer the question. Prefer official releases, project repositories, standards bodies, papers, and first-party announcements. Add public community discussion only when sentiment or lived experience is part of the question.
3. Follow `web-research-routing`: use SearXNG for compact URL discovery and Crawl4AI to read known public pages. Use native web tools only when those project services are unavailable.
4. Record both publication date and event date when they differ. Exclude undated claims from the time-bounded conclusion.
5. Deduplicate syndicated stories and copied posts. Treat one underlying announcement as one item.
6. Separate verified facts, recurring opinions, disagreements, and inference. Weight primary evidence above popularity.
7. Stop when additional searches repeat known claims or the useful source facets are covered.

## Safety and access

- Never read browser profiles, cookies, local credential stores, `.env`, SSH material, or unrelated user files.
- Never route around CAPTCHAs, login walls, robots controls, rate limits, or platform restrictions.
- Do not install CLIs, packages, or hosted connectors without explicit permission.
- Do not send private repository content to public search or retrieval services.

## Output

Give the answer first, then:

- notable developments with exact dates;
- where sources agree or disagree;
- what appears important versus merely popular;
- material coverage gaps or uncertainty;
- direct links beside the claims they support.

Adapted from `mvanhorn/last30days-skill` for this repository's SearXNG/Crawl4AI and credential-safety policy.
