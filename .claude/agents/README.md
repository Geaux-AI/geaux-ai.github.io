# The Team — subagents managed by the orchestrator

A personal team of Claude Code subagents, built from the "Build Your Whole Team with Claude — 42 Skills" org chart (7 departments), and personalized for one job: **helping anyone who brings a problem land on the right solution shape — an agent, a subagent, a simple workflow, an MCP server, or a connector.**

The **orchestrator** is the manager. You bring it a request; it splits the request into slices, routes each slice to the department that owns it, collects each specialist's Solution Card, and synthesizes one Solution Brief with a single recommended shape.

## Roster

| Sub-agent | Role | Model | Tools | Mode |
|---|---|---|---|---|
| `orchestrator` | Manager: intake → route → delegate → synthesize | **opus** | Read, Grep, Glob, WebSearch, WebFetch, TodoWrite | see + coordinate |
| `developers` | Build agents, subagents, skills, MCP servers, code, tests | **opus** | Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch | do |
| `legal` | Contract/NDA review, policies, compliance | **opus** | Read, Grep, Glob, WebSearch, WebFetch, Write, Edit | see + draft |
| `designers` | UI/UX, brand, frontend, motion, web artifacts | **sonnet** | Read, Write, Edit, Grep, Glob, WebSearch, WebFetch | do |
| `marketing` | Copywriting, SEO, lead magnets, campaigns | **sonnet** | Read, Write, Edit, Grep, Glob, WebSearch, WebFetch | do |
| `finance` | Statements, reconciliation, budgets, audits | **sonnet** | Read, Write, Edit, Bash, Grep, Glob | see + do |
| `small-business` | Cash flow, payroll, invoicing, operations | **sonnet** | Read, Write, Edit, Bash, Grep, Glob, WebFetch | do |
| `social-media` | Posts, Reels, thumbnails, calendars | **haiku** | Read, Write, Edit, WebSearch, WebFetch | do |

## Why these models

- **opus** goes to the seats where a wrong answer is expensive or the reasoning is deep: the manager's decomposition/synthesis, engineering builds, and legal review.
- **sonnet** goes to the craft-and-accuracy seats — design, marketing, finance, ops — where it's the best balance of quality and cost.
- **haiku** goes to social media: short, high-volume content where speed and cost win.

## Why these tools ("see vs. do")

Each seat only gets the tools its job needs:

- **See / advise** seats (orchestrator, and the review side of legal/finance) lean on read + search tools — `Read, Grep, Glob, WebSearch, WebFetch` — and don't get write access they wouldn't use.
- **Do / build** seats (developers, designers, marketing, social, ops) get `Write`/`Edit` to produce artifacts. `Bash` is added only where execution is needed — engineering, finance calcs, ops scripts. The orchestrator has **no** `Write`/`Bash`: a manager coordinates, it doesn't build.

## The five solution shapes

Every recommendation resolves to one (or a small combo) of these:

- **Agent** — a standalone Claude persona that owns a whole role.
- **Subagent** — a specialist the orchestrator delegates one slice to (like every seat here).
- **Workflow** — a repeatable packaged procedure: a skill, slash command, or documented process.
- **MCP server** — a custom tool for a system with no off-the-shelf integration.
- **Connector** — a hosted integration to a common SaaS tool (Gmail, Drive, GitHub, Slack…).

## How to use it

Talk to the orchestrator first:

> "Use the orchestrator — my org spends hours every week chasing dues and I don't know what to build."

It routes to `finance` + `small-business`, collects their cards, and hands you a Solution Brief that names the shape (e.g. "a workflow + a Stripe connector"), the build plan, the skills to install, and rough effort vs. payoff.

You can also call any specialist directly when you already know the seat.

## Installable skills behind each seat

- **Developers** — Superpowers, Context7, Skill Creator, MCP Builder, Webapp Testing, Claude-Mem
- **Designers** — UI UX Pro Max, Taste, Frontend Design, Transitions, Web Artifacts, Brand Guidelines
- **Marketing** — 45 marketing skills → github.com/coreyhaines31/marketingskills
- **Social Media** — 17 social skills → github.com/charlie947/social-media-skills
- **Finance** — 8 finance skills → claude.com/plugins/finance
- **Small Business** — 31 ops skills → claude.com/plugins/small-business
- **Legal** — 9 legal skills → claude.com/plugins/legal

Each seat's file lists its own skill links. Recommendations always cite real, installable skills.

## Scope & making it global

These live in `.claude/agents/` in this repo, so they load whenever Claude Code runs here and travel with the repo. To use the team everywhere, copy the files into `~/.claude/agents/`.

> Note: this team **replaces** the previous GEAUX 4D officer skills (orchestrator, president-router, architect, compliance, developer, events, membership, secretary, treasurer). Those were global skills under `~/.claude/skills/`; if any copy still exists in your permanent config, delete those folders to fully retire the old team.
