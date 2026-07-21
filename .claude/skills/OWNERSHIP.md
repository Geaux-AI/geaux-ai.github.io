# Skill ownership — which seat owns which installed skill

Every skill in this folder is invocable by whichever subagent owns it (each owner carries the `Skill` tool). Claude Code does not scope skills per-agent at the framework level, so this file is the source of truth for ownership. Skills auto-trigger by their descriptions; owners invoke them deliberately.

## developers (38 skills)

- `babysit`
- `brainstorming`
- `cloud-sync`
- `context7-cli`
- `context7-mcp`
- `design-is`
- `dispatching-parallel-agents`
- `do`
- `executing-plans`
- `find-docs`
- `finishing-a-development-branch`
- `how-it-works`
- `knowledge-agent`
- `learn-codebase`
- `make-plan`
- `mcp-builder`
- `mem-search`
- `oh-my-issues`
- `pathfinder`
- `receiving-code-review`
- `requesting-code-review`
- `skill-creator`
- `smart-explore`
- `standup`
- `subagent-driven-development`
- `systematic-debugging`
- `test-driven-development`
- `timeline-report`
- `using-git-worktrees`
- `using-superpowers`
- `verification-before-completion`
- `version-bump`
- `webapp-testing`
- `weekly-digests`
- `what-the`
- `wowerpoint`
- `writing-plans`
- `writing-skills`

## designers (7 skills)

- `brand-guidelines`
- `frontend-design`
- `taste-skill`
- `transitions-dev`
- `transitions-polish`
- `ui-ux-pro-max`
- `web-artifacts-builder`

## marketing (47 skills)

- `ab-testing`
- `ad-creative`
- `ads`
- `ai-seo`
- `analytics`
- `aso`
- `churn-prevention`
- `co-marketing`
- `cold-email`
- `community-marketing`
- `competitor-profiling`
- `competitors`
- `content-strategy`
- `copy-editing`
- `copywriting`
- `cro`
- `customer-research`
- `directory-submissions`
- `emails`
- `free-tools`
- `image`
- `launch`
- `lead-magnets`
- `marketing-council`
- `marketing-ideas`
- `marketing-loops`
- `marketing-plan`
- `marketing-psychology`
- `offers`
- `onboarding`
- `paywalls`
- `popups`
- `pricing`
- `product-marketing`
- `programmatic-seo`
- `prospecting`
- `public-relations`
- `referrals`
- `revops`
- `sales-enablement`
- `schema`
- `seo-audit`
- `signup`
- `site-architecture`
- `sms`
- `social`
- `video`

## social-media (17 skills)

- `analytics-dashboard`
- `content-matrix`
- `gemini-carousel`
- `gemini-infographic`
- `graphic-designer`
- `hook-generator`
- `newsletter-voice`
- `niche-research`
- `pinned-comment`
- `post-formatter`
- `post-scorer`
- `post-writer`
- `profile-optimizer`
- `quote-post`
- `reels-scripting`
- `voice-builder`
- `youtube-thumbnail`

## finance (plugin — enabled)

Not in this folder; from the `finance` plugin (knowledge-work-plugins marketplace), account-level:
- `/finance:reconciliation`, `/finance:journal-entry`, `/finance:income-statement`, `/finance:variance-analysis`, `/finance:sox-testing`, `finance:close-management`

## legal (plugin — enabled)

Not in this folder; from the `legal` plugin (knowledge-work-plugins marketplace), account-level:
- `/legal:review-contract`, `/legal:triage-nda`, `/legal:vendor-check`, `/legal:brief`, `legal:legal-risk-assessment`

## small-business (plugin — available, not yet enabled)

Not in this folder; the `small-business` plugin (knowledge-work-plugins marketplace) is available but must be enabled from the plugin catalog to activate.

## orchestrator

Owns no skills by design — it routes to the seats above and synthesizes their output.
