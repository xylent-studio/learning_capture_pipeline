# Project brief

## What we are building

State of Mind needs a pipeline to capture video, audio, images, screenshots, visible text, reports, course structure, quiz content, and learning flow from SeedTalent, then transform that material into internal training.

SeedTalent has granted permission for screen capture but is not providing backend access or APIs. Therefore, the project is a governed capture and reconstruction system rather than a conventional integration.

## Why this matters

State of Mind wants an internal training intelligence layer that can answer questions, generate refreshers, build quizzes, support manager coaching, create roleplays, summarize product/brand knowledge, and connect training activity with operational outcomes.

## Core outcome

A reviewer-approved library of source-linked training chunks that can power:

- internal search
- RAG answers with citations
- draft training modules
- quizzes
- flashcards
- SOP checklists
- manager coaching guides
- budtender/customer roleplays
- compliance refreshers
- training analytics

## Primary constraint

Do not depend on SeedTalent backend cooperation. Use authorized screen/audio capture and normal UI access only.

## Safety/legal posture

The pipeline must preserve a clean boundary:

- We capture authorized user-visible training experiences.
- We do not reverse engineer or extract SeedTalent software.
- We do not probe hidden APIs.
- We do not store credentials in code.
- We do not publish generated training without human review.
