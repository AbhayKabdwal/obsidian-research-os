#!/usr/bin/env python3

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import ics_feed
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# Only event access is needed: this tool reads, creates and deletes events
# but never manages calendars themselves. The wider ".../auth/calendar" scope
# would also permit creating and deleting whole calendars.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
CALENDAR_ID = "primary"

# A Google Calendar "Secret address in iCal format". When set, the read-only
# commands use it instead of OAuth, which needs no Google Cloud project and
# no consent screen. Creating and deleting events still requires OAuth.
ICS_URL = os.environ.get(
    "OBSIDIAN_CALENDAR_ICS",
    "",
).strip()

# auto (default) prefers OAuth when credentials.json exists, else the feed.
# ics or oauth pin one mode.
CALENDAR_MODE = os.environ.get(
    "OBSIDIAN_CALENDAR_MODE",
    "auto",
).strip().lower()

CONFIG_DIR = Path(
    os.environ.get(
        "OBSIDIAN_RESEARCH_OS_CONFIG_DIR",
        Path.home() / ".config" / "obsidian-research-os",
    )
).expanduser()
CREDENTIALS = CONFIG_DIR / "credentials.json"
TOKEN = CONFIG_DIR / "token.json"

CALENDAR_API = "https://www.googleapis.com/calendar/v3"


# ================================================================
# Safe I/O and network helpers
# ================================================================

def atomic_write_text(path, text):
    """
    Write text to a file atomically.

    Writes to a temp file in the same directory, then renames it
    into place, so a crash mid-write can never leave a truncated
    Daily note, mapping file, or token file behind.
    """

    path = Path(path)
    tmp = path.parent / f".{path.name}.tmp{os.getpid()}"

    try:
        tmp.write_text(text)
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def request_or_die(func, *args, **kwargs):
    """
    Run a network request and turn connection-level failures (proxy
    down, DNS failure, timeout, etc.) into a friendly SystemExit
    instead of an uncaught traceback.
    """

    try:
        return func(*args, **kwargs)
    except requests.RequestException as exc:
        raise SystemExit(
            "Could not reach Google Calendar.\n"
            f"{exc}\n\n"
            "Check your network connection and proxy settings."
        )


def api_error(response):
    """Print a Google Calendar API error response and exit."""

    print()
    print("Google Calendar API error:")
    print(f"HTTP {response.status_code}")

    try:
        print(json.dumps(response.json(), indent=2))
    except ValueError:
        print(response.text)

    print()
    raise SystemExit(1)


def local_timezone_name():
    """
    Return the machine's IANA timezone name for Google Calendar.

    Google Calendar requires an IANA timezone name when a timed event
    uses recurrence rules.
    """

    # Explicit TZ environment variable takes priority when it is an
    # IANA timezone name.
    tz_env = os.environ.get("TZ", "").strip()
    if tz_env and "/" in tz_env:
        return tz_env

    # Most Linux systems expose the local timezone through /etc/localtime.
    try:
        resolved = Path("/etc/localtime").resolve()
        marker = "/zoneinfo/"
        resolved_str = str(resolved)
        if marker in resolved_str:
            timezone_name = resolved_str.split(marker, 1)[1]
            if timezone_name and "/" in timezone_name:
                return timezone_name
    except OSError:
        pass

    # Debian/Ubuntu commonly also stores the timezone here.
    try:
        timezone_file = Path("/etc/timezone")
        if timezone_file.exists():
            timezone_name = timezone_file.read_text().strip()
            if timezone_name and "/" in timezone_name:
                return timezone_name
    except OSError:
        pass

    # Fall back to the local offset only if an IANA name cannot be found.
    # The event remains correctly localized by its ISO-8601 offset.
    return None


def local_zoneinfo():
    """
    Return a tzinfo usable for arbitrary dates (past, present, future).

    A plain `datetime.now().astimezone().tzinfo` only captures *today's*
    fixed UTC offset; applied to a different date it can be wrong across
    a DST boundary. Prefer a real IANA zone (which knows the correct
    offset for any date) and only fall back to the fixed-offset value
    when no IANA name can be detected.
    """

    timezone_name = local_timezone_name()

    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            pass

    return (
        dt.datetime.now()
        .astimezone()
        .tzinfo
    )


# ================================================================
# Google authentication
# ================================================================

FATAL_OAUTH_ERRORS = (
    "deleted_client",
    "invalid_client",
    "invalid_grant",
    "unauthorized_client",
    "client_not_found",
)


