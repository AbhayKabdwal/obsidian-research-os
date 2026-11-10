#!/usr/bin/env bash
# Configuration and paths shared by the obs command modules.

OBS_CONFIG_FILE="${OBSIDIAN_RESEARCH_OS_CONFIG:-${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-research-os/config.env}"

# Remember any overrides that were already set in the environment. Sourcing
# the saved config below would otherwise overwrite them, which would silently
# ignore a per-command override such as:
#   OBSIDIAN_VAULT_PATH=./demo-vault obs init
# and operate on the saved vault instead.
_obs_env_vault_path="${OBSIDIAN_VAULT_PATH:-}"
_obs_env_vault_name="${OBSIDIAN_VAULT_NAME:-}"
_obs_env_obsidian_cmd="${OBSIDIAN_CMD:-}"
_obs_env_obsidian_app_cmd="${OBSIDIAN_APP_CMD:-}"
_obs_env_start_hook="${OBS_START_HOOK:-}"

if [[ -f "$OBS_CONFIG_FILE" ]]; then
  # This file is created locally by `obs setup`; it is intentionally not part
  # of the repository because it describes one person's vault.
  # shellcheck disable=SC1090
  source "$OBS_CONFIG_FILE"
fi

# An explicit environment variable wins over the saved config.
OBSIDIAN_VAULT_PATH="${_obs_env_vault_path:-${OBSIDIAN_VAULT_PATH:-}}"
OBSIDIAN_VAULT_NAME="${_obs_env_vault_name:-${OBSIDIAN_VAULT_NAME:-}}"
OBSIDIAN_CMD="${_obs_env_obsidian_cmd:-${OBSIDIAN_CMD:-}}"
OBSIDIAN_APP_CMD="${_obs_env_obsidian_app_cmd:-${OBSIDIAN_APP_CMD:-}}"
OBS_START_HOOK="${_obs_env_start_hook:-${OBS_START_HOOK:-}}"

unset _obs_env_vault_path _obs_env_vault_name _obs_env_obsidian_cmd
unset _obs_env_obsidian_app_cmd _obs_env_start_hook

VAULT_PATH="${OBSIDIAN_VAULT_PATH:-${VAULT_PATH:-}}"
VAULT_NAME="${OBSIDIAN_VAULT_NAME:-${VAULT_NAME:-${VAULT_PATH:+$(basename "$VAULT_PATH")}}}"
OBSIDIAN_CMD="${OBSIDIAN_CMD:-obsidian}"
OBSIDIAN_APP_CMD="${OBSIDIAN_APP_CMD:-}"
OBS_START_HOOK="${OBS_START_HOOK:-}"

setup_vault() {
  local requested_path="${1:-}"
  local requested_name="${2:-}"

  if [[ -z "$requested_path" ]]; then
    echo "Usage: obs setup PATH_TO_VAULT [OBSIDIAN_VAULT_NAME]" >&2
    echo "Example: obs setup ~/Documents/My-Vault" >&2
    exit 1
  fi

  mkdir -p "$requested_path"
  requested_path="$(cd "$requested_path" && pwd)"
  requested_name="${requested_name:-$(basename "$requested_path")}"
  mkdir -p "$(dirname "$OBS_CONFIG_FILE")"

  umask 077
  {
    printf '# Created by obs setup. This file stays on your computer.\n'
    printf 'OBSIDIAN_VAULT_PATH=%q\n' "$requested_path"
    printf 'OBSIDIAN_VAULT_NAME=%q\n' "$requested_name"
  } > "$OBS_CONFIG_FILE"

  VAULT_PATH="$requested_path"
  VAULT_NAME="$requested_name"
  echo "Saved vault configuration: $OBS_CONFIG_FILE"
  echo "Vault: $VAULT_PATH"
}

show_config() {
  echo "Vault path: ${VAULT_PATH:-not configured}"
  echo "Vault name: ${VAULT_NAME:-not configured}"
  echo "Config file: $OBS_CONFIG_FILE"
}

require_vault() {
  if [[ -z "$VAULT_PATH" ]]; then
    echo "No vault is configured yet." >&2
    echo "Run: obs setup /path/to/your-vault" >&2
    exit 1
  fi
  if [[ ! -d "$VAULT_PATH" ]]; then
    echo "ERROR: Obsidian vault not found: $VAULT_PATH" >&2
    echo "Update it with: obs setup /path/to/your-vault" >&2
    exit 1
  fi
}
