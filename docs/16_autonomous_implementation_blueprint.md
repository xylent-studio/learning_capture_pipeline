# 16 Autonomous Implementation Blueprint

## Build order

1. Permission manifest loader.
2. Auth preflight with persisted storage state.
3. Local fake SeedTalent-like course fixture.
4. Page observation model.
5. Page classifier.
6. Course discovery from visible UI.
7. Course inventory.
8. Course capture planner.
9. Recorder abstraction.
10. Playwright autopilot runner.
11. Static page capture.
12. Video/audio page capture.
13. Quiz capture controller.
14. Report/export capture controller.
15. QA scoring and recapture queue.
16. Processing pipeline.
17. Review/search/training generation.

## Fake fixture first

Before touching real SeedTalent, build a local HTML fixture that mimics course flows:

- catalog page,
- course overview,
- lesson list,
- static lesson,
- video lesson using a small fake media element or mocked player,
- quiz page,
- feedback page,
- completion page,
- report table.

The full autonomous runner should pass against this fixture.

## Visible DOM extraction

For each page:

- extract `document.title`,
- extract visible body text,
- extract visible buttons/links/forms,
- extract visible tables,
- identify likely course/lesson titles,
- identify media controls,
- save screenshot.

This is not backend scraping. It is browser-state capture from the approved user session.

## Static lesson capture

Actions:

1. full-page screenshot,
2. visible DOM text extraction,
3. scroll viewport by viewport,
4. screenshot at each stop,
5. OCR screenshots,
6. next when bottom reached and content is stable.

## Video/audio lesson capture

Actions:

1. screenshot before play,
2. start recorder before content,
3. press visible play button,
4. monitor audio signal,
5. monitor visible player state and/or media element progress,
6. screenshot periodically,
7. wait until video ends or Next becomes enabled,
8. capture final frame,
9. advance.

## Quiz capture

Actions:

1. screenshot question,
2. capture visible DOM question/options,
3. apply configured quiz mode,
4. submit,
5. capture feedback,
6. retry only if policy allows,
7. advance.

Recommended MVP quiz mode:

```text
capture_and_complete_on_capture_account
```

The capture account should be isolated from production employee certification/reporting wherever possible.

## Reports

Prefer visible UI export buttons when present. Otherwise:

- screenshot,
- visible DOM table extraction,
- OCR fallback,
- store learner/report analytics separately from training content,
- hash employee identifiers before analytics,
- never embed raw employee names into the training knowledge base.

## Scheduler

A scheduled batch should:

- run auth preflight,
- capture one course at a time by default,
- respect rate limits,
- pause between courses,
- write run logs,
- stop on repeated auth failures,
- queue recaptures,
- produce batch summary.
