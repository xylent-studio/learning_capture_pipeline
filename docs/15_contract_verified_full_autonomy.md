# 15 Contract-Verified Full Autonomy

## Position

State of Mind has paid for and obtained permission from SeedTalent and relevant vendors to use the covered content. This repository should encode that business fact directly.

The system should not behave as though State of Mind lacks permission for covered content. The implementation should instead preserve proof of permission, enforce scope boundaries, and keep credentials/PII safe.

## Primary permission basis

Use:

```text
seedtalent_contract_full_use
```

for in-scope SeedTalent/vender content covered by the contract and permission manifest.

Recommended default metadata:

```text
permission_basis = seedtalent_contract_full_use
rights_status = seedtalent_contract_full_use
ai_use_allowed = true
derivative_use_allowed = true
internal_training_use_allowed = true
screen_capture_allowed = true
visible_dom_capture_allowed = true
audio_capture_allowed = true
video_capture_allowed = true
quiz_capture_allowed = true
report_capture_allowed = true
```

## What rights controls are for

Rights controls are not a moral/legal refusal layer. They are an evidence and audit layer.

They should answer:

- Which contract or vendor permission covers this capture?
- Which course, vendor, brand, and account was used?
- Was the content inside the agreed scope?
- Was the capture performed through approved visible-UI mechanisms?
- Was employee PII kept out of training embeddings?
- Can this chunk be used for internal training generation?
- Which generated module came from which timestamp/screenshot/chunk?

## What should trigger a flag

A flag is appropriate only when:

- the course/vendor is not covered by the manifest,
- the URL is outside approved SeedTalent training scope,
- the page is account/billing/private-message/settings/support rather than training content,
- employee PII or report data is being mixed into training content,
- the bot is using a prohibited technique,
- QA coverage is poor,
- the capture appears incomplete.

## What should not trigger a flag

Do not flag merely because:

- the source is SeedTalent,
- the content belongs to a vendor that is in the permission manifest,
- the bot is autonomous,
- the bot uses a dedicated credentialed capture account,
- the bot uses visible DOM extraction,
- the bot records audio/video through approved screen capture,
- the bot creates derivative internal training from in-scope content.

## Implementation rule

The permission manifest is the source of truth. Codex should implement `authorize_capture(course, vendor, url, manifest)` and use it to stamp in-scope records as authorized.

Unknown should be rare and specific. It should mean the system lacks enough metadata to match the manifest, not that SeedTalent content is generally unauthorized.
