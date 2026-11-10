# Obsidian Research OS

Obsidian Research OS is a small terminal companion for an Obsidian vault. It
helps you begin the day, keep tasks from drifting, capture thoughts before they
disappear, and keep research and practice visible. Your notes stay ordinary
Markdown files in your own vault; this tool just makes the recurring bits quick.

**New here?** Follow [GETTING_STARTED.md](GETTING_STARTED.md) for a
step-by-step walkthrough from a fresh clone to a working daily routine. This
README is the full reference.

## Who this is for

This is a good fit if you:

- use Obsidian for daily notes and want some structure without another big app;
- read papers, build ideas, or work on a longer research project;
- want a lightweight weekly view of tasks, research, Inbox items, and skills;
- like quick terminal actions but do your real writing in Obsidian.

It may be more than you need for a plain todo list. Calendar and PDF features
are optional, so you can start small and add them later.

## What it does

| Area | What `obs` helps with |
| --- | --- |
| Daily work | Open today’s note, add tasks, finish tasks, and close the day with a reflection. |
| Inbox | Capture a thought in one command, then turn it into a task or concept later. |
| Research | Create concept notes, import PDFs, make paper notes, and maintain indexes. |
| Skills | Log chess, typing, or any other practice you want to revisit. |
| Weekly review | See task movement, research updates, inbox state, wins, and skill progress. |
| Optional extras | Sync Google Calendar and back up the vault with Git. |

## Install

