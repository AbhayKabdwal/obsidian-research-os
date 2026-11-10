# Getting Started

A first-run walkthrough: from a fresh clone to a working daily routine in
about fifteen minutes. The [README](README.md) is the reference for every
command; this page is the path through it in order.

Each step ends with a way to check it worked. If a check fails, stop there —
later steps assume it passed.

---

## Before you start

You need:

| Requirement | Why | Check |
| --- | --- | --- |
| Bash | Runs the `obs` command | `bash --version` |
| Python 3.10+ | Tasks, notes, calendar | `python3 --version` |
| Obsidian | Where you actually read and write | — |
| Obsidian CLI as `obsidian` | Opening, searching, capture, papers | `obsidian --version` |
| Git | Only for `obs backup` | `git --version` |

The Obsidian CLI must be enabled inside the app at
**Settings → General → Command line interface**, and Obsidian must be running
for commands that open or search notes. On macOS, read
[MACOS_INSTALL.md](MACOS_INSTALL.md) first — Bash and the CLI both need extra
steps there.

Everything except Bash, Python and Obsidian is optional. You can finish
steps 1–5 and have a useful tool without Git or the calendar.

---

## Step 1 — Install the command

```bash
git clone https://github.com/AbhayKabdwal/obsidian-research-os
cd obsidian-research-os
./install.sh
```

`install.sh` symlinks `bin/obs` into `~/.local/bin`. Keep the clone — the
symlink points back at it, so moving or deleting the folder breaks `obs`.

Make sure `~/.local/bin` is on your `PATH`, then restart your terminal.

**Check:** `obs help` prints the command list.

If it says `obs: command not found`, add this to your shell profile
(`~/.bashrc` or `~/.zshrc`) and restart the terminal:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## Step 2 — Connect a vault

Point `obs` at an Obsidian vault. It can be one you already use or an empty
folder that becomes one.

```bash
obs setup ~/Documents/My-Research-Vault
```

If the vault's display name inside Obsidian differs from its folder name, pass
it as a second argument:

```bash
obs setup ~/Documents/My-Research-Vault "My Research Vault"
```

This writes to `~/.config/obsidian-research-os/config.env` — outside the repo
and outside your vault, so your personal paths never reach Git.

**Check:** `obs config show` prints the vault path you chose.

---

## Step 3 — Create the structure

```bash
obs init
```

This adds folders, templates and index notes, creating only what is missing.
It is safe to run on a vault full of existing notes, and safe to re-run later.

You get:

```text
Daily/                 one note per day
Inbox/                 quick captures (Inbox/Archive after review)
Research/Concepts/     durable ideas
Research/Papers/       paper notes
PDFs/Papers/           imported PDFs, grouped by year
Templates/             Daily, Inbox, Research, Paper
```

**Check:** `obs doctor` reports `Vault templates: ready`.

---

## Step 4 — Point Obsidian at the same structure

In Obsidian, enable the core **Templates** and **Daily notes** plugins, then
set:

```text
Templates folder:       Templates
Daily notes folder:     Daily
Daily notes template:   Templates/Daily
```

Without this, Obsidian creates daily notes in a different place than `obs`
writes them, and the two stop agreeing about what "today" means. This is the
single most common setup mistake.

**Check:** creating a daily note from inside Obsidian puts it in `Daily/`.

---

## Step 5 — Run one full day

This is the core loop. Try it end to end now, with throwaway content:

```bash
obs start                                   # open today, show tasks
obs task add "Read the introduction"
obs task add "! Email my supervisor"        # ! marks it important
obs tasks                                   # list, with due/overdue flagged
obs task next                               # what to do now; ! first
obs capture "Retrieval ranking" "Compare with BM25"
obs task done 1
obs close                                   # reflect, carry work forward
```

`obs close` is what keeps tasks from silently dying: unfinished work is
carried into tomorrow instead of being stranded in a note you stop opening.

**Check:** today's note in `Daily/` shows the tasks, the completed one ticked,
and your reflection.

---

## Step 6 — Verify everything

```bash
obs doctor
```

This changes nothing. It checks the vault, templates, Python, Obsidian CLI,
Git, the calendar environment, and your calendar credentials. Run it first
whenever something misbehaves, and include its output in any bug report.

Lines marked `!` are optional features you have not set up. Lines marked `✓`
are working.

---

