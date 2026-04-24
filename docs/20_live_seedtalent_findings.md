# Live SeedTalent Findings

Owner/source of truth: manually maintained repo doc for durable real-UI patterns  
Refresh trigger: after a live pilot run confirms or invalidates one of these patterns  
Maintenance mode: manual  
Last validated against live SeedTalent: 2026-04-24

## Purpose

This document stores normalized live UI truths that future agents and operators should reuse. It is not a run log and it must not contain course-specific proprietary lesson content beyond what is necessary to describe visible UI behavior.

## Canonical Findings

1. Auth sampled too early can look expired even when the stored session is still valid.
2. Outer shell readiness is different from SCORM content readiness.
3. Real course content usually lives inside the visible SCORM frame rather than the outer SeedTalent shell.
4. Lesson interaction gates can block progression even after the correct page is loaded.
5. Checkbox-based lesson gates may require clicking the visible label wrapper rather than the raw checkbox input.
6. Quiz flow is not one state. It has at least intro, question, results, and exit/continue phases.
7. Hidden or low-value skip controls can be visible to automation and must not outrank visible progression controls like `Next`, `Continue`, or `Submit`.

## Real State Taxonomy

- `course_shell_loading`: the outer SeedTalent shell is present, but meaningful course content is not yet ready.
- `scorm_frame_loading`: the SCORM content frame exists, but the visible lesson or quiz content is still loading.
- `course_overview`: the course intro/overview is ready and the course can be started.
- `lesson_list`: the lesson menu or ordered progression screen is visible.
- `lesson_interaction_gate`: the lesson requires visible interaction before progression.
- `lesson_static_text`: readable lesson content with normal next-step progression.
- `lesson_video` / `lesson_audio`: media-first lesson content.
- `quiz_intro`: visible quiz start state before the actual question flow begins.
- `quiz_question`: visible question state with answer submission controls.
- `quiz_results`: visible score/results state that still requires progression to completion.
- `completion_page`: visible course completion state.

## Current Highest-Value Blocker

The current live blocker is the quiz-results exit transition. The runner now reaches the visible results state, but it still needs stable handling for the next-step action after score/results are shown.

## Design Rules That Follow

- Prefer the active visible capture surface over the outer URL when diagnosing failures.
- Treat shell-vs-frame as first-class diagnostic data, not a guess.
- Do not encode brittle selector lists in docs. Keep exact selector priority in code and generated diagnostics.
- When a new live pattern repeats across runs, promote it into page taxonomy, diagnostics, or a skill rather than a one-off note.
