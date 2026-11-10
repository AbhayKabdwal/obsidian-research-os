#!/usr/bin/env bash
# Human-readable command views for the obs CLI.

short_usage() {
  cat <<'EOF'
Obsidian Research OS — a calm command line for your vault

START HERE
  obs setup PATH             Connect a vault once
  obs doctor                 Check setup and optional tools
  obs init                   Add the folders, templates, and indexes
  obs start                  Open today and begin working
  obs close                  Wrap up and carry work forward

DAILY WORK
  obs task add "…"            Add a task       obs tasks
  obs task done NUMBER        Finish a task    obs task delete NUMBER
  obs task next               Show the next task (prioritizes ! tasks)
  obs focus [MINUTES] ["…"]   Run and log a focus session
  obs capture "Title" "Content" Save an idea   obs inbox review
  obs capture check             Update and audit captures

RESEARCH & LEARNING
  obs concept "…"             Make a concept note
  obs paper new|import|show   Work with papers
  obs skill chess|typing|note Log practice
  obs review week             See the week at a glance
  obs export week [FILE]      Save that review as Markdown

ORGANIZE & SYNC
  obs index                  Refresh note indexes
  obs calendar ics           Read-only calendar, no Cloud project
  obs calendar auth          Authorise Google Calendar
  obs calendar today|sync|add|delete
  obs backup                 Commit the vault to Git
  obs backup status          Check backup health
  obs update                 Fast-forward this Git checkout

Try: obs help task | paper | calendar | skills | all
EOF
}

help() {
  case "${1:-}" in
    ""|main) short_usage ;;
    setup) echo 'obs setup PATH [VAULT_NAME] — save this vault location locally, then run obs init. Use obs config show to inspect it.' ;;
    doctor) echo 'obs doctor — check vault configuration, templates, Python, Obsidian CLI, Git, and optional calendar setup.' ;;
    init) echo 'obs init — create the Research OS folders, copy templates, and build indexes. It never overwrites an existing template.' ;;
    today) echo "obs today — open today's Daily note in Obsidian." ;;
    start|morning) echo "obs start — recover overdue tasks, run the optional startup hook, open today's note, and show open tasks." ;;
    close) echo 'obs close — reflect on today and select unfinished tasks to carry into tomorrow.' ;;
    task)
      cat <<'EOF'
Tasks

  obs task add "Task text"
  obs tasks
  obs task done NUMBER
  obs task delete NUMBER
  obs task next
  obs task due YYYY-MM-DD "Task text"

`obs task "Task text"` is kept as a short alias for adding a task.
EOF
      ;;
    tasks) echo "obs tasks — list today's open tasks with numbers." ;;
    index) echo 'obs index — rebuild Daily Notes.md and Paper Notes.md without touching your own text.' ;;
    capture)
      cat <<'EOF'
obs capture "Title" "Content" — create a titled Inbox note.
obs capture check             — update the capture index and audit captures.
EOF
      ;;
    inbox) echo 'obs inbox review — turn Inbox notes into tasks or concepts, archive them, or keep them for later.' ;;
    review) echo 'obs review week — show task, research, inbox, reflection, focus, and skill progress from the last seven days. Use obs export week to save it.' ;;
    export) echo 'obs export week [OUTPUT.md] — write a shareable Markdown copy of this week’s review. Defaults to vault/Exports/.' ;;
    focus) echo 'obs focus [MINUTES] ["Task description"] — open the built-in focus window with Pause and Finish controls; finishing logs the session in today’s note.' ;;
    concept|research) echo 'obs concept "Title" — create a note in Research/Concepts.' ;;
    paper|paper-add|paper-show)
      cat <<'EOF'
Paper workflow

  obs paper new "Title"       Create a blank paper note
  obs paper import [FILE.pdf]  Copy a PDF and create/update its note
  obs paper show               Find and open a paper note

Important concepts found during import can be saved in Research/Concepts.
EOF
      ;;
    skill|skills)
      cat <<'EOF'
Skill log

  obs skill chess "What improved" [ELO]
  obs skill typing WPM ACCURACY [MODE]
  obs skill note "Skill" "What improved"
EOF
      ;;
    search) echo 'obs search "Query" — search vault note names and content through Obsidian.' ;;
    calendar)
      cat <<'EOF'
Calendar

  obs calendar today
  obs calendar sync [--date YYYY-MM-DD]
  obs calendar add ["Title" "YYYY-MM-DD HH:MM" "YYYY-MM-DD HH:MM"]
  obs calendar delete EVENT_ID [--yes]
EOF
      ;;
    backup) echo 'obs backup [status] — commit vault changes and push when an origin remote is configured; status checks the latest backup and pending changes.' ;;
    update) echo 'obs update — fast-forward this Git checkout after confirming it has no uncommitted project changes.' ;;
    all)
      short_usage
      echo
      echo 'Compatibility aliases: morning, research, paper-add, and paper-show.'
      ;;
    *)
      echo "Usage: obs help [setup|doctor|init|today|start|close|task|focus|tasks|index|capture|inbox|concept|paper|skills|search|calendar|review|export|backup|update|all]" >&2
      exit 1
      ;;
  esac
}
