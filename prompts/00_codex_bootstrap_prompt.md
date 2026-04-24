# Codex bootstrap prompt

Use this as the first Codex task in the new repo.

```text
Goal: Read the repo context and turn this scaffold into a working first slice of the State of Mind SeedTalent authorized screen-capture pipeline.

Context:
- AGENTS.md
- README.md
- docs/00_project_brief.md
- docs/01_architecture.md
- docs/02_capture_sop.md
- docs/03_governance_policy.md
- docs/04_data_model.md
- src/som_seedtalent_capture/models.py
- src/som_seedtalent_capture/cli.py
- migrations/001_initial_capture_schema.sql

Constraints:
- SeedTalent has permitted screen capture, but there is no backend/API access.
- Do not implement scraping, hidden API calls, network interception, or credential automation.
- Do not add real SeedTalent content, production credentials, or employee PII.
- Use fake fixtures only.
- All reconstructed chunks and generated training outputs must default to needs_review.

Task:
1. Inspect the scaffold.
2. Identify the smallest useful end-to-end MVP slice.
3. Propose a concrete implementation plan before coding.
4. Then implement the first slice if the plan is straightforward.

Target first slice:
- create capture batch
- create capture session
- append operator note/event
- register screenshot path
- generate a simple QA report object from session metadata
- persist as local JSON files only, no real database yet unless already simple
- tests using fake data

Done when:
- pytest passes
- python -m compileall src passes
- README or docs are updated if behavior changes
- final response lists files changed, tests run, assumptions, and security/privacy notes
```
