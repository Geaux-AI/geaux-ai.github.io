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

## Delivery workflow (every client engagement)

Every solution built for someone follows this pipeline.

**The hard rule: nothing is *published* — merged to `main`, added to the public showcase, or presented as finished — until it is proven to work AND the client has accepted it.** A broken or unproven result on the public site is the single thing to avoid. Work living on a branch is fine; "not on `main`/showcase" means "not published," and that's the safe state.

1. **Build** on a working branch. Branch visibility doesn't matter.
2. **Prove it works.** Validate end-to-end (run it, or test against a sandbox) before calling it done.
3. **Client review.** Share privately with the client; iterate until they explicitly accept.
4. **On acceptance — produce BOTH outputs:**
   - **Hand off to the client (they own it completely):** a fresh repo that is theirs **and** a downloadable zip of the deliverable.
   - **Keep the public showcase copy:** add the finished solution to the portfolio/gallery on `geaux-ai.github.io` so it can be shown off and reused as a template for others.
5. Only step 4 (the showcase copy) touches `main`. Never publish earlier.

If asked to publish, showcase, or merge something that hasn't cleared steps 2–3, stop and flag it rather than proceeding.

## Leader rundown (end every solution with this)

At the end of **every** solution, close with a short **Leader Rundown** addressed to me (the leader), in this order:

1. **The problem** — restate what was actually being solved, in plain terms.
2. **What I did** — the work performed and who (which seats) did it.
3. **Why this is the best solution** — the reasoning behind the chosen approach and any tradeoffs weighed.

Keep it tight and skimmable. This runs on top of the normal Solution Brief — it's the leader-facing recap, not a replacement.
