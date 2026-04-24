# TICKET 023: Permission Manifest Loader

Implement a loader for `config/permission_manifest.example.yaml`.

Requirements:
- Pydantic models for manifest, vendor permissions, account aliases, PII policy.
- `authorize_capture(url, vendor, course_title, manifest)` returns authorized/flagged with reason.
- In-scope wildcard fixture should resolve to `seedtalent_contract_full_use`.
- Unknown only when metadata cannot match manifest.
- Unit tests.
