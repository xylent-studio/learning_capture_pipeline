---
name: authorized-screen-capture
description: Use when building or modifying human-guided or headed-browser capture workflows for authorized SeedTalent screen/audio/screenshot capture. Do not use for backend scraping, hidden API extraction, or credential automation.
---

# Authorized screen capture skill

## Purpose

Help Codex build normal-user browser capture workflows for the State of Mind SeedTalent project.

## Use when

- creating capture CLI commands
- creating Playwright headed browser capture
- recording URL/title/page events
- adding screenshot interval capture
- integrating OBS or FFmpeg wrappers
- creating fake HTML course fixtures

## Rules

- Do not inspect network traffic.
- Do not call hidden APIs.
- Do not automate SeedTalent login using production secrets.
- Persist any browser storage state outside the repo.
- Use fake local HTML fixtures for tests.
- Keep screen/audio capture artifacts out of git.
- Preserve timestamps, URLs, page titles, and operator notes.
- Every capture session must reference a permission basis.

## Done checklist

- tests use fake fixtures only
- no credentials committed
- no real SeedTalent content committed
- artifacts are ignored by git
- session metadata is sufficient for reconstruction