def _client_id_from_credentials():
    """Return the client_id configured in credentials.json, or None."""

    try:
        with open(CREDENTIALS, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None

    block = (
        data.get("installed")
        or data.get("web")
        or {}
    )

    return block.get("client_id")


def _client_id_from_token():
    """Return the client_id stored in token.json, or None."""

    try:
        with open(TOKEN, encoding="utf-8") as fh:
            return json.load(fh).get("client_id")
    except Exception:
        return None


def _discard_token():
    """Remove a token that can no longer be used."""

    try:
        TOKEN.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _oauth_error_text(exc):
    """Flatten an OAuth exception into lowercase searchable text."""

    parts = [str(exc)]

    for attr in ("args", "description"):
        value = getattr(exc, attr, None)
        if value:
            parts.append(str(value))

    response = getattr(exc, "response", None)

    if response is not None:
        try:
            parts.append(str(response.text))
        except Exception:
            pass

    return " ".join(parts).lower()


def _missing_credentials_error():
    return SystemExit(
        f"Missing Google OAuth credentials:\n"
        f"  {CREDENTIALS}\n\n"
        "Create an OAuth client in Google Cloud Console:\n"
        "  1. https://console.cloud.google.com/apis/credentials\n"
        "  2. Enable the Google Calendar API for the project.\n"
        "  3. Create Credentials -> OAuth client ID -> Desktop app.\n"
        "  4. Download the JSON and save it to the path above.\n"
        "  5. Under OAuth consent screen, add your Google account\n"
        "     as a Test user (or publish the app) so consent works.\n\n"
        "Then run: obs calendar auth"
    )


def _dead_client_error(detail):
    client_id = _client_id_from_credentials() or "unknown"

    return SystemExit(
        "Google rejected the OAuth client in:\n"
        f"  {CREDENTIALS}\n"
        f"  client_id: {client_id}\n\n"
        f"Google said: {detail}\n\n"
        "This client no longer exists or is no longer authorised, so no\n"
        "stored token can be refreshed. Create a replacement client:\n"
        "  1. https://console.cloud.google.com/apis/credentials\n"
        "  2. Enable the Google Calendar API for the project.\n"
        "  3. Create Credentials -> OAuth client ID -> Desktop app.\n"
        f"  4. Overwrite {CREDENTIALS} with the downloaded JSON.\n"
        "  5. Under OAuth consent screen, add your Google account\n"
        "     as a Test user (or publish the app).\n\n"
        "Then run: obs calendar auth"
    )


def _run_consent_flow():
    """Run the interactive browser consent flow and return fresh creds."""

    if not CREDENTIALS.exists():
        raise _missing_credentials_error()

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS),
            SCOPES,
        )
    except ValueError as exc:
        raise SystemExit(
            f"Could not read Google OAuth credentials:\n"
            f"  {CREDENTIALS}\n\n"
            f"{exc}\n\n"
            "The file should be the JSON downloaded for a Desktop app\n"
            "OAuth client, containing an \"installed\" section."
        )

    if not sys.stdin.isatty():
        raise SystemExit(
            "Google Calendar needs interactive authorisation, but this\n"
            "session has no terminal attached (it may be a systemd timer\n"
            "or cron job).\n\n"
            "Run this once from a terminal, then retry:\n"
            "  obs calendar auth"
        )

    try:
        return flow.run_local_server(
            port=0,
            open_browser=True,
        )
    except Exception as exc:
        text = _oauth_error_text(exc)

        for code in FATAL_OAUTH_ERRORS:
            if code in text:
                raise _dead_client_error(code)

        raise SystemExit(
            "Google OAuth authorisation failed.\n"
            f"{exc}\n\n"
            "If a browser did not open, copy the printed URL into one\n"
            "manually. If Google reported that the app is blocked, add\n"
            "your account as a Test user on the OAuth consent screen."
        )


def authorize(force_reauth=False):
    """Obtain valid Google credentials, re-authorising when necessary."""

    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if force_reauth:
        _discard_token()

    creds = None

    # ------------------------------------------------------------
    # Load existing token
    # ------------------------------------------------------------

    if TOKEN.exists():

        # A token minted for a previous OAuth client can never be
        # refreshed against the current one. Drop it up front rather
        # than failing on an opaque invalid_client from Google.

        cred_client = _client_id_from_credentials()
        token_client = _client_id_from_token()

        if cred_client and token_client and cred_client != token_client:
            print(
                "Stored Google token belongs to a different OAuth client; "
                "re-authorising.",
                file=sys.stderr,
            )
            _discard_token()

        else:
            try:
                creds = Credentials.from_authorized_user_file(
                    str(TOKEN),
                    SCOPES,
                )
            except Exception:
                creds = None

    # ------------------------------------------------------------
    # Refresh expired token
    # ------------------------------------------------------------

    if creds and not creds.valid and creds.refresh_token:

        try:
            creds.refresh(Request())

        except Exception as exc:
            text = _oauth_error_text(exc)

            if any(code in text for code in FATAL_OAUTH_ERRORS):

                # The grant is permanently dead: the client was deleted,
                # consent was revoked, or a testing-mode refresh token
                # aged out after seven days. A stored token cannot
                # recover from any of these, so start a fresh consent
                # flow instead of exiting.

                print(
                    "Stored Google token can no longer be refreshed; "
                    "re-authorising.",
                    file=sys.stderr,
                )

                _discard_token()
                creds = None

            else:
                raise SystemExit(
                    "Could not refresh Google OAuth token.\n"
                    f"{exc}\n\n"
                    "This is usually a transient network or proxy problem.\n"
                    "If it persists, re-authorise with: obs calendar auth"
                )

    # ------------------------------------------------------------
    # First-time or repeat authentication
    # ------------------------------------------------------------

    if not creds or not creds.valid:
        creds = _run_consent_flow()

    # ------------------------------------------------------------
    # Save token
    # ------------------------------------------------------------

    atomic_write_text(
        TOKEN,
        creds.to_json(),
    )

    try:
        TOKEN.chmod(0o600)
    except OSError:
        pass

    return creds


def get_service(force_reauth=False):
    """Authenticate with Google Calendar and return an AuthorizedSession."""

    creds = authorize(
        force_reauth=force_reauth,
    )

    # ------------------------------------------------------------
    # Proxy
    # ------------------------------------------------------------

    proxy_url = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )

    session = AuthorizedSession(
        creds
    )

    if proxy_url:
        session.proxies.update(
            {
                "http": proxy_url,
                "https": proxy_url,
            }
        )

        print(
            f"Using proxy: {proxy_url}"
        )

    return session


# ================================================================
# Calendar mapping
# ================================================================

# ================================================================
# Calendar access mode
# ================================================================

