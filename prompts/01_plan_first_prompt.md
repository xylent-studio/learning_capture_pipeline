# Plan-first Codex prompt

```text
Use Plan mode first.

Goal: Build the next component of the State of Mind SeedTalent capture pipeline.

Context: Read AGENTS.md, docs/01_architecture.md, docs/03_governance_policy.md, and the relevant files for this task.

Before coding:
- Restate the allowed/disallowed boundaries.
- Identify the likely data flow.
- Identify tests needed.
- Identify privacy/security risks.
- Ask only blocking questions; otherwise make reasonable assumptions and proceed.

Constraints:
- no backend SeedTalent scraping
- no hidden APIs
- no credentials
- no real SeedTalent content
- fake fixtures only
- all generated/reconstructed content starts as needs_review

Done when:
- tests pass
- code is reviewed against AGENTS.md
- source citations/review gates are preserved where relevant
```
