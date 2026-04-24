# Ticket 004: Recorder abstraction

Goal: Add an interface for screen/audio recording providers.

Providers:
- dry-run fake provider for tests
- OBS command provider skeleton
- FFmpeg command provider skeleton

Requirements:
- start/stop recording methods
- output path metadata
- command construction separated from execution
- no platform-specific assumptions hardcoded into tests

Done when:
- tests verify command construction and fake provider behavior
