# CLAUDE.md — Geaux AI

Static single-page site (`index.html`), no build step. Push to `main` to deploy via GitHub Pages.

## The team

This project ships a team of subagents in `.claude/agents/`, managed by an orchestrator, with department skills in `.claude/skills/`. See `.claude/agents/README.md` for the full roster, models, and tools.

## Orchestrator trigger

When the user says **"use the orchestrator"** or runs **`/orchestrator`**, run the orchestration flow (defined in `.claude/commands/orchestrator.md`) **at the top level yourself** — because only the top-level session can spawn subagents:

1. Restate the problem.
2. Route it to the owning seat(s): `developers`, `designers`, `marketing`, `social-media`, `finance`, `small-business`, `legal`.
3. Spawn each needed subagent with the Agent tool, giving it only its slice, and collect its Solution Card.
4. Synthesize the cards into one Solution Brief with a single recommended shape: **agent / subagent / workflow / MCP server / connector**.

You do the delegating and the final synthesis; the seats do the specialist work. Don't solve it yourself before routing.
