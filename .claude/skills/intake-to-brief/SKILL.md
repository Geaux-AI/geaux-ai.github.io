---
name: intake-to-brief
description: "Turn a raw Geaux AI intake into a solution. Use whenever the user pastes a Google Form submission, an intake response, a row from the 'Geaux AI- Intake' sheet, or messy question-and-answer text and wants a recommendation. Triggers include 'run the orchestrator on this', 'here's a submission', 'new intake', pasted form responses, or any jumbled name/email/problem block from the contact form. It cleans the raw paste into a structured problem brief, then routes it through the orchestrator for a best-fit solution."
---

# Intake to Brief

Take a raw, messy Geaux AI form submission and turn it into a clean problem brief, then run it through the orchestrator to produce a solution. The person pasting it should not have to format anything — that's this skill's job.

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

## Step 3 — Route it through the orchestrator

Hand the Problem Brief to the orchestrator flow (see `.claude/commands/orchestrator.md`): restate it, route to the owning seat(s), collect each Solution Card, and synthesize one recommendation. Keep the Geaux AI rule in mind — this is a service, so recommend the **simplest** fix that solves it, not the fanciest. Not everyone needs an agent.

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
