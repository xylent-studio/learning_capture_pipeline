# Agent Truth Map

Owner/source of truth: manually maintained repo doc for agent re-entry conventions  
Refresh trigger: when a canonical truth surface is added, replaced, or removed  
Maintenance mode: manual  
Last validated against live SeedTalent: 2026-04-24

## Purpose

Future agents should not rediscover where project truth lives. This file is the canonical map.

## Where Truth Lives

1. Repo docs
   Durable patterns and operating rules live in repo-tracked docs such as:
   - [20_live_seedtalent_findings.md](/C:/dev/Learning%20Capture%20Pipeline/docs/20_live_seedtalent_findings.md)
   - [19_runbook_first_autonomous_pilot.md](/C:/dev/Learning%20Capture%20Pipeline/docs/19_runbook_first_autonomous_pilot.md)
   - [06_codex_operating_model.md](/C:/dev/Learning%20Capture%20Pipeline/docs/06_codex_operating_model.md)

2. Runtime digest
   The latest live pilot truth lives outside git in the generated digest:
   - `C:\dev\_secrets\learning-capture-pipeline\outputs\live-findings-digest.json`
   This is the first runtime file to inspect for live-pilot work after re-entry.

3. `_intel` checkpoint
   Continuity and re-entry state live in:
   - `C:\dev\_intel\ops\local-machine-ops\checkpoints\learning-capture-pipeline\latest.md`
   This should tell the next agent what changed, what is blocked, and what evidence matters.

4. Run manifest
   The current execution truth for a specific run lives in that run's `run-manifest.json`.
   This is the authoritative source for:
   - lifecycle status
   - attempts
   - blocker category
   - diagnostics
   - evidence paths

## Prohibited Knowledge Sprawl

- Do not create ad hoc note files when one of the canonical surfaces above already owns that knowledge.
- Do not create multiple narrative docs for the same live findings.
- Do not keep static selector notes in docs that will drift from code.
- If a new surface is added, it must declare owner, refresh trigger, and whether it is manual or generated.

## Agent Re-entry Order

1. Run repo rehydration.
2. Read the latest `_intel` checkpoint.
3. Read the runtime live findings digest if the task touches live SeedTalent work.
4. Read the active run manifest for the current course or batch.
5. Read the canonical repo findings doc only for durable patterns, not for run-specific status.
