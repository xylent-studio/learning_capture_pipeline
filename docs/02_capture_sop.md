# Capture SOP

## Before each capture

1. Confirm the course/report is in authorized scope.
2. Confirm the operator is using the approved capture account.
3. Confirm browser zoom is 100% and viewport is fixed, preferably 1920x1080 or higher.
4. Confirm audio routing works.
5. Record a 10-second test clip and verify sound.
6. Create a capture session with course title, URL, brand, jurisdiction, and notes.
7. Start screen/audio recording.

## During course capture

1. Capture the course overview page.
2. Slowly scroll the overview top to bottom.
3. Capture lesson list and module titles.
4. Enter lesson 1.
5. For video/audio, play at normal speed and avoid skipping.
6. If captions are available, enable them when they do not obscure key content.
7. For static pages, scroll slowly and pause at each section.
8. Capture quizzes, feedback, knowledge checks, and completion screens.
9. Add operator notes for ambiguous states, missing audio, dynamic interactions, or things needing human review.
10. Repeat for every lesson.

## After capture

1. Stop recording.
2. Save artifacts to the capture session folder.
3. Generate initial QA report.
4. Mark missing sections, audio problems, low OCR confidence, PII issues, or recapture needs.
5. Send the session to processing.

## Quality standards

- Audio must be audible and transcribable.
- Text should be readable in screenshots.
- Every lesson should have a visible title and source timestamp.
- Long static pages should have enough screenshots for OCR coverage.
- Quizzes and feedback should be captured if allowed by internal rules.
- Employee names and sensitive data should not be captured unless specifically required and controlled.

## Reports

For completion/certification/performance reports:

- Prefer UI-visible CSV/export buttons when available.
- If no export exists, screen capture and OCR are fallback methods.
- Treat learner/report data as analytics data, not training content.
- Do not put raw employee names into embeddings.
- Hash or map employees to internal IDs before analysis.
