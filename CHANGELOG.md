# Changelog

## Unreleased

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
