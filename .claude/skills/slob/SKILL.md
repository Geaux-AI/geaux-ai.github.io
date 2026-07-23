---
name: slob
description: "Turn raw messy intake ('slob') into a solution. Use whenever the user pastes a Google Form submission, an intake response, a row from the 'Geaux AI- Intake' sheet, or any jumbled question-and-answer text and wants a recommendation. Triggers include 'slob', 'run the orchestrator on this', 'here's a submission', 'new intake', pasted form responses, or any messy name/email/problem block from the contact form. It cleans the paste into a structured brief, then fires the orchestrator, which spins up the specialist subagents and returns a best-fit solution."
---

# Slob

Take a raw, messy Geaux AI form submission (the "slob") and turn it into a clean problem brief, then run it through the orchestrator — which spins up the specialist subagents — to produce a solution. The person pasting it should not have to format anything. That's this skill's job.

## When this fires

The user pastes anything that came out of the Geaux AI intake: a Google Form individual response, a copied spreadsheet row (tab-separated), or a jumble of questions and answers. It may be incomplete or messy. Do not ask them to reformat it.

## Step 1 — Normalize the paste into a brief

Read the raw text and map it onto these fields. The form asks nine questions; match answers to them even if labels are missing, out of order, or tab-separated. If a field is absent, mark it "not given" — never invent one.

- **Name**
- **Email**
- **What they do** (business, role, or project)
- **The problem** (the task that eats their time)
- **Frequency & time cost** (how often, how long each time)
- **What "solved" looks like**
- **Tools they use today**
- **Areas it touches** (building/tech, design, marketing, social, finance, operations, legal, not sure)
- **Hard constraints** (deadline, budget, private/sensitive data)

Then write a short, clean **Problem Brief** — three or four plain sentences that state who they are, what hurts, how often, and what a win looks like. No jargon, no em-dashes. This is the description the orchestrator works from.

## Step 2 — Check for gaps before routing

If the two fields that matter most — **the problem** and **what "solved" looks like** — are thin or missing, ask the user at most two quick questions to fill them. If the brief is solid, skip straight to Step 3. Do not stall a good submission with unnecessary questions.

## Step 3 — Fire the orchestrator and spin up the subagents

Run the orchestration flow (`.claude/commands/orchestrator.md`) **at the top level yourself** — only the top-level session can spawn subagents, so do not delegate this step to another agent.

1. **Restate** the problem from the Brief in one or two lines.
2. **Route** it to the owning seat(s): `developers`, `designers`, `marketing`, `social-media`, `finance`, `small-business`, `legal`. Pick only the seats the problem actually touches — usually one or two. Do not wake all seven by reflex.
3. **Spawn** each needed seat with the Agent tool, giving it only its slice of the Brief, and collect its Solution Card.
4. **Synthesize** the cards into one recommendation with a single best-fit shape.

Keep the Geaux AI rule in mind: this is a service, so recommend the **simplest** fix that solves it, not the fanciest. If the problem is small enough that no subagent is needed, say so and answer it directly. Not everyone needs an agent, and not every intake needs the whole team.

## Step 4 — Return the solution in this shape

Give the user back one tidy block they can act on or forward to the client:

- **Problem** (one line)
- **Best-fit shape** — agent / subagent / workflow / MCP server / connector / no build needed
- **Why** (2–3 plain sentences, no jargon, no dashes)
- **What to build** (concrete steps)
- **Who builds it** (which seat)
- **Effort vs payoff** (rough size, what they get)
- **First reply to the client** (3–4 sentences they could send as-is)

## Rules

- Never lose or distort what they wrote. If something is ambiguous, quote their words rather than guessing.
- Keep every output free of em-dashes, filler triads, and jargon. It should read like a person wrote it.
- Be honest when little or no AI is needed. Undersell before you oversell.
