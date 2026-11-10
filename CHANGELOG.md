# Changelog

## Unreleased

- Fixed environment overrides being silently ignored. `config.env` was sourced
  after the environment was read, so `OBSIDIAN_VAULT_PATH=./other obs init`
  (and `OBSIDIAN_VAULT_NAME`, `OBSIDIAN_CMD`, `OBSIDIAN_APP_CMD`,
  `OBS_START_HOOK`) operated on the saved vault instead of the requested one.
  An explicit environment variable now wins over the saved config.
- Added `GETTING_STARTED.md`, a step-by-step setup and first-day walkthrough.
- `obs help` now lists `obs calendar auth`.

- Fixed Google Calendar OAuth getting permanently stuck: a stored token that
  can no longer be refreshed (`deleted_client`, `invalid_client`,
  `invalid_grant`, `unauthorized_client`) is now discarded and re-authorized
  instead of aborting the sync.
- A token minted for a different OAuth client is detected and replaced, so
  dropping in a new `credentials.json` no longer requires deleting
  `token.json` by hand.
- Added `obs calendar auth [--reset]` to authorize and verify the connection,
  reporting the calendar name and timezone on success.
- `obs doctor` now checks calendar credentials, token presence, and OAuth
  client mismatch.
- OAuth failures now explain the cause and the fix, including enabling the
  Calendar API and adding yourself as a Test user; non-interactive runs
  (systemd timers) say to run `obs calendar auth` from a terminal.

## 0.1.0 — 2026-09-07

- First shareable release of Obsidian Research OS.
- Portable `obs setup` configuration and a GitHub-friendly install flow.
- Daily tasks, Inbox capture, research/paper workflows, skill logs, calendar
  sync, Git backups, and seven-day review.
- Added `obs doctor`, `obs config show`, `obs task next`, and `obs streak`.
- Added a polished GUI focus timer with a visual countdown, Pause/Resume,
  Finish controls, and keyboard shortcuts, linked to Daily-note logging; also
  added dated tasks, weekly Markdown exports, backup status, and safe
  Git-checkout updates.
