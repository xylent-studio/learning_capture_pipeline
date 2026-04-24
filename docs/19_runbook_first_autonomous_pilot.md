# 19 Runbook: First Autonomous Pilot

## Goal

Prove autonomous capture on a small set of SeedTalent courses.

## Scope

- one dedicated capture account,
- one capture station,
- one browser profile,
- one recorder profile,
- three to ten courses,
- capture at 1080p,
- screenshot interval 3-5 seconds,
- visible DOM extraction on every page,
- QA report after every course.

## Steps

1. Replace `config/permission_manifest.example.yaml` with real internal permission metadata.
2. Create `.secrets/playwright/` outside git.
3. Run auth bootstrap and save storage state.
4. Run auth preflight.
5. Run catalog discovery.
6. Review course inventory.
7. Generate capture plans.
8. Run one course capture.
9. Review QA report.
10. Tune selectors/state classifier.
11. Run the remaining pilot courses.
12. Process transcript/OCR.
13. Reconstruct lessons.
14. Generate draft internal modules.
15. Review outputs and recapture failures.

## Pilot success criteria

- bot captures at least 80 percent of selected courses without manual intervention,
- every successful course has screen recording, audio, screenshots, visible DOM text, and QA report,
- videos are captured to completion,
- static lessons are fully scrolled/captured,
- quizzes are captured according to policy,
- QA failures create actionable recapture records,
- generated chunks cite screenshots/timestamps,
- no credentials or real content enter the repo.