## Daily rhythm, once you are settled

| When | Command | What it does |
| --- | --- | --- |
| Morning | `obs start` | Opens today's note, shows tasks |
| During | `obs task add "…"` | Capture work as it arrives |
| During | `obs capture "Title" "Thought"` | Park an idea without derailing |
| During | `obs focus 25 "…"` | Timed block, logged when finished |
| Evening | `obs close` | Reflect, carry unfinished work forward |
| Weekly | `obs review week` | Seven days at a glance |
| Weekly | `obs inbox review` | Turn captures into concepts or tasks |

Anything you capture is a plain Markdown file in your vault. If you stop using
this tool tomorrow, your notes are unaffected — that is deliberate.

---

## Optional: Google Calendar

Calendar is genuinely optional; skip it if you do not want it.

### 1. Install the dependencies

From the repository folder:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-calendar.txt
```

Keep `.venv` — every `obs calendar` command uses it. It is gitignored, so it
never reaches the repository.

### 2. Create a Google OAuth client

1. Open <https://console.cloud.google.com/apis/credentials> and create or pick
   a project.
2. Enable the **Google Calendar API** for that project.
3. **Create Credentials → OAuth client ID → Desktop app**.
4. Download the JSON and save it as:

   ```text
   ~/.config/obsidian-research-os/credentials.json
   ```

5. On the **OAuth consent screen**, add your own Google account under
   **Test users**.

Step 5 is not optional. Without it Google refuses consent with
`Error 403: access_denied`, because an app in Testing mode only admits
developer-approved testers.

### 3. Authorise

```bash
obs calendar auth
```

A browser opens for consent. On success it prints your calendar name and
timezone, which means the API is genuinely reachable — not just that a file
was written.

### 4. Use it

```bash
obs calendar today                  # today's events and tasks
obs calendar sync                   # pull events into today's note
obs calendar sync --date 2026-11-14
obs calendar add                    # interactive, with repeat options
```

Google Calendar is the source of truth. Deleting a rendered event out of a
daily note does not delete it from Google.

### Worth knowing: the 7-day expiry

While your OAuth app stays in **Testing**, Google expires refresh tokens after
exactly 7 days, so you re-authorise weekly. To stop that, set the publishing
status to **In production** on the same consent screen. Because the calendar
scope is sensitive and the app is unverified, you will see a
"Google hasn't verified this app" warning — click **Advanced → Go to … (unsafe)**.
That is expected for a personal tool where you are both developer and only user.

---

## Optional: Git backup of your vault

```bash
cd ~/Documents/My-Research-Vault
git init
git remote add origin <your-private-vault-repo>
```

Then from anywhere:

```bash
obs backup           # commit and push the vault
obs backup status    # check backup health
```

Use a **private** repository. This backs up your notes, which is different
from this tool's own public repository.

---

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `obs: command not found` | `~/.local/bin` not on `PATH` | Export it in your shell profile, restart terminal |
| Cannot find Obsidian | CLI disabled, or app closed | Enable **Settings → General → Command line interface**; open Obsidian |
| Daily notes in two places | Obsidian folders do not match step 4 | Re-check Templates and Daily notes settings |
| `obs task add "Do it!!!"` misbehaves | Bash history expansion on `!` | Single-quote the text, or source `shell/obs.bash` |
| `obs focus` does nothing | Tkinter missing | Install `python3-tk` |
| Calendar: `Error 403: access_denied` | Not a Test user | Add your account under Test users, retry |
| Calendar: `deleted_client` | OAuth client deleted in Google Cloud | Make a new Desktop client, overwrite `credentials.json`, run `obs calendar auth` |
| Calendar: stops working after a week | Testing-mode 7-day expiry | `obs calendar auth`, or publish the app |
| Calendar fails under a systemd timer | Consent needs a browser | Run `obs calendar auth` once in a terminal |

When a stored calendar token can no longer be refreshed, it is discarded and
re-authorised automatically — you do not need to delete `token.json` by hand.

Still stuck? Run `obs doctor` and open an issue with its output:
<https://github.com/AbhayKabdwal/obsidian-research-os/issues>

---

## Where to go next

- [README](README.md) — full command reference and vault layout
- `obs help all` — every command, offline
- `obs help task | paper | calendar | skills` — one area at a time
- [CONTRIBUTING.md](CONTRIBUTING.md) — if you want to change the code
