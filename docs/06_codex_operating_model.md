# Codex operating model

## Roles

Human product owner:

- defines scope
- confirms permission boundaries
- chooses priorities
- reviews generated training policy

Codex:

- writes code
- writes tests
- drafts docs
- reviews diffs
- suggests safer designs
- turns repeated workflows into skills

Human reviewer:

- reviews PRs
- approves content governance rules
- approves generated training before publishing

## Recommended Codex workflow

1. Keep `AGENTS.md` current.
2. Use one branch per ticket.
3. Start complex tasks in Plan mode.
4. Ask Codex to restate constraints before coding.
5. Require tests and a self-review.
6. Use `/review` or a separate Codex task before merging.
7. Promote repeated prompts into `.agents/skills`.
8. Promote repeated live-debug findings into one of the canonical truth surfaces instead of leaving them in ad hoc notes:
   - repo findings docs for durable patterns
   - runtime-generated digests for latest live truth
   - `_intel` checkpoints for continuity
   - run manifests for execution truth

## Prompt structure

```text
Goal: ...
Context: ...
Constraints: ...
Done when: ...
```

## First Codex task

Use `prompts/00_codex_bootstrap_prompt.md`.

## Parallelization

Safe parallel tracks:

- data schema + migrations
- capture CLI
- fake HTML fixture
- recorder abstraction
- OCR/transcription provider interfaces
- docs and SOPs

Do not run multiple live Codex threads editing the same files unless using worktrees.

## Review policy

Before merge, require Codex to answer:

- Did this task add any path for unauthorized scraping?
- Are credentials excluded?
- Are real data/PII excluded?
- Are source citations preserved?
- Do outputs default to `needs_review`?
- What tests were run?

## Live pilot continuity rule

When a live SeedTalent debugging session teaches a reusable UI truth, do not leave that learning only in chat or a one-off file. Promote it into:

1. [20_live_seedtalent_findings.md](/C:/dev/Learning%20Capture%20Pipeline/docs/20_live_seedtalent_findings.md) if it is a durable real-UI pattern.
2. The runtime live findings digest if it is current run truth.
3. `_intel` if it changes the next re-entry path.
