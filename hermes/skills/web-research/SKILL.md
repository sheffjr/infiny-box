---
name: web-research
description: Search the web, read pages: news, prices, docs, facts
triggers: search, google, look up, find online, news, latest, current, what is, who is, price of, поиск, найди, загугли, новости, актуальн, что такое, кто такой, сколько стоит
---

# Web Research (self-hosted, private)

You can search the web and read pages. Both run **inside this container** —
SearXNG for search, a real Chromium for reading. No cloud API, no key, no
tracking. This is Infiny's privacy stance.

## Non-negotiable acceptance criteria
- **Call `web_search`. Do not describe calling it.** Saying "I will search",
  "let me look that up", or "I used web-research" without an actual tool call
  is a false statement about the real world. If the answer did not come from a
  tool result in this conversation, it did not come from the web.
- Always search BEFORE answering questions about current or changing facts
  (news, prices, release dates, versions, "latest X"). Training data is stale
  by definition and you cannot tell how stale.
- Cite the source URL for every fact you got from the web.
- If a tool fails, report the error verbatim and stop. Never fill the gap
  from memory and never imply you searched when you did not.

## Tools
- `web_search {query, limit?}` — search via the local SearXNG; returns titles,
  URLs and snippets.
- `web_extract {urls}` — read those pages. A real headless Chromium renders
  JavaScript first, so weather widgets, SPAs and lazy-loaded pages come back as
  actual text rather than an empty shell.

Long pages are truncated for you and the full copy is kept on disk — when the
part you got is cut short, read the rest with `read_file` from the path in the
tool result instead of fetching the page again.

## Workflow: Search → Extract
1. `web_search` with a focused query (a few keywords, not a sentence).
2. Look at the results; pick the most relevant 1-2 URLs.
3. `web_extract` those URLs to read details.
4. Synthesize a concise answer WITH source links.

## Query tips
- Keep queries short (2-5 keywords). Add the year for current info.
- For docs/errors, search the exact error string or "<tool> <topic> docs".
- If first results are weak, refine keywords once — don't loop endlessly.

## Search is already running — there is nothing to start
SearXNG runs inside this container and is started automatically. There is no
Docker here and no compose file. Never run `docker compose up`, never tell the
user to start a web stack: both are leftovers from an older design and will
simply fail.

Some sites refuse automated readers outright — `web_extract` will say so. That
is a fact about that site, not permission to answer from memory: report it and
try a different source.

## Output
A concise answer with source URLs. Never dump raw page content — summarize.
