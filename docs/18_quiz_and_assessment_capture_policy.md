# 18 Quiz and Assessment Capture Policy

## Purpose

Courses may require knowledge checks or quizzes before completion. The autonomous bot must capture them consistently without polluting real employee training results.

## Recommended account policy

Use a dedicated capture account that is clearly separate from employees and excluded from operational training dashboards when possible.

## Quiz modes

### capture_only

Screenshot and extract the question/options, then stop before submit.

Use when assessments are sensitive or completion is not required.

### capture_and_complete_on_capture_account

Screenshot and extract the question/options, select an answer using configured strategy, submit, capture feedback, and proceed.

Use for the default autonomous MVP if the capture account is isolated.

### known_answer_bank

Use approved known answers from internal training ops.

Use after reviewers build an answer bank.

### model_assisted_answer

Use visible course content and captured lesson transcript/OCR to select the likely answer.

Use only on the capture account. Capture feedback and mark low-confidence items for review.

## Retry rule

Do not endlessly guess. Limit attempts per question. If repeated failure blocks completion, queue human exception.

## Output

Every quiz capture should store:

- question text,
- answer options,
- selected answer,
- feedback text,
- whether correct/incorrect if visible,
- screenshot,
- timestamp,
- course/lesson metadata,
- review status.