def calendar_mode():
    """
    Decide how to reach the calendar.

    Returns "oauth" for full read/write access or "ics" for the read-only
    feed. OAuth wins by default when it is configured, so an existing setup
    keeps every command; the feed is the zero-setup fallback.
    """

    if CALENDAR_MODE == "ics":
        if not ICS_URL:
            raise SystemExit(
                "OBSIDIAN_CALENDAR_MODE=ics is set, but no feed URL was "
                "given.\n\n"
                "Set OBSIDIAN_CALENDAR_ICS to the calendar's "
                "\"Secret address in iCal format\".\n"
                "See: obs calendar ics"
            )
        return "ics"

    if CALENDAR_MODE == "oauth":
        return "oauth"

    if CALENDAR_MODE not in ("auto", ""):
        raise SystemExit(
            f"Unknown OBSIDIAN_CALENDAR_MODE: {CALENDAR_MODE}\n"
            "Expected one of: auto, ics, oauth"
        )

    if CREDENTIALS.exists():
        return "oauth"

    if ICS_URL:
        return "ics"

    return "unconfigured"


def require_oauth(action):
    """
    Stop a write when only the read-only feed is available.

    The iCalendar feed is a download, so there is nothing to write back to.
    """

    mode = calendar_mode()

    if mode == "oauth":
        return

    if mode == "ics":
        raise SystemExit(
            f"Cannot {action}: the calendar is in read-only feed mode.\n\n"
            "An iCalendar feed can only be read, so creating and deleting\n"
            "events needs OAuth. To enable it, create a Desktop OAuth\n"
            f"client and save it to:\n  {CREDENTIALS}\n\n"
            "Then run: obs calendar auth\n\n"
            "`obs calendar sync` and `obs calendar today` keep working in\n"
            "feed mode."
        )

    raise SystemExit(
        "No calendar access is configured.\n\n"
        "Pick one:\n"
        "  Read-only, no Google Cloud project needed:\n"
        "    obs calendar ics\n"
        "  Full read and write:\n"
        f"    save a Desktop OAuth client to {CREDENTIALS}\n"
        "    then run: obs calendar auth"
    )


