# Ticket 005: Playwright headed capture runner

Goal: Build a headed-browser runner for authorized capture sessions.

Requirements:
- fixed viewport
- manual login support
- storage state path outside repo
- URL/title event logging
- interval screenshots
- operator notes accepted from CLI or file
- fake local HTML course fixture for tests

Hard constraints:
- no network interception
- no hidden API calls
- no credential storage in repo

Done when:
- tests run against fake HTML fixture
- docs describe manual login process
