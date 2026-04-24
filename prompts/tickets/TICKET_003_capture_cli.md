# Ticket 003: Capture CLI

Goal: Expand `som-capture` into useful operator commands.

Commands:
- batch create
- session start
- session note
- session screenshot
- session stop
- session status
- qa report

Requirements:
- rich output
- JSON persistence through local store
- no login automation
- no real SeedTalent access in tests

Done when:
- CLI tests use isolated temp directories
- help text is clear for operators
