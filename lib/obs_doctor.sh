#!/usr/bin/env bash
# Friendly, non-mutating setup diagnostics.

doctor() {
  local problems=0

  echo "Obsidian Research OS doctor"
  if [[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]]; then
    echo "  ✓ Vault: $VAULT_PATH"
  else
    echo "  ✗ Vault: not configured (run: obs setup /path/to/vault)"
    problems=$((problems + 1))
  fi

  if command -v python3 >/dev/null 2>&1; then
    echo "  ✓ Python: $(python3 --version 2>&1)"
  else
    echo "  ✗ Python 3: not found"
    problems=$((problems + 1))
  fi

  if python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "  ✓ Focus window: ready"
  else
    echo "  ! Focus window: Tkinter is missing (install python3-tk to use obs focus)"
  fi

  if command -v "$OBSIDIAN_CMD" >/dev/null 2>&1; then
    echo "  ✓ Obsidian CLI: $OBSIDIAN_CMD"
  else
    echo "  ! Obsidian CLI: '$OBSIDIAN_CMD' not found (needed for opening, search, capture, and papers)"
  fi

  if command -v git >/dev/null 2>&1; then
    echo "  ✓ Git: $(git --version | head -n 1)"
  else
    echo "  ! Git: not found (only needed for obs backup)"
  fi

  if [[ -x "$BASE_DIR/.venv/bin/python" ]]; then
    echo "  ✓ Calendar environment: ready"
  else
    echo "  ! Calendar environment: optional; create with python3 -m venv .venv"
  fi

  local cal_config_dir="${OBSIDIAN_RESEARCH_OS_CONFIG_DIR:-$HOME/.config/obsidian-research-os}"
  local cal_credentials="$cal_config_dir/credentials.json"
  local cal_token="$cal_config_dir/token.json"

  if [[ ! -f "$cal_credentials" ]]; then
    echo "  ! Calendar credentials: not set up ($cal_credentials)"
    echo "      Create a Desktop OAuth client, then run: obs calendar auth"
  elif [[ ! -f "$cal_token" ]]; then
    echo "  ! Calendar auth: not authorised yet (run: obs calendar auth)"
  else
    local cred_id token_id
    cred_id="$(
      sed -n 's/.*"client_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
        "$cal_credentials" | head -n 1
    )"
    token_id="$(
      sed -n 's/.*"client_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
        "$cal_token" | head -n 1
    )"

    if [[ -n "$cred_id" && -n "$token_id" && "$cred_id" != "$token_id" ]]; then
      echo "  ! Calendar auth: stored token is for a different OAuth client"
      echo "      Re-authorise with: obs calendar auth --reset"
    else
      echo "  ✓ Calendar auth: credentials and token present"
      echo "      Verify the live connection with: obs calendar auth"
    fi
  fi

  if [[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]]; then
    local template missing=0
    for template in Daily.md Research.md Paper.md Inbox.md; do
      if [[ ! -f "$VAULT_PATH/Templates/$template" ]]; then
        missing=1
      fi
    done
    if [[ $missing -eq 0 ]]; then
      echo "  ✓ Vault templates: ready"
    else
      echo "  ! Vault templates: missing one or more (run: obs init)"
    fi
  fi

  if [[ $problems -eq 0 ]]; then
    printf '\nCore setup looks good. Items marked ! are optional.\n'
  else
    printf '\nFix the items marked ✗, then run obs doctor again.\n'
    return 1
  fi
}
