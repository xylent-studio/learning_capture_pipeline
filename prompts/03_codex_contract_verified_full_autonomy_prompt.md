Goal: Convert this scaffold into a contract-verified, fully autonomous SeedTalent capture system.

Project facts:
- State of Mind has paid SeedTalent and obtained permission from SeedTalent and relevant vendors to use the covered content.
- SeedTalent is not providing backend access or APIs.
- The approved capture path is autonomous visible-UI capture through a credentialed SeedTalent account.
- In-scope content should use `permission_basis=seedtalent_contract_full_use`.
- Rights metadata is for proof/audit/scope, not a generic blocker.

Read first:
- AGENTS.md
- docs/11_autonomous_capture_strategy.md
- docs/15_contract_verified_full_autonomy.md
- docs/16_autonomous_implementation_blueprint.md
- docs/17_credential_and_auth_design.md
- config/permission_manifest.example.yaml
- .agents/skills/contract-verified-autonomy/SKILL.md

Do not:
- probe hidden APIs,
- intercept network traffic,
- reverse engineer backend endpoints,
- bypass access controls,
- commit credentials,
- commit real SeedTalent content,
- put employee PII in tests, fixtures, logs, embeddings, or generated training.

First task:
1. Inspect the repo.
2. Propose the smallest end-to-end autonomous slice.
3. Implement that slice against a fake local SeedTalent-like fixture.

Target first slice:
- load permission manifest,
- confirm `seedtalent_contract_full_use` authorizes fixture course,
- run a fake auth preflight,
- discover one fixture course through visible UI,
- create a course capture plan,
- drive the fake course with Playwright,
- capture visible DOM text and screenshots,
- detect static/video/quiz/completion states,
- create a QA report,
- mark successful capture ready_for_reconstruction.

Done when:
- tests pass,
- `python -m compileall src` passes,
- no credentials or real content are added,
- final response lists files changed, tests run, assumptions, and remaining risks.