def fetch_ics_text():
    """
    Download the iCalendar feed.

    Proxy settings are left to requests, which reads HTTP_PROXY/HTTPS_PROXY
    and, unlike an explicit proxies dict, also honours NO_PROXY.
    """

    try:
        response = requests.get(
            ICS_URL,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise SystemExit(
            "Could not fetch the calendar feed.\n"
            f"{exc}\n\n"
            "Check the network, and that OBSIDIAN_CALENDAR_ICS is the\n"
            "current secret address. Resetting it in Google Calendar\n"
            "invalidates the old URL."
        )

    if response.status_code == 404:
        raise SystemExit(
            "The calendar feed returned 404 (not found).\n\n"
            "The secret address may have been reset, which invalidates the\n"
            "old URL. Copy the current one from Google Calendar:\n"
            "  Settings and sharing -> Secret address in iCal format"
        )

    if not response.ok:
        raise SystemExit(
            "The calendar feed returned "
            f"HTTP {response.status_code}.\n"
            f"{response.text[:400]}"
        )

    text = response.text

    if "BEGIN:VCALENDAR" not in text:
        raise SystemExit(
            "That URL did not return an iCalendar feed.\n\n"
            "Use the \"Secret address in iCal format\", which ends in\n"
            "/basic.ics - not the calendar's web address."
        )

    return text


def fetch_events_ics(day):
    """
    Read one local day of events from the iCalendar feed.

    The window is half-open from midnight to midnight so that an all-day
    event belonging to the next day is not counted as today's.
    """

    local_tz = local_zoneinfo()

    start = dt.datetime.combine(
        day,
        dt.time.min,
        tzinfo=local_tz,
    )

    end = start + dt.timedelta(days=1)

    return ics_feed.events_in_range(
        fetch_ics_text(),
        start,
        end,
        local_tz,
    )


def read_events(day):
    """
    Read one day of events using whichever mode is configured.

    Both modes return dictionaries shaped like the Google Calendar API's,
    so callers do not need to know which one produced them.
    """

    mode = calendar_mode()

    if mode == "ics":
        return fetch_events_ics(day)

    if mode == "unconfigured":
        require_oauth("read the calendar")

    return fetch_events(
        get_service(),
        day,
    )


def mapping_path(vault):
    return (
        Path(vault)
        / "99-System"
        / "calendar"
        / "events.json"
    )


def load_mapping(vault):
    path = mapping_path(vault)

    if not path.exists():
        return {}

    try:
        return json.loads(
            path.read_text()
        )
    except json.JSONDecodeError:
        return {}


def save_mapping(vault, data):
    path = mapping_path(vault)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    atomic_write_text(
        path,
        json.dumps(
            data,
            indent=2,
            sort_keys=True,
        ),
    )


def rebuild_mapping_for_date(vault, day, events):
    """
    Replace mappings belonging to one date with the current
    Google Calendar events for that date.
    """

    mapping = load_mapping(vault)
    date_string = day.isoformat()

    mapping = {
        event_id: data
        for event_id, data in mapping.items()
        if data.get("date") != date_string
    }

    for event in events:

        event_id = event.get("id")

        if not event_id:
            continue

        mapping[event_id] = {
            "summary": event.get("summary", ""),
            "date": date_string,
            "source": "google-calendar",
        }

    save_mapping(
        vault,
        mapping,
    )


# ================================================================
# Daily notes
# ================================================================

def daily_path(vault, day):
    """
    Daily notes use:

        Daily/YYYY-MM-DD.md
    """

    return (
        Path(vault)
        / "Daily"
        / f"{day:%Y-%m-%d}.md"
    )


def ensure_daily(day_path, day):
    """
    Create a Daily note if it does not already exist.

    Existing notes are never overwritten here.
    """

    if day_path.exists():
        return day_path.read_text()

    day_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = f"""---
type: daily
date: {day:%Y-%m-%d}
---

# {day:%A, %-d %B %Y}

## Calendar

<!-- CALENDAR:START -->
<!-- CALENDAR:END -->

## Tasks

- [ ]

## Research

-

## Notes

-

## Inbox / Ideas

-

## Skill Log

### Chess

### Typing

### Other Skills

## End of Day

<!-- CLOSE:START -->
### Reflection

- Win:
- Lesson:
- Tomorrow's first priority:

### Carry Forward

- 
<!-- CLOSE:END -->
"""

    atomic_write_text(
        day_path,
        text,
    )

    return text


# ================================================================
# Google Calendar event helpers
# ================================================================

def event_start_date(event):
    start = event.get(
        "start",
        {},
    )

    # All-day event.
    if "date" in start:
        try:
            return dt.date.fromisoformat(
                start["date"]
            )
        except ValueError:
            return None

    value = start.get(
        "dateTime"
    )

    if not value:
        return None

    try:
        parsed = dt.datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    return parsed.astimezone().date()


def event_sort_key(event):
    start = event.get(
        "start",
        {}
    )

    return start.get(
        "dateTime",
        start.get(
            "date",
            "",
        ),
    )


def event_line(event):
    summary = (
        event.get("summary")
        or "(untitled)"
    )

    start = event.get(
        "start",
        {}
    )

    end = event.get(
        "end",
        {}
    )

    # ------------------------------------------------------------
    # All-day event
    # ------------------------------------------------------------

    if "date" in start:
        return (
            f"- **All day** — {summary}"
        )

    # ------------------------------------------------------------
    # Timed event
    # ------------------------------------------------------------

    start_value = start.get(
        "dateTime"
    )

    end_value = end.get(
        "dateTime"
    )

    if not start_value:
        return f"- {summary}"

    try:
        s = dt.datetime.fromisoformat(
            start_value.replace(
                "Z",
                "+00:00",
            )
        ).astimezone()
    except ValueError:
        return f"- {summary}"

    if end_value:
        try:
            e = dt.datetime.fromisoformat(
                end_value.replace(
                    "Z",
                    "+00:00",
                )
            ).astimezone()

            return (
                f"- {s:%H:%M}–{e:%H:%M} — {summary}"
            )

        except ValueError:
            pass

    return (
        f"- {s:%H:%M} — {summary}"
    )


# ================================================================
# Calendar rendering
# ================================================================

def render_calendar(vault, day, events):
    """
    Replace the managed Calendar section of a Daily note.

    Only content between the Calendar markers is managed.
    """

    path = daily_path(
        vault,
        day,
    )

    text = ensure_daily(
        path,
        day,
    )

    events = sorted(
        events,
        key=event_sort_key,
    )

    lines = [
        event_line(event)
        for event in events
    ]

    if not lines:
        lines = [
            "- No events"
        ]

    pattern = (
        r"<!-- CALENDAR:START -->"
        r".*?"
        r"<!-- CALENDAR:END -->"
    )

    replacement = (
        "<!-- CALENDAR:START -->\n"
        + "\n".join(lines)
        + "\n"
        + "<!-- CALENDAR:END -->"
    )

    new_text, count = re.subn(
        pattern,
        replacement,
        text,
        flags=re.S,
    )

    # ------------------------------------------------------------
    # Markers missing
    # ------------------------------------------------------------

    if count == 0:

        marker = "## Calendar"

        insert = (
            "\n\n"
            "<!-- CALENDAR:START -->\n"
            + "\n".join(lines)
            + "\n"
            + "<!-- CALENDAR:END -->"
        )

        if marker in text:

            new_text = text.replace(
                marker,
                marker + insert,
                1,
            )

        else:

            new_text = (
                text
                + "\n\n## Calendar"
                + insert
            )

    # ------------------------------------------------------------
    # Write only when changed
    # ------------------------------------------------------------

    if new_text != text:
        atomic_write_text(
            path,
            new_text,
        )


# ================================================================
# Fetch events
# ================================================================

def fetch_events(session, day):
    """
    Fetch all Google Calendar events for a local calendar day.
    """

    local_tz = local_zoneinfo()

    start = dt.datetime.combine(
        day,
        dt.time.min,
        tzinfo=local_tz,
    )

    end = dt.datetime.combine(
        day,
        dt.time.max,
        tzinfo=local_tz,
    )

    events = []

    page_token = None

    while True:

        params = {
            "calendarId": CALENDAR_ID,
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 2500,
        }

        if page_token:
            params["pageToken"] = page_token

        response = request_or_die(
            session.get,
            f"{CALENDAR_API}/calendars/"
            f"{CALENDAR_ID}/events",
            params=params,
            timeout=30,
        )

        if not response.ok:
            api_error(response)

        result = response.json()

        events.extend(
            result.get(
                "items",
                []
            )
        )

        page_token = result.get(
            "nextPageToken"
        )

        if not page_token:
            break

    return events


# ================================================================
# Sync
# ================================================================

def sync(vault, day=None):
    """
    Google Calendar -> Obsidian Daily note.

    Defaults to today's date.
    """

    if day is None:
        day = dt.date.today()

    events = read_events(day)

    render_calendar(
        vault,
        day,
        events,
    )

    rebuild_mapping_for_date(
        vault,
        day,
        events,
    )

    print(
        f"Synced {len(events)} Google Calendar events "
        f"into {daily_path(vault, day)}"
    )


# ================================================================
# Datetime parsing
# ================================================================

def parse_local(value):
    """
    Parse:

        YYYY-MM-DD HH:MM

    using the machine's local timezone.
    """

    try:

        parsed = dt.datetime.strptime(
            value,
            "%Y-%m-%d %H:%M",
        )

    except ValueError:

        raise SystemExit(
            f"Invalid date/time: {value}\n"
            "Expected format: YYYY-MM-DD HH:MM\n"
            "Example: 2026-09-05 20:00"
        )

    return parsed.astimezone()


# ================================================================
# Recurrence
# ================================================================

WEEKDAY_CODES = [
    "MO",
    "TU",
    "WE",
    "TH",
    "FR",
    "SA",
    "SU",
]


def recurrence_rule(
    repeat,
    start_dt,
    end_type="never",
    end_value=None,
    interval=1,
    byday=None,
):
    """Build a Google Calendar RRULE."""

    repeat = (repeat or "none").lower().strip()

    if repeat == "none":
        return None

    try:
        interval = int(interval or 1)
    except (TypeError, ValueError):
        raise SystemExit("Repeat interval must be a positive integer.")
    if interval < 1:
        raise SystemExit("Repeat interval must be at least 1.")

    if byday and repeat != "weekly":
        print(
            f"WARNING: --repeat-days is ignored for --repeat {repeat}; "
            "it only applies to weekly recurrence.",
            file=sys.stderr,
        )

    if repeat == "daily":
        rule = f"FREQ=DAILY;INTERVAL={interval}"
    elif repeat == "weekly":
        days = byday or WEEKDAY_CODES[start_dt.weekday()]
        rule = f"FREQ=WEEKLY;INTERVAL={interval};BYDAY={days}"
    elif repeat == "monthly":
        rule = f"FREQ=MONTHLY;INTERVAL={interval}"
    elif repeat == "yearly":
        rule = f"FREQ=YEARLY;INTERVAL={interval}"
    elif repeat == "weekdays":
        rule = "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR"
    elif repeat == "custom":
        raise SystemExit(
            "Custom recurrence requires a custom frequency and interval."
        )
    else:
        raise SystemExit(f"Invalid repeat option: {repeat}")

    if end_type == "date":
        try:
            until = dt.date.fromisoformat(end_value)
        except ValueError:
            raise SystemExit(
                f"Invalid repeat end date: {end_value}\n"
                "Expected format: YYYY-MM-DD"
            )
        until_dt = dt.datetime.combine(
            until, dt.time(23, 59, 59), tzinfo=start_dt.tzinfo
        ).astimezone(dt.timezone.utc)
        rule += f";UNTIL={until_dt:%Y%m%dT%H%M%SZ}"
    elif end_type == "count":
        try:
            count = int(end_value)
        except (TypeError, ValueError):
            raise SystemExit("Repeat count must be a positive integer.")
        if count < 1:
            raise SystemExit("Repeat count must be at least 1.")
        rule += f";COUNT={count}"
    elif end_type != "never":
        raise SystemExit("Invalid recurrence end option.")

    return f"RRULE:{rule}"


def prompt_custom_repeat(start_dt):
    """Interactively collect a custom recurrence."""

    print()
    print("Custom repeat:")
    print("  1. Every N days")
    print("  2. Every N weeks")
    print("  3. Every N months")
    print("  4. Every N years")

    choice = input("Custom frequency [1]: ").strip() or "1"
    frequencies = {
        "1": "daily",
        "2": "weekly",
        "3": "monthly",
        "4": "yearly",
    }
    if choice not in frequencies:
        raise SystemExit("Invalid custom frequency option.")

    repeat = frequencies[choice]
    interval_text = input("Repeat every (N) [1]: ").strip() or "1"
    try:
        interval = int(interval_text)
    except ValueError:
        raise SystemExit("Repeat interval must be a positive integer.")
    if interval < 1:
        raise SystemExit("Repeat interval must be at least 1.")

    byday = None
    if repeat == "weekly":
        print()
        print("Days of week:")
        for i, name in enumerate(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            1,
        ):
            print(f"  {i}. {name}")
        print("  Leave blank to use the event's start weekday.")
        raw = input("Days (e.g. 1,3,5): ").strip()
        if raw:
            selected = []
            for item in raw.split(","):
                item = item.strip()
                if item not in {str(i) for i in range(1, 8)}:
                    raise SystemExit("Invalid weekday. Use numbers 1-7.")
                selected.append(WEEKDAY_CODES[int(item) - 1])
            byday = ",".join(dict.fromkeys(selected))

    return repeat, interval, byday


def prompt_repeat(start_dt):
    """Interactive recurrence selection."""

    print()
    print("Repeat:")
    print("  1. Does not repeat")
    print("  2. Every day")
    print("  3. Every week")
    print("  4. Every month")
    print("  5. Every year")
    print("  6. Every weekday (Mon–Fri)")
    print("  7. Custom")

    choices = {
        "1": "none",
        "2": "daily",
        "3": "weekly",
        "4": "monthly",
        "5": "yearly",
        "6": "weekdays",
        "7": "custom",
    }

    choice = input("Repeat option [1]: ").strip() or "1"
    if choice not in choices:
        raise SystemExit("Invalid repeat option.")

    repeat = choices[choice]
    interval = 1
    byday = None

    if repeat == "none":
        return "none", "never", None, interval, byday

    if repeat == "custom":
        repeat, interval, byday = prompt_custom_repeat(start_dt)

    print()
    print("Repeat ends:")
    print("  1. Never")
    print("  2. On a date")
    print("  3. After a number of occurrences")

    end_choice = input("Ends [1]: ").strip() or "1"

    if end_choice == "1":
        return repeat, "never", None, interval, byday
    if end_choice == "2":
        end_date = input("End date (YYYY-MM-DD): ").strip()
        return repeat, "date", end_date, interval, byday
    if end_choice == "3":
        count = input("Number of occurrences: ").strip()
        return repeat, "count", count, interval, byday

    raise SystemExit("Invalid repeat end option.")


# ================================================================
# Add event
# ================================================================

def add(
    vault,
    summary,
    start,
    end,
    repeat="none",
    repeat_end="never",
    repeat_value=None,
    repeat_interval=1,
    repeat_byday=None,
):
    """
    Create a Google Calendar event.

    Then refresh the Daily note corresponding to the event's
    start date.
    """

    if not summary.strip():
        raise SystemExit(
            "Event title cannot be empty."
        )

    require_oauth("create an event")

    session = get_service()

    s = parse_local(
        start
    )

    e = parse_local(
        end
    )

    if e <= s:
        raise SystemExit(
            "Invalid event time:\n"
            "End time must be after start time."
        )

    rule = recurrence_rule(
        repeat,
        s,
        repeat_end,
        repeat_value,
        repeat_interval,
        repeat_byday,
    )

    timezone_name = local_timezone_name()

    if not timezone_name:
        print(
            "WARNING: Could not detect an IANA timezone for this machine.\n"
            "Google Calendar requires one for timed events, especially "
            "recurring ones, and may reject this request.\n"
            "Set the TZ environment variable to an IANA zone name "
            "(e.g. Asia/Kolkata) and try again if it fails.",
            file=sys.stderr,
        )

    event = {
        "summary": summary,
        "start": {
            "dateTime": s.isoformat(),
        },
        "end": {
            "dateTime": e.isoformat(),
        },
    }

    # Google Calendar requires an IANA timezone definition for recurring
    # timed events. Supplying it for all timed events also keeps the event
    # timezone explicit and consistent with the local machine timezone.
    if timezone_name:
        event["start"]["timeZone"] = timezone_name
        event["end"]["timeZone"] = timezone_name

    if rule:
        event["recurrence"] = [
            rule
        ]

    response = request_or_die(
        session.post,
        f"{CALENDAR_API}/calendars/"
        f"{CALENDAR_ID}/events",
        json=event,
        timeout=30,
    )

    if not response.ok:
        api_error(response)

    created = response.json()

    event_id = created.get(
        "id",
        "(unknown)",
    )

    print(
        f"Created Google Calendar event: "
        f"{event_id}"
    )

    # ------------------------------------------------------------
    # Sync the event's date
    # ------------------------------------------------------------

    event_day = s.date()

    events = fetch_events(
        session,
        event_day,
    )

    render_calendar(
        vault,
        event_day,
        events,
    )

    rebuild_mapping_for_date(
        vault,
        event_day,
        events,
    )

    print(
        f"Synced {len(events)} Google Calendar events "
        f"into {daily_path(vault, event_day)}"
    )


def interactive_add(vault):
    """
    Create a Google Calendar event interactively.

    Asks for:
      title
      start
      end
      repeat rule
      repeat end
    """

    require_oauth("create an event")

    print()
    print("==============================================================")
    print("                 CREATE CALENDAR EVENT")
    print("==============================================================")
    print()

    summary = input(
        "Event title: "
    ).strip()

    if not summary:
        raise SystemExit(
            "Event title cannot be empty."
        )

    start = input(
        "Start (YYYY-MM-DD HH:MM): "
    ).strip()

    end = input(
        "End   (YYYY-MM-DD HH:MM): "
    ).strip()

    # Validate the start before asking recurrence questions.
    start_dt = parse_local(
        start
    )

    # Validate the end as well.
    end_dt = parse_local(
        end
    )

    if end_dt <= start_dt:
        raise SystemExit(
            "Invalid event time:\n"
            "End time must be after start time."
        )

    (
        repeat,
        repeat_end,
        repeat_value,
        repeat_interval,
        repeat_byday,
    ) = prompt_repeat(start_dt)

    add(
        vault,
        summary,
        start,
        end,
        repeat,
        repeat_end,
        repeat_value,
        repeat_interval,
        repeat_byday,
    )


# ================================================================
# Today's tasks
# ================================================================

def extract_today_tasks(vault, day):
    """
    Read Markdown checkbox tasks from today's ## Tasks section.

    Both incomplete and completed tasks are returned.
    """

    path = daily_path(
        vault,
        day,
    )

    if not path.exists():
        return []

    text = path.read_text()

    match = re.search(
        r"^## Tasks(?:[ \t]*$|(?=- \[[ xX]\][ \t]))"
        r"(?P<section>.*?)"
        r"(?=^## |\Z)",
        text,
        flags=re.M | re.S,
    )

    if not match:
        return []

    tasks = []

    for line in match.group(
        "section"
    ).splitlines():

        stripped = line.strip()

        if re.match(
            r"^- \[([ xX])\] ",
            stripped,
        ):
            tasks.append(
                stripped
            )

    return tasks


# ================================================================
# Today's dashboard
# ================================================================

def today(vault):
    """
    Show today's Google Calendar events and today's Daily-note tasks.

    Calendar is refreshed first so the dashboard reflects the
    current Google Calendar state.
    """

    day = dt.date.today()

    events = read_events(day)

    render_calendar(
        vault,
        day,
        events,
    )

    rebuild_mapping_for_date(
        vault,
        day,
        events,
    )

    tasks = extract_today_tasks(
        vault,
        day,
    )

    print()
    print("=" * 62)
    print(
        f"Today — {day:%A, %-d %B %Y}"
    )
    print("=" * 62)

    print()
    print("CALENDAR")
    print("-" * 62)

    if events:

        for event in sorted(
            events,
            key=event_sort_key,
        ):
            print(
                event_line(event)
            )

    else:
        print("- No events")

    print()
    print("TASKS")
    print("-" * 62)

    if tasks:

        for task in tasks:
            print(task)

        print()
        print(
            f"{len(tasks)} task(s)"
        )

    else:
        print("- No tasks")


# ================================================================
# Delete event
# ================================================================

def delete(vault, event_id, assume_yes=False):
    """
    Delete a Google Calendar event.

    The event's date is determined before deletion so that
    the corresponding Daily note can be refreshed.
    """

    require_oauth("delete an event")

    session = get_service()

    # ------------------------------------------------------------
    # Find event first
    # ------------------------------------------------------------

    response = request_or_die(
        session.get,
        f"{CALENDAR_API}/calendars/"
        f"{CALENDAR_ID}/events/"
        f"{event_id}",
        timeout=30,
    )

    if response.status_code == 404:
        raise SystemExit(
            f"Google Calendar event not found: {event_id}"
        )

    if not response.ok:
        api_error(response)

    existing = response.json()

    event_day = event_start_date(
        existing
    )

    # ------------------------------------------------------------
    # Confirm before deleting a recurring series
    #
    # Deleting the master event of a recurring series removes ALL
    # occurrences, not just one. Ask before doing that irreversibly.
    # ------------------------------------------------------------

    if existing.get("recurrence") and not assume_yes:

        summary = existing.get("summary") or "(untitled)"

        print()
        print(
            "This event repeats. Deleting it removes the ENTIRE "
            "recurring series, not just one occurrence:"
        )
        print(f'  "{summary}"')

        answer = input(
            "Type 'yes' to delete the whole series: "
        ).strip().lower()

        if answer != "yes":
            print("Cancelled. No event was deleted.")
            return

    # ------------------------------------------------------------
    # Delete event
    # ------------------------------------------------------------

    response = request_or_die(
        session.delete,
        f"{CALENDAR_API}/calendars/"
        f"{CALENDAR_ID}/events/"
        f"{event_id}",
        timeout=30,
    )

    if not response.ok:
        api_error(response)

    # ------------------------------------------------------------
    # Remove mapping
    # ------------------------------------------------------------

    mapping = load_mapping(
        vault
    )

    mapping.pop(
        event_id,
        None,
    )

    save_mapping(
        vault,
        mapping,
    )

    print(
        f"Deleted Google Calendar event: "
        f"{event_id}"
    )

    # ------------------------------------------------------------
    # Refresh affected Daily note
    # ------------------------------------------------------------

    if event_day:

        events = fetch_events(
            session,
            event_day,
        )

        render_calendar(
            vault,
            event_day,
            events,
        )

        rebuild_mapping_for_date(
            vault,
            event_day,
            events,
        )

        print(
            f"Synced {len(events)} Google Calendar events "
            f"into {daily_path(vault, event_day)}"
        )


# ================================================================
# CLI
# ================================================================

def ics_check():
    """Verify the read-only feed and report what it contains."""

    text = fetch_ics_text()

    day = dt.date.today()
    events = fetch_events_ics(day)

    names = set()

    for line in ics_feed.unfold(text).split("\n"):
        name, _, value = ics_feed.split_property(line.strip())
        if name == "X-WR-CALNAME":
            names.add(ics_feed.unescape_text(value))

    print("Calendar feed OK (read-only)")

    if names:
        print(f"  calendar: {sorted(names)[0]}")

    print(f"  events today: {len(events)}")
    print("  mode:     ics")
    print()
    print("Read-only: `obs calendar add` and `obs calendar delete` need")
    print("OAuth. Run `obs calendar auth` after saving a Desktop OAuth")
    print(f"client to {CREDENTIALS}")


def auth_check(force_reauth=False):
    """Verify calendar access in whichever mode is configured."""

    mode = calendar_mode()

    if mode == "ics":
        ics_check()
        return

    if mode == "unconfigured":
        require_oauth("read the calendar")

    session = get_service(
        force_reauth=force_reauth,
    )

    # Probe the events collection rather than the calendar resource:
    # calendars.get needs the wider ".../auth/calendar" scope, while the
    # events list is covered by ".../auth/calendar.events" and reports the
    # calendar's title and timezone in the same response.
    try:
        response = session.get(
            f"{CALENDAR_API}/calendars/{CALENDAR_ID}/events",
            params={"maxResults": 1},
            timeout=30,
        )
    except Exception as exc:
        raise SystemExit(
            "Authorised, but could not reach the Google Calendar API.\n"
            f"{exc}"
        )

    if response.status_code in (401, 403):
        raise SystemExit(
            "Authorised, but Google refused the request:\n"
            f"{response.text}\n\n"
            "Two common causes:\n"
            "  1. The Google Calendar API is not enabled for the project:\n"
            "     https://console.cloud.google.com/apis/library/"
            "calendar-json.googleapis.com\n"
            "  2. The stored token was granted a different scope than the\n"
            "     one now requested. Re-consent with:\n"
            "       obs calendar auth --reset"
        )

    if response.status_code != 200:
        raise SystemExit(
            "Authorised, but the Google Calendar API returned "
            f"HTTP {response.status_code}:\n"
            f"{response.text}"
        )

    calendar = response.json()

    print("Google Calendar authorisation OK")
    print(f"  calendar: {calendar.get('summary', CALENDAR_ID)}")
    print(f"  timezone: {calendar.get('timeZone', 'unknown')}")
    print(f"  token:    {TOKEN}")
    print("  mode:     oauth (read and write)")


def ics_help():
    """Explain the read-only feed mode and report the current state."""

    mode = calendar_mode()

    print("Read-only calendar access (no Google Cloud project needed)")
    print()

    if ICS_URL:
        shown = ICS_URL

        # The token in the URL is a credential; show only enough of it to
        # confirm which feed is configured.
        if len(shown) > 60:
            shown = shown[:40] + "..." + shown[-14:]

        print(f"  configured feed: {shown}")
        print(f"  active mode:     {mode}")

        if mode == "oauth":
            print()
            print("  OAuth credentials are present, so OAuth is being used")
            print("  (it also supports add and delete). To force the feed:")
            print("    OBSIDIAN_CALENDAR_MODE=ics obs calendar today")

        print()
        print("Verify it with: obs calendar auth")
        return

    print("No feed is configured. To set one up:")
    print()
    print("  1. Open Google Calendar in a browser.")
    print("  2. Hover the calendar in the left sidebar, then")
    print("     three dots -> Settings and sharing.")
    print("  3. Scroll to Integrate calendar.")
    print("  4. Copy \"Secret address in iCal format\" (ends in .ics).")
    print("  5. Add it to your shell profile or")
    print(f"     {CONFIG_DIR / 'config.env'}:")
    print()
    print("       export OBSIDIAN_CALENDAR_ICS='<the URL>'")
    print()
    print("  6. Verify with: obs calendar auth")
    print()
    print("That URL is a password: anyone holding it can read the")
    print("calendar. Reset it from the same screen if it leaks.")
    print()
    print("Feed mode supports `obs calendar sync` and")
    print("`obs calendar today`. Creating and deleting events needs OAuth.")


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Google Calendar integration "
            "for Obsidian Research OS"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # ------------------------------------------------------------
    # auth
    # ------------------------------------------------------------

    p = sub.add_parser(
        "ics",
        help="Show how to set up read-only feed access",
    )

    p = sub.add_parser(
        "auth",
        help="Authorise (or re-authorise) Google Calendar access",
    )

    p.add_argument(
        "--reset",
        action="store_true",
        help="Discard the stored token and force a fresh consent flow",
    )

    # ------------------------------------------------------------
    # sync
    # ------------------------------------------------------------

    p = sub.add_parser(
        "sync",
        help="Sync Google Calendar events",
    )

    p.add_argument(
        "--vault",
        required=True,
    )

    p.add_argument(
        "--date",
        help="YYYY-MM-DD; defaults to today",
    )

    # ------------------------------------------------------------
    # today
    # ------------------------------------------------------------

    p = sub.add_parser(
        "today",
        help="Show today's calendar and tasks",
    )

    p.add_argument(
        "--vault",
        required=True,
    )

    # ------------------------------------------------------------
    # add
    # ------------------------------------------------------------

    p = sub.add_parser(
        "add",
        help="Create a Google Calendar event",
    )

    p.add_argument(
        "--vault",
        required=True,
    )

    p.add_argument(
        "summary",
        nargs="?",
    )

    p.add_argument(
        "start",
        nargs="?",
        help="YYYY-MM-DD HH:MM",
    )

    p.add_argument(
        "end",
        nargs="?",
        help="YYYY-MM-DD HH:MM",
    )

    p.add_argument(
        "--repeat",
        choices=[
            "none",
            "daily",
            "weekly",
            "monthly",
            "yearly",
            "weekdays",
            "custom",
        ],
        default="none",
        help="Repeat rule",
    )

    p.add_argument(
        "--repeat-until",
        help="End recurrence on YYYY-MM-DD",
    )

    p.add_argument(
        "--repeat-count",
        type=int,
        help="End recurrence after N occurrences",
    )

    p.add_argument(
        "--repeat-interval",
        type=int,
        default=1,
        help="Repeat every N units for daily/weekly/monthly/yearly",
    )

    p.add_argument(
        "--repeat-days",
        help="Comma-separated weekdays for weekly recurrence, e.g. MO,WE,FR",
    )

    p.add_argument(
        "--repeat-frequency",
        choices=["daily", "weekly", "monthly", "yearly"],
        help="Custom recurrence frequency when --repeat custom is used",
    )

    # ------------------------------------------------------------
    # delete
    # ------------------------------------------------------------

    p = sub.add_parser(
        "delete",
        help="Delete a Google Calendar event",
    )

    p.add_argument(
        "--vault",
        required=True,
    )

    p.add_argument(
        "event_id",
    )

    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation when deleting a recurring event series",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------

    if args.command == "ics":

        ics_help()

    elif args.command == "auth":

        auth_check(
            force_reauth=args.reset,
        )

    # ------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------

    elif args.command == "sync":

        day = None

        if args.date:

            try:
                day = dt.date.fromisoformat(
                    args.date
                )

            except ValueError:

                raise SystemExit(
                    f"Invalid date: {args.date}\n"
                    "Expected format: YYYY-MM-DD\n"
                    "Example: 2026-09-05"
                )

        sync(
            args.vault,
            day,
        )

    # ------------------------------------------------------------
    # Today
    # ------------------------------------------------------------

    elif args.command == "today":

        today(
            args.vault
        )

    # ------------------------------------------------------------
    # Add
    # ------------------------------------------------------------

    elif args.command == "add":

        if not args.summary:

            interactive_add(
                args.vault
            )

        elif not args.start or not args.end:

            raise SystemExit(
                "Usage:\n"
                "  obs calendar add\n"
                "  obs calendar add "
                "\"Title\" "
                "\"YYYY-MM-DD HH:MM\" "
                "\"YYYY-MM-DD HH:MM\""
            )

        else:

            if (
                args.repeat_until
                and args.repeat_count
            ):
                raise SystemExit(
                    "Use either --repeat-until "
                    "or --repeat-count, not both."
                )

            repeat_end = "never"
            repeat_value = None

            if args.repeat_until:

                repeat_end = "date"
                repeat_value = args.repeat_until

            elif args.repeat_count:

                repeat_end = "count"
                repeat_value = args.repeat_count

            repeat_mode = args.repeat
            if repeat_mode == "custom":
                if not args.repeat_frequency:
                    raise SystemExit(
                        "--repeat custom requires --repeat-frequency "
                        "daily, weekly, monthly, or yearly."
                    )
                repeat_mode = args.repeat_frequency

            add(
                args.vault,
                args.summary,
                args.start,
                args.end,
                repeat_mode,
                repeat_end,
                repeat_value,
                args.repeat_interval,
                args.repeat_days,
            )

    # ------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------

    elif args.command == "delete":

        delete(
            args.vault,
            args.event_id,
            args.yes,
        )


if __name__ == "__main__":
    main()
