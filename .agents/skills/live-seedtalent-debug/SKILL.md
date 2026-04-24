---
name: live-seedtalent-debug
description: Use when resuming or debugging the real SeedTalent live pilot. Focuses future agents on the canonical truth surfaces, current blocker chain, and real UI lessons already learned.
---

# Live SeedTalent debug skill

## Purpose

Help future agents resume live-pilot work quickly without rereading the full thread history or rediscovering the same real UI behavior.

## Use when

- debugging a real `execute-course` run
- resuming after interruption or machine restart
- inspecting live blocker categories
- tuning real SCORM frame or quiz progression behavior

## First inspection order

1. Read the current `_intel` checkpoint:
   - `C:\dev\_intel\ops\local-machine-ops\checkpoints\learning-capture-pipeline\latest.md`
2. Read the generated runtime digest:
   - `C:\dev\_secrets\learning-capture-pipeline\outputs\live-findings-digest.json`
3. Read the active run manifest for the current course.
4. Inspect the latest key screenshots referenced by the run manifest or digest.
5. Only then inspect the runner/classifier code if the blocker is still unclear.

## Known real UI lessons

- Auth can look expired if sampled before visible dashboard/course-shell stability.
- The active capture surface is usually the SCORM frame, not the outer page.
- Shell-ready and frame-ready are different states.
- Lesson interaction gates may require visible label clicks for checkbox completion.
- Quiz flow includes intro, question, results, and exit states.
- Hidden skip controls should not outrank visible progression controls.

## Do not do

- do not treat the outer page URL as the only truth
- do not add ad hoc notes when the digest, checkpoint, run manifest, or canonical findings doc can be updated instead
- do not automate login with production secrets
- do not inspect network traffic or hidden APIs

## Output expectation

When using this skill, report:
- current blocker category
- last observed page kind
- active capture surface
- best evidence files
- concrete next code change or runbook step
