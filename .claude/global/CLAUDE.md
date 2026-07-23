# My team — global config

I run a personal team of subagents managed by an orchestrator. This is available in every session.

## Orchestrator trigger

When I say **"use the orchestrator"** or run **`/orchestrator`**, run the orchestration flow at the top level yourself (only the top-level session can spawn subagents):

1. Restate the problem in one short paragraph.
2. Route it to the owning seat(s): `developers`, `designers`, `marketing`, `social-media`, `finance`, `small-business`, `legal`.
3. Spawn each needed subagent with the Agent tool, giving it only its slice. Seats do the work directly (build mode); they return a Solution Card only when asked to advise.
4. Synthesize the results into one recommendation with a single shape: **agent / subagent / workflow / MCP server / connector**.

You do the delegating and the final synthesis. Don't solve it yourself before routing.
