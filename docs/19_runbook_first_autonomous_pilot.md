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

1. Copy the runtime config example and fill it with external local paths only.
2. Replace the external runtime manifest path with real internal permission metadata.
3. Create the external storage-state path under `C:\dev\_secrets\learning-capture-pipeline\playwright\`.
4. Run `som-capture pilot validate-config --config <runtime-config.yaml>`.
5. Run `som-capture pilot bootstrap-auth --config <runtime-config.yaml>`.
6. Perform the one-time headed login and save storage state.
7. Run `som-capture pilot auth-preflight --config <runtime-config.yaml> --headed`.
8. Run `som-capture pilot discovery --config <runtime-config.yaml> --headed`.
9. Review course inventory and write the approved courses file under the external secret root.
10. Run `som-capture pilot plans-from-approved --config <runtime-config.yaml>`.
11. Run `som-capture pilot run-course --config <runtime-config.yaml> --plan-bundle <plans.json>` to create the first live batch/run manifest set and confirm preflight readiness.
12. Review the run manifest, preflight output, QA placeholder, and any failure bundle under the external artifact root.
13. Tune selectors/state classifier if preflight or diagnostics show issues.
14. Run one real course capture once the live traversal slice exists.
15. Run `som-capture pilot run-batch --config <runtime-config.yaml> --plan-bundle <plans.json>` when batch-level preflight and one-course live execution are stable.
16. Process transcript/OCR.
17. Reconstruct lessons.
18. Generate draft internal modules.
19. Review outputs and recapture failures.

## Pilot success criteria

- bot captures at least 80 percent of selected courses without manual intervention,
- every successful course has screen recording, audio, screenshots, visible DOM text, and QA report,
- videos are captured to completion,
- static lessons are fully scrolled/captured,
- quizzes are captured according to policy,
- QA failures create actionable recapture records,
- generated chunks cite screenshots/timestamps,
- no credentials or real content enter the repo.
