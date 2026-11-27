# How we build with agents in this repo

A plain-language guide to the Matt Pocock skills set up here. Type `/ask-matt` any time you're not sure which skill fits.

## Where things are written down

| What | Where | Who writes it |
|---|---|---|
| Domain words (Owner, Franchise, Week...) | `GLOSSARY.md` | `/grill-with-docs`, `/domain-modeling` |
| Decisions and why | `docs/adr/NNNN-slug.md` | `/grill-with-docs`, `/domain-modeling` |
| Specs and tickets | GitHub Issues | `/to-spec`, `/to-tickets` |
| Rules every agent follows | `AGENTS.md` (`CLAUDE.md` just imports it) | you, `/retro` |
| How skills find the above | `docs/agents/*.md` | `/setup-matt-pocock-skills` |

An ADR gets written only when a decision is **hard to reverse**, **surprising without context**, and **a real trade-off**. ADRs 0001–0007 record what has been decided so far (0004 is partly superseded by 0006).

## The main flow, for a new feature

1. **`/grill-with-docs`**: the agent questions you about the idea until it's sharp. New terms go into `GLOSSARY.md` and decisions into ADRs as you go.
2. **`/to-spec`**: turns that conversation into a spec issue on GitHub.
3. **`/to-tickets`**: splits the spec into small tickets (issues), each saying which tickets block it.
4. **`/implement`** on one ticket, then `/clear`, then the next ticket. It builds test-first (`/tdd`) and finishes with `/code-review`.
   - Or **`/implement-spec`** to have it run every ticket in parallel on one branch.
5. **`/retro`**: after the build, it suggests changes to `AGENTS.md`, checks or tooling so the next build goes better.

Keep steps 1–3 in **one session** without clearing, so the spec builds on the full conversation.

For small changes, skip steps 2–3: `/grill-with-docs` then `/implement` in the same session.

## Other entry points

- **`/wayfinder`**: for huge, foggy efforts (like "the whole frontend"). It maps open questions as GitHub issues and resolves them one by one, then hands off to `/to-spec`.
- **`/diagnosing-bugs`**: when something's broken. It builds a command that reproduces the bug before fixing anything.
- **`/triage`**: for issues you didn't write yourself. Not needed for tickets from `/to-tickets`.
- **`/prototype`**: throwaway code to answer a question you can't settle by talking.
- **`/improve-codebase-architecture`**: periodic cleanup survey.

## Triage labels (on GitHub)

`needs-triage` → `needs-info` (waiting on someone) → `ready-for-agent` (an agent can do it unattended) or `ready-for-human` → `wontfix`.

## Picking up in a new session

A new session starts with no memory of earlier ones. Everything it needs is in the repo:

- `AGENTS.md`: the rules, layout and commands.
- `docs/GAMEPLAN.md`: the status table, v1 scope and the "Later" roadmap.
- GitHub Issues: what's open and what blocks what (`gh issue list --repo tjdavis2112/washingwood`).
- `docs/guides/`: how to build, deploy and test.

Before building, check the local setup:
- Docker Desktop is running (the Postgres-backed tests and the build need it).
- The `washingwood-pg` container is up, and `.env` has `WASHINGWOOD_PG`.
- For deploys, Wrangler is still logged in: `npx wrangler whoami` in `site/`.

To start the next feature, open a fresh session and run `/grill-with-docs` on one item from GAMEPLAN's "Later" list (for example the Owners hub). Then `/to-spec`, `/to-tickets`, and `/implement` per ticket, as above.
