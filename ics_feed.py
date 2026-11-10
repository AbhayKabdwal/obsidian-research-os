#!/usr/bin/env python3

"""
Read-only calendar access through an iCalendar (.ics) feed.

Google Calendar publishes a per-calendar private feed under
Settings and sharing -> "Secret address in iCal format". Fetching it needs
no OAuth client, no Google Cloud project and no consent screen: the random
token in the URL is the credential.

This module turns such a feed into event dictionaries shaped like the Google
Calendar API's, so the rest of the tool can render them unchanged:

    {
        "id":      "<uid>",
        "summary": "Group meeting",
        "start":   {"dateTime": "2026-11-10T09:30:00+05:30"},
        "end":     {"dateTime": "2026-11-10T10:30:00+05:30"},
    }

All-day events use {"date": "2026-11-10"} instead, exactly as the API does.

The feed is read-only, so creating and deleting events still needs OAuth.
"""

import datetime as dt
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# Guard against pathological feeds: a daily event starting years before the
# requested window should not spin forever while being expanded.
MAX_OCCURRENCES = 10000

WEEKDAYS = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}


# ================================================================
# Lexing
# ================================================================

def unfold(text):
    """
    Undo RFC 5545 line folding.

    Long content lines are split with CRLF followed by a single space or
    tab. Joining them back together has to happen before anything else is
    parsed, or long summaries and RRULEs arrive truncated.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    return re.sub(
        r"\n[ \t]",
        "",
        text,
    )


def split_property(line):
    """
    Split one content line into (name, params, value).

    A line looks like NAME;PARAM=VALUE;PARAM=VALUE:actual value, and the
    value itself may contain colons, so only the first one separates.
    """

    if ":" not in line:
        return None, {}, ""

    head, _, value = line.partition(":")
    parts = head.split(";")
    name = parts[0].strip().upper()

    params = {}

    for param in parts[1:]:
        if "=" in param:
            key, _, raw = param.partition("=")
            params[key.strip().upper()] = raw.strip()

    return name, params, value


def unescape_text(value):
    """Decode the backslash escapes RFC 5545 uses in text values."""

    out = []
    i = 0

    while i < len(value):
        char = value[i]

        if char == "\\" and i + 1 < len(value):
            nxt = value[i + 1]

            if nxt in ("n", "N"):
                out.append("\n")
            elif nxt in ("\\", ";", ","):
                out.append(nxt)
            else:
                out.append(nxt)

            i += 2
            continue

        out.append(char)
        i += 1

    return "".join(out)


# ================================================================
# Dates and times
# ================================================================

def parse_ics_datetime(value, params, default_tz):
    """
    Parse a DTSTART/DTEND/EXDATE value.

    Returns (value, is_all_day) where value is a date for an all-day entry
    and an aware datetime otherwise. Three forms appear in practice:

        DTSTART;VALUE=DATE:20261110              an all-day event
        DTSTART:20261110T093000Z                 UTC
        DTSTART;TZID=Asia/Kolkata:20261110T0930  a named zone

    A datetime with no zone and no trailing Z is "floating": the spec says
    to read it in the viewer's own timezone.
    """

    value = value.strip()

    if not value:
        return None, False

    if params.get("VALUE", "").upper() == "DATE" or (
        len(value) == 8 and "T" not in value
    ):
        try:
            return (
                dt.datetime.strptime(value, "%Y%m%d").date(),
                True,
            )
        except ValueError:
            return None, False

    is_utc = value.endswith("Z")
    naked = value[:-1] if is_utc else value

    try:
        stamp = dt.datetime.strptime(naked, "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            stamp = dt.datetime.strptime(naked, "%Y%m%dT%H%M")
        except ValueError:
            return None, False

    if is_utc:
        return stamp.replace(tzinfo=dt.timezone.utc), False

    tzid = params.get("TZID")

    if tzid:
        try:
            return stamp.replace(tzinfo=ZoneInfo(tzid)), False
        except (ZoneInfoNotFoundError, ValueError):
            pass

    return stamp.replace(tzinfo=default_tz), False


def parse_until(value, default_tz):
    """Parse an RRULE UNTIL value, which may be a date or a datetime."""

    stamp, _ = parse_ics_datetime(value, {}, default_tz)

    if isinstance(stamp, dt.date) and not isinstance(stamp, dt.datetime):
        return dt.datetime.combine(
            stamp,
            dt.time.max,
            tzinfo=default_tz,
        )

    return stamp


def parse_rrule(value):
    """Turn an RRULE value into a dict of its parts."""

    rule = {}

    for chunk in value.split(";"):
        if "=" not in chunk:
            continue

        key, _, raw = chunk.partition("=")
        rule[key.strip().upper()] = raw.strip()

    return rule


# ================================================================
# Parsing
# ================================================================

def parse_events(text, default_tz=None):
    """
    Pull raw VEVENT records out of a feed.

    Everything else (VTIMEZONE, VALARM, VTODO) is skipped. The records come
    back as plain dicts so recurrence expansion can stay separate and
    testable.
    """

    if default_tz is None:
        default_tz = dt.datetime.now().astimezone().tzinfo

    events = []
    current = None
    depth_other = 0

    for line in unfold(text).split("\n"):
        line = line.strip()

        if not line:
            continue

        name, params, value = split_property(line)

        if name == "BEGIN":
            kind = value.strip().upper()

            if kind == "VEVENT":
                current = {"exdates": [], "uid": None}
            elif current is not None:
                # A VALARM nested inside this event: ignore its properties
                # so they cannot overwrite the event's own.
                depth_other += 1

            continue

        if name == "END":
            kind = value.strip().upper()

            if kind == "VEVENT":
                if current is not None:
                    events.append(current)
                current = None
            elif depth_other > 0:
                depth_other -= 1

            continue

        if current is None or depth_other > 0:
            continue

        if name == "SUMMARY":
            current["summary"] = unescape_text(value)

        elif name == "DESCRIPTION":
            current["description"] = unescape_text(value)

        elif name == "LOCATION":
            current["location"] = unescape_text(value)

        elif name == "UID":
            current["uid"] = value.strip()

        elif name == "STATUS":
            current["status"] = value.strip().upper()

        elif name == "RECURRENCE-ID":
            stamp, _ = parse_ics_datetime(value, params, default_tz)
            current["recurrence_id"] = stamp

        elif name == "DTSTART":
            stamp, all_day = parse_ics_datetime(value, params, default_tz)
            current["start"] = stamp
            current["all_day"] = all_day

        elif name == "DTEND":
            stamp, _ = parse_ics_datetime(value, params, default_tz)
            current["end"] = stamp

        elif name == "DURATION":
            current["duration"] = parse_duration(value)

        elif name == "RRULE":
            current["rrule"] = parse_rrule(value)

        elif name == "EXDATE":
            for piece in value.split(","):
                stamp, _ = parse_ics_datetime(piece, params, default_tz)
                if stamp is not None:
                    current["exdates"].append(stamp)

    return [e for e in events if e.get("start") is not None]


def parse_duration(value):
    """Parse an RFC 5545 DURATION such as PT1H30M or P2D."""

    match = re.fullmatch(
        r"(?P<sign>[+-])?P"
        r"(?:(?P<weeks>\d+)W)?"
        r"(?:(?P<days>\d+)D)?"
        r"(?:T(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?"
        r"(?:(?P<seconds>\d+)S)?)?",
        value.strip().upper(),
    )

    if not match:
        return None

    parts = {
        key: int(val)
        for key, val in match.groupdict().items()
        if key != "sign" and val
    }

    if not parts:
        return None

    delta = dt.timedelta(
        weeks=parts.get("weeks", 0),
        days=parts.get("days", 0),
        hours=parts.get("hours", 0),
        minutes=parts.get("minutes", 0),
        seconds=parts.get("seconds", 0),
    )

    if match.group("sign") == "-":
        return -delta

    return delta


# ================================================================
# Recurrence
# ================================================================

def add_months(stamp, months):
    """Shift a date or datetime by whole months, clamping the day."""

    month_index = stamp.month - 1 + months
    year = stamp.year + month_index // 12
    month = month_index % 12 + 1

    day = min(stamp.day, days_in_month(year, month))

    return stamp.replace(year=year, month=month, day=day)


def days_in_month(year, month):
    if month == 12:
        following = dt.date(year + 1, 1, 1)
    else:
        following = dt.date(year, month + 1, 1)

    return (following - dt.date(year, month, 1)).days


def event_span(event):
    """
    How long one occurrence lasts.

    Used to decide overlap: the API's timeMin/timeMax select events that
    intersect the window, so an event that began before it but is still
    running counts as inside.
    """

    start = event["start"]
    end = event.get("end")
    duration = event.get("duration")

    if end is not None and type(end) is type(start):
        span = end - start
        if span > dt.timedelta(0):
            return span

    if duration is not None and duration > dt.timedelta(0):
        return duration

    if event.get("all_day", False):
        return dt.timedelta(days=1)

    return dt.timedelta(0)


def overlaps(candidate, span, lower, upper):
    """True when [candidate, candidate+span) intersects [lower, upper)."""

    if candidate >= upper:
        return False

    # A zero-length event is treated as covering its own instant, so one
    # landing exactly on the lower bound still counts.
    if span == dt.timedelta(0):
        return candidate >= lower

    return candidate + span > lower


def expand_occurrences(event, lower, upper, default_tz, span=None):
    """
    List the start times of one event that intersect [lower, upper).

    A non-recurring event contributes at most itself. A recurring one is
    walked forward from DTSTART; only FREQ, INTERVAL, COUNT, UNTIL and
    WEEKLY's BYDAY are honoured, which covers the repeats Google Calendar's
    own UI creates. Anything more exotic falls back to the single start,
    which under-reports rather than inventing events.
    """

    start = event["start"]
    rule = event.get("rrule")

    if span is None:
        span = event_span(event)

    if not rule:
        if overlaps(start, span, lower, upper):
            return [start]
        return []

    freq = rule.get("FREQ", "").upper()

    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        if overlaps(start, span, lower, upper):
            return [start]
        return []

    try:
        interval = max(1, int(rule.get("INTERVAL", "1")))
    except ValueError:
        interval = 1

    count = None

    if "COUNT" in rule:
        try:
            count = max(0, int(rule["COUNT"]))
        except ValueError:
            count = None

    until = None

    if "UNTIL" in rule:
        until = parse_until(rule["UNTIL"], default_tz)

        if until is not None and isinstance(start, dt.datetime):
            if until.tzinfo is None:
                until = until.replace(tzinfo=default_tz)
        elif until is not None and not isinstance(start, dt.datetime):
            until = until.date()

    bydays = []

    if freq == "WEEKLY" and "BYDAY" in rule:
        for token in rule["BYDAY"].split(","):
            token = token.strip().upper()[-2:]
            if token in WEEKDAYS:
                bydays.append(WEEKDAYS[token])

    occurrences = []
    emitted = 0
    cursor = start
    steps = 0

    while steps < MAX_OCCURRENCES:
        steps += 1

        if freq == "WEEKLY" and bydays:
            # Emit each requested weekday within the cursor's week.
            week_start = cursor - dt.timedelta(days=cursor.weekday())
            candidates = [
                week_start + dt.timedelta(days=offset)
                for offset in sorted(bydays)
            ]
        else:
            candidates = [cursor]

        for candidate in candidates:
            if candidate < start:
                continue

            if until is not None and candidate > until:
                return occurrences

            if count is not None and emitted >= count:
                return occurrences

            # COUNT and UNTIL are counted over the whole series, not just
            # the queried window, so this has to happen before the window
            # test below.
            emitted += 1

            if candidate >= upper:
                return occurrences

            if overlaps(candidate, span, lower, upper):
                occurrences.append(candidate)

        if freq == "DAILY":
            cursor = cursor + dt.timedelta(days=interval)
        elif freq == "WEEKLY":
            cursor = cursor + dt.timedelta(weeks=interval)
        elif freq == "MONTHLY":
            cursor = add_months(cursor, interval)
        else:
            cursor = add_months(cursor, 12 * interval)

        if cursor >= upper:
            break

    return occurrences


# ================================================================
# Public surface
# ================================================================

def to_api_shape(event, start_value, default_tz):
    """Render one occurrence the way the Google Calendar API would."""

    all_day = event.get("all_day", False)

    if all_day:
        end_value = start_value + dt.timedelta(days=1)

        original_end = event.get("end")
        duration = event.get("duration")

        if isinstance(original_end, dt.date) and not isinstance(
            original_end, dt.datetime
        ):
            span = original_end - event["start"]
            if span.days >= 1:
                end_value = start_value + span
        elif duration is not None and duration.days >= 1:
            end_value = start_value + duration

        shaped = {
            "start": {"date": start_value.isoformat()},
            "end": {"date": end_value.isoformat()},
        }

    else:
        end_value = None
        original_end = event.get("end")
        duration = event.get("duration")

        if isinstance(original_end, dt.datetime):
            end_value = start_value + (original_end - event["start"])
        elif duration is not None:
            end_value = start_value + duration

        shaped = {
            "start": {"dateTime": start_value.isoformat()},
        }

        if end_value is not None:
            shaped["end"] = {"dateTime": end_value.isoformat()}
        else:
            shaped["end"] = {}

    shaped["id"] = event.get("uid") or "(ics)"

    if event.get("summary"):
        shaped["summary"] = event["summary"]

    if event.get("description"):
        shaped["description"] = event["description"]

    if event.get("location"):
        shaped["location"] = event["location"]

    return shaped


def events_in_range(text, start, end, default_tz=None):
    """
    Parse a feed and return the events overlapping [start, end).

    `start` and `end` are aware datetimes. The result is sorted the way the
    API's orderBy=startTime returns them, so callers can treat both sources
    identically.
    """

    if default_tz is None:
        default_tz = dt.datetime.now().astimezone().tzinfo

    # For all-day entries the comparison happens in whole dates. The upper
    # bound stays exclusive, so a window of one day does not pull in the
    # following day's all-day event.
    window_start_date = start.astimezone(default_tz).date()
    window_end_date = end.astimezone(default_tz).date()

    shaped = []
    overrides = {}

    parsed = parse_events(text, default_tz)

    # RECURRENCE-ID records replace one instance of a series. Collect them
    # first so the generated instance can be dropped.
    for event in parsed:
        if event.get("recurrence_id") is not None and event.get("uid"):
            overrides[(event["uid"], event["recurrence_id"])] = event

    for event in parsed:
        if event.get("status") == "CANCELLED":
            continue

        all_day = event.get("all_day", False)

        if all_day:
            window_a = window_start_date
            window_b = window_end_date
        else:
            window_a = start
            window_b = end

        span = event_span(event)

        occurrences = expand_occurrences(
            event,
            window_a,
            window_b,
            default_tz,
            span,
        )

        excluded = set(event.get("exdates") or [])

        for occurrence in occurrences:
            if occurrence in excluded:
                continue

            if event.get("recurrence_id") is None and event.get("uid"):
                if (event["uid"], occurrence) in overrides:
                    continue

            shaped.append(
                to_api_shape(event, occurrence, default_tz)
            )

    def sort_key(item):
        value = (
            item["start"].get("dateTime")
            or item["start"].get("date")
            or ""
        )
        # Date-only values sort before same-day timed ones, which matches
        # how the API orders an all-day event against a timed one.
        return (value[:10], len(value), value)

    shaped.sort(key=sort_key)

    return shaped
