# 17 Credential and Auth Design

## Goal

Enable fully autonomous capture without putting SeedTalent credentials into code, prompts, tests, logs, screenshots, or repository files.

## Supported auth modes

### manual_storage_state

A human logs in once through the headed browser. The system saves Playwright storage state to a local secret path outside the repo. The bot reuses that state.

Use for MVP.

### vault_backed_login

The bot retrieves username/password from an approved secret manager at runtime and logs in through the normal visible UI.

Supported providers can be added behind an interface:

- 1Password CLI
- AWS Secrets Manager
- GCP Secret Manager
- Azure Key Vault
- Doppler
- Bitwarden CLI

### manual_reauth_on_expiry

If storage state expires or MFA is required, the bot stops, records `auth_expired`, and opens a manual reauth flow.

## Rules

- Do not commit storage state.
- Do not log cookies, tokens, passwords, MFA codes, or auth-state JSON.
- Put `.secrets/`, `playwright/.auth/`, and storage state paths in `.gitignore`.
- Use a dedicated capture account.
- Prefer account-level permissions limited to the approved course/report scope.
- Record the account alias, not the raw credential, in audit metadata.
- Do not use employee identities if a capture-bot account is available.

## Auth preflight

Before a capture batch:

1. launch headed browser,
2. load storage state,
3. visit SeedTalent base URL,
4. confirm logged-in state via visible UI,
5. confirm not on a prohibited page,
6. capture preflight screenshot,
7. record status.

If preflight fails, do not start the recorder or capture content. Create an auth exception.
