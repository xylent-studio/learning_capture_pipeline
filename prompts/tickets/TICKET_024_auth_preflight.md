# TICKET 024: Auth Preflight

Implement auth preflight abstraction.

Requirements:
- Support `manual_storage_state` mode.
- Verify storage state path exists without printing its contents.
- Playwright preflight interface with fake implementation for tests.
- Return status: authenticated, auth_expired, prohibited_path, failed.
- Tests must not use real credentials.