You need Bash, Python 3.10+, and Obsidian. Git is only needed for backups.
Commands that open or search notes also need the [Obsidian CLI](https://help.obsidian.md/cli)
available as `obsidian`.

Clone the project anywhere you like, then link the command from that folder:

```bash
git clone https://github.com/AbhayKabdwal/obsidian-research-os
cd obsidian-research-os
chmod +x bin/obs
mkdir -p "$HOME/.local/bin"
ln -sf "$(pwd)/bin/obs" "$HOME/.local/bin/obs"
```

Or, from the repository folder, run `./install.sh` to create that link for you.

Make sure `~/.local/bin` is on your `PATH`, restart the terminal if needed, and
check the command:

```bash
obs help
```

### macOS Installation

For macOS-specific setup details (Bash upgrade, Obsidian CLI, troubleshooting), see [MACOS_INSTALL.md](MACOS_INSTALL.md).


### Connect your vault

Pick an existing vault or a new folder. `obs setup` stores that choice in a
small local config file outside the repository and outside your vault, so it
will not end up in Git.

```bash
obs setup ~/Documents/My-Research-Vault
obs init
```

`obs init` creates folders and copies templates only when they do not already
exist, so it is safe to run on an existing vault.

In Obsidian, enable the core **Templates** and **Daily notes** plugins and set:

```text
Templates folder: Templates
Daily notes folder: Daily
Daily notes template: Templates/Daily
```

If your vault has a different display name inside Obsidian, supply it too:

```bash
obs setup ~/Documents/My-Research-Vault "My Research Vault"
```

To use another vault for one command without changing your saved setup
(an environment variable takes precedence over the saved config):

```bash
OBSIDIAN_VAULT_PATH=./demo-vault OBSIDIAN_VAULT_NAME=demo-vault obs init
```

### Bash note

Bash treats `!` specially in some configurations. If `obs task add "Follow up!!!"`
behaves oddly, source `shell/obs.bash` from your shell profile (using your own
clone location), or use single quotes around text that contains `!`.

## Everyday use

A simple first-day flow:

```bash
obs start
obs task add "Read the introduction"
obs capture "Retrieval ranking" "Compare this idea with retrieval ranking"
obs capture check
obs concept "Retrieval ranking"
obs skill typing 92 98 60s
obs close
```

The main command view is deliberately short. Ask for help whenever you need it:

```text
obs setup PATH [VAULT_NAME]       Connect a vault once
obs doctor                        Check setup and optional tools
obs init                          Create folders, templates, and indexes
obs today | obs start | obs close Work with today’s note

obs task add "…" | done N | delete N | next | obs tasks
obs capture "Title" "Content" | obs inbox review
obs concept "…" | obs paper new|import|show
obs skill chess|typing|note
obs review week | obs streak | obs index | obs backup
obs calendar today|sync|add|delete
```

Useful examples:

```bash
obs task done 2
obs task next
obs task due 2026-09-12 "Send the draft"
obs focus 25 "Write the draft introduction"
obs paper import ~/Downloads/a-paper.pdf
obs skill chess "Kept my king active in endings" 1482
obs skill note "Spanish" "Practised the past tense"
obs review week
```

`obs review week` is a calm reset, not a scorecard. It summarizes the last
seven days of tasks, carry-forwards, research bullets, new concepts and paper
notes, Inbox state, reflection wins, and skill logs.

### Optional programs when starting work

`obs start` only opens Obsidian and shows your tasks. It does not launch a
timer, music player, or any other personal application by default.

If you want to start another program, set `OBS_START_HOOK` in your shell
profile or in `~/.config/obsidian-research-os/config.env`. The hook is a shell
command run in the background whenever `obs start` runs:

```bash
# Example: start a timer alongside your daily note.
OBS_START_HOOK='pomatez'
```

You can replace `pomatez` with any command available on your computer. Keep
the hook short and make the invoked program responsible for avoiding duplicate
instances if that matters for your workflow.

### Obsidian CLI troubleshooting (Linux)

The `obsidian` CLI connects to the running desktop app, so it must be enabled
in **Settings → General → Command line interface** and Obsidian must be open.
`obs` now uses the registered `obsidian://` desktop handler by default rather
than trying to launch the CLI client as though it were the app. For an AppImage
or another custom install, point `OBSIDIAN_APP_CMD` at the desktop launcher:

```bash
OBSIDIAN_APP_CMD='/path/to/Obsidian.AppImage' obs start
```

If Obsidian was installed with Flatpak and the CLI still says it cannot find
Obsidian, its runtime socket may be isolated. Create this per-login symlink,
then retry:

```bash
ln -sf /run/user/$(id -u)/.flatpak/md.obsidian.Obsidian/xdg-run/.obsidian-cli.sock \
  /run/user/$(id -u)/.obsidian-cli.sock
```

Run `obs doctor` afterwards to check the rest of the local setup.

`obs focus` opens a clean built-in focus window: a single task card, visual
countdown ring, and only **Pause/Resume** and **Finish session** controls. It
starts at 25 minutes by default (or a duration you choose), and logs a completed
block in today’s note. Use **Space** or **P** to pause, **Enter** to finish, and
**Esc** to cancel without logging. Finishing early asks whether to log the actual
focused time. The window uses Python’s built-in Tkinter. On Linux, install your
distribution’s `python3-tk` package if `obs doctor` reports it is missing.
`obs task due YYYY-MM-DD "Task"` adds a readable due-date marker; `obs tasks`
highlights tasks due today or overdue.

To share a weekly snapshot, run `obs export week`. It writes a Markdown report
to `Exports/` in the vault by default, or accept a path such as
`obs export week ~/Desktop/weekly-review.md`.

Run `obs doctor` if something is not working or before reporting a setup
problem. It checks the vault, templates, Python, Obsidian CLI, Git, and the
optional calendar environment without changing anything. `obs config show`
prints the saved vault configuration.

## Research and note layout

After `obs init`, the vault has a simple layout:

```text
Daily/                 one note per day
Inbox/                 quick captures (and Inbox/Archive after review)
Research/Concepts/     durable ideas
Research/Papers/       paper notes
PDFs/Papers/           imported PDFs, grouped by year
Templates/             Daily, Inbox, Research, and Paper templates
```

`obs index` refreshes `Daily Notes.md` and `Paper Notes.md` while leaving your
own text around the generated index blocks alone.

## Optional: Google Calendar

From the repository folder, create the project virtual environment and install
the optional calendar dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-calendar.txt
```

Create a Google Cloud project, enable Google Calendar API, and create an OAuth
**Desktop app** credential. Save the downloaded JSON as:

```text
~/.config/obsidian-research-os/credentials.json
```

On the **OAuth consent screen**, add your own Google account under
**Test users** (or publish the app). Without this, Google blocks the
authorization and refresh tokens expire after seven days.

Then authorize once:

```bash
obs calendar auth
```

This opens Google authorization and verifies the connection, printing the
calendar name and timezone on success. The token stays in the same config
directory and should never be committed. Google Calendar is the source of
truth; deleting a rendered event from a Daily note does not delete it from
Google.

### Calendar authorization troubleshooting

`obs doctor` reports whether credentials and a token are present, and
`obs calendar auth` checks the live connection. An expired token is refreshed
automatically; a token that can no longer be refreshed at all is discarded and
re-authorized on the next run.

| Google reports | Meaning | Fix |
| --- | --- | --- |
| `deleted_client` | The OAuth client was deleted in Google Cloud | Create a new Desktop app client, overwrite `credentials.json`, run `obs calendar auth` |
| `invalid_client` | `credentials.json` does not match a live client | Re-download the client JSON, then `obs calendar auth --reset` |
| `invalid_grant` | Consent revoked, or a testing-mode refresh token aged out after 7 days | `obs calendar auth` (add yourself as a Test user to stop it recurring) |
| `access_denied` / app blocked | Your account is not a Test user | Add it on the OAuth consent screen, then `obs calendar auth` |
| API disabled (HTTP 403) | Calendar API not enabled for the project | Enable the Google Calendar API, then retry |

To force a fresh consent flow after replacing credentials:

```bash
obs calendar auth --reset
```

Authorization needs a terminal and a browser. A `systemd` timer cannot
authorize on its own, so run `obs calendar auth` once by hand after any
credential change; the timer then refreshes the token unattended.

## Optional: Git backup

Initialize Git once in your vault and add a remote if you want off-machine
backups:

```bash
cd ~/Documents/My-Research-Vault
git init
git add .
git commit -m "Start my vault"
```

After that, `obs backup` makes a commit and pushes when an `origin` remote
exists. Without a remote it still creates a local backup commit.

Use `obs backup status` to see uncommitted vault changes, the most recent
backup, and the configured remote. If this project was installed as a Git
clone, `obs update` safely fast-forwards it after checking that the project
itself has no uncommitted changes.

## Optional: scheduled jobs (Linux/systemd)

The `systemd/` folder contains user services for calendar sync, task rollover,
and Git backup. They use the vault you connected with `obs setup`; no vault
path needs editing in the service files.

```bash
mkdir -p ~/.config/systemd/user
cp systemd/*.service systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now obsidian-calendar-sync.timer
systemctl --user enable --now obsidian-task-rollover.timer
systemctl --user enable --now obsidian-vault-backup.timer
```

## Project layout

```text
bin/obs                 command dispatcher and workflows
lib/obs_config.sh       portable per-user vault configuration
lib/obs_help.sh         CLI help views
lib/obs_doctor.sh       non-mutating setup diagnostics
vault_ops.py            safe Daily-note edits, indexes, and weekly review
calendar_sync.py        optional Google Calendar integration
focus_timer.py          small GUI focus timer, linked to Daily-note logging
templates/              vault templates copied by obs init
systemd/                optional Linux user timers
tests/                  automated checks for core Daily-note behavior
```

## Releases and contributing

This project is available under the [MIT License](LICENSE). See
[CHANGELOG.md](CHANGELOG.md) for release notes and [CONTRIBUTING.md](CONTRIBUTING.md)
if you would like to help improve it.

To publish your own copy, create an empty GitHub repository, then run these
commands from this project folder (replace the URL with yours):

```bash
git init -b main
git add .
git commit -m "Initial open-source release"
git remote add origin https://github.com/YOUR-ACCOUNT/obsidian-research-os.git
git push -u origin main
```

The repository includes an MIT license, contribution guidance, and GitHub pull
request and issue templates so others can contribute without needing access to
your vault or credentials.

## Privacy and safety

The tool works on local Markdown files. Keep OAuth credentials, tokens, and
your local config outside the repository. The included `.gitignore` keeps
generated Python files and local secrets out of Git.
