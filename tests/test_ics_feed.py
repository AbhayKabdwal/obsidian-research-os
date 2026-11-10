#!/usr/bin/env python3

"""Tests for the read-only iCalendar feed parser."""

import datetime as dt
import os
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

import ics_feed  # noqa: E402


IST = ZoneInfo("Asia/Kolkata")


def feed(*blocks):
    """Wrap VEVENT blocks in a minimal VCALENDAR."""

    body = "\r\n".join(blocks)

    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Test//EN\r\n"
        f"{body}\r\n"
        "END:VCALENDAR\r\n"
    )


def window(day, tz=IST):
    """A whole-day window, as calendar_sync builds it."""

    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    end = start + dt.timedelta(days=1)

    return start, end


class TestUnfolding(unittest.TestCase):

    def test_folded_lines_are_rejoined(self):
        text = "SUMMARY:A very long\r\n  title\r\n"

        self.assertEqual(
            ics_feed.unfold(text).strip(),
            "SUMMARY:A very long title",
        )

    def test_tab_continuation_is_rejoined(self):
        text = "SUMMARY:split\r\n\there\r\n"

        self.assertEqual(
            ics_feed.unfold(text).strip(),
            "SUMMARY:splithere",
        )

    def test_folded_summary_survives_parsing(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:fold-1\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261110T103000\r\n"
            "SUMMARY:Reading group on retrieval\r\n  ranking methods\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["summary"],
            "Reading group on retrieval ranking methods",
        )


class TestPropertySplitting(unittest.TestCase):

    def test_value_may_contain_colons(self):
        name, params, value = ics_feed.split_property(
            "SUMMARY:Talk: part 2"
        )

        self.assertEqual(name, "SUMMARY")
        self.assertEqual(value, "Talk: part 2")
        self.assertEqual(params, {})

    def test_parameters_are_collected(self):
        name, params, value = ics_feed.split_property(
            "DTSTART;TZID=Asia/Kolkata;VALUE=DATE-TIME:20261110T093000"
        )

        self.assertEqual(name, "DTSTART")
        self.assertEqual(params["TZID"], "Asia/Kolkata")
        self.assertEqual(params["VALUE"], "DATE-TIME")
        self.assertEqual(value, "20261110T093000")

    def test_escapes_are_decoded(self):
        self.assertEqual(
            ics_feed.unescape_text(r"Line one\nLine two\, and\; more"),
            "Line one\nLine two, and; more",
        )


class TestDateParsing(unittest.TestCase):

    def test_utc_datetime(self):
        stamp, all_day = ics_feed.parse_ics_datetime(
            "20261110T040000Z", {}, IST
        )

        self.assertFalse(all_day)
        self.assertEqual(stamp.tzinfo, dt.timezone.utc)
        self.assertEqual(stamp.hour, 4)

    def test_named_zone(self):
        stamp, all_day = ics_feed.parse_ics_datetime(
            "20261110T093000", {"TZID": "Asia/Kolkata"}, IST
        )

        self.assertFalse(all_day)
        self.assertEqual(stamp.hour, 9)
        self.assertEqual(stamp.utcoffset(), dt.timedelta(hours=5, minutes=30))

    def test_all_day_value_date(self):
        stamp, all_day = ics_feed.parse_ics_datetime(
            "20261110", {"VALUE": "DATE"}, IST
        )

        self.assertTrue(all_day)
        self.assertEqual(stamp, dt.date(2026, 11, 10))

    def test_bare_eight_digits_is_all_day(self):
        stamp, all_day = ics_feed.parse_ics_datetime("20261110", {}, IST)

        self.assertTrue(all_day)
        self.assertEqual(stamp, dt.date(2026, 11, 10))

    def test_floating_time_uses_default_zone(self):
        stamp, _ = ics_feed.parse_ics_datetime(
            "20261110T093000", {}, IST
        )

        self.assertEqual(stamp.tzinfo, IST)

    def test_unparseable_value_is_ignored(self):
        stamp, _ = ics_feed.parse_ics_datetime("not-a-date", {}, IST)

        self.assertIsNone(stamp)

    def test_duration_parsing(self):
        self.assertEqual(
            ics_feed.parse_duration("PT1H30M"),
            dt.timedelta(hours=1, minutes=30),
        )
        self.assertEqual(
            ics_feed.parse_duration("P2D"),
            dt.timedelta(days=2),
        )


class TestSingleEvents(unittest.TestCase):

    def test_timed_event_shaped_like_the_api(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:one\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261110T103000\r\n"
            "SUMMARY:Group meeting\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["id"], "one")
        self.assertEqual(event["summary"], "Group meeting")
        self.assertIn("dateTime", event["start"])
        self.assertNotIn("date", event["start"])
        self.assertTrue(event["start"]["dateTime"].startswith("2026-11-10T09:30"))
        self.assertTrue(event["end"]["dateTime"].startswith("2026-11-10T10:30"))

    def test_all_day_event_uses_date_key(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:holiday\r\n"
            "DTSTART;VALUE=DATE:20261110\r\n"
            "DTEND;VALUE=DATE:20261111\r\n"
            "SUMMARY:Institute holiday\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["start"], {"date": "2026-11-10"})
        self.assertNotIn("dateTime", events[0]["start"])

    def test_event_outside_the_window_is_dropped(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:later\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261125T093000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261125T103000\r\n"
            "SUMMARY:Much later\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )

    def test_duration_supplies_the_end(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:dur\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "DURATION:PT45M\r\n"
            "SUMMARY:Standup\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertTrue(
            events[0]["end"]["dateTime"].startswith("2026-11-10T10:15")
        )

    def test_cancelled_event_is_skipped(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:gone\r\n"
            "STATUS:CANCELLED\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "SUMMARY:Called off\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )

    def test_valarm_does_not_leak_into_the_event(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:alarmed\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "SUMMARY:Real title\r\n"
            "BEGIN:VALARM\r\n"
            "ACTION:DISPLAY\r\n"
            "SUMMARY:Reminder noise\r\n"
            "END:VALARM\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(events[0]["summary"], "Real title")

    def test_missing_dtstart_is_ignored(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:broken\r\n"
            "SUMMARY:No start time\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )


class TestWindowOverlap(unittest.TestCase):
    """The API's timeMin/timeMax select events that intersect the window."""

    def test_event_running_into_the_window_is_kept(self):
        # 23:00 yesterday to 01:00 today overlaps today.
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:overnight\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261109T230000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261110T010000\r\n"
            "SUMMARY:Overnight run\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["summary"], "Overnight run")

    def test_event_ending_exactly_at_window_start_is_excluded(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:touching\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261109T220000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261110T000000\r\n"
            "SUMMARY:Ends at midnight\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )

    def test_tomorrows_all_day_event_is_not_included(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:tomorrow\r\n"
            "DTSTART;VALUE=DATE:20261111\r\n"
            "DTEND;VALUE=DATE:20261112\r\n"
            "SUMMARY:Tomorrow only\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )

    def test_multi_day_all_day_event_spanning_the_window_is_kept(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:conference\r\n"
            "DTSTART;VALUE=DATE:20261109\r\n"
            "DTEND;VALUE=DATE:20261112\r\n"
            "SUMMARY:Conference\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["summary"], "Conference")

    def test_recurring_instance_outside_window_is_excluded(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:weekly-miss\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261103T140000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261103T150000\r\n"
            "RRULE:FREQ=WEEKLY\r\n"
            "SUMMARY:Tuesdays\r\n"
            "END:VEVENT"
        )

        # Wednesday has no instance.
        start, end = window(dt.date(2026, 11, 11))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST),
            [],
        )


class TestRecurrence(unittest.TestCase):

    def test_daily_rule_hits_a_later_day(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:daily\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "DTEND;TZID=Asia/Kolkata:20261101T100000\r\n"
            "RRULE:FREQ=DAILY\r\n"
            "SUMMARY:Daily standup\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertTrue(
            events[0]["start"]["dateTime"].startswith("2026-11-10T09:30")
        )

    def test_interval_skips_days(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:alt\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "RRULE:FREQ=DAILY;INTERVAL=2\r\n"
            "SUMMARY:Every other day\r\n"
            "END:VEVENT"
        )

        # 1 Nov + 2n lands on odd days, so the 10th has nothing.
        start, end = window(dt.date(2026, 11, 10))
        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST), []
        )

        start, end = window(dt.date(2026, 11, 11))
        self.assertEqual(
            len(ics_feed.events_in_range(text, start, end, IST)), 1
        )

    def test_weekly_byday(self):
        # 2026-11-10 is a Tuesday.
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:weekly\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261103T140000\r\n"
            "RRULE:FREQ=WEEKLY;BYDAY=TU,TH\r\n"
            "SUMMARY:Lecture\r\n"
            "END:VEVENT"
        )

        for day, expected in (
            (dt.date(2026, 11, 10), 1),   # Tuesday
            (dt.date(2026, 11, 12), 1),   # Thursday
            (dt.date(2026, 11, 11), 0),   # Wednesday
        ):
            start, end = window(day)
            self.assertEqual(
                len(ics_feed.events_in_range(text, start, end, IST)),
                expected,
                f"wrong count for {day}",
            )

    def test_count_limits_the_series(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:counted\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "RRULE:FREQ=DAILY;COUNT=3\r\n"
            "SUMMARY:Three only\r\n"
            "END:VEVENT"
        )

        # 1, 2, 3 Nov only.
        start, end = window(dt.date(2026, 11, 3))
        self.assertEqual(
            len(ics_feed.events_in_range(text, start, end, IST)), 1
        )

        start, end = window(dt.date(2026, 11, 4))
        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST), []
        )

    def test_until_stops_the_series(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:untilled\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "RRULE:FREQ=DAILY;UNTIL=20261105T000000Z\r\n"
            "SUMMARY:Stops early\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST), []
        )

    def test_exdate_removes_one_instance(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:skipper\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "RRULE:FREQ=DAILY\r\n"
            "EXDATE;TZID=Asia/Kolkata:20261110T093000\r\n"
            "SUMMARY:Daily but not the 10th\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        self.assertEqual(
            ics_feed.events_in_range(text, start, end, IST), []
        )

        start, end = window(dt.date(2026, 11, 9))
        self.assertEqual(
            len(ics_feed.events_in_range(text, start, end, IST)), 1
        )

    def test_monthly_clamps_short_months(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:monthly\r\n"
            "DTSTART;TZID=Asia/Kolkata:20260131T090000\r\n"
            "RRULE:FREQ=MONTHLY\r\n"
            "SUMMARY:Month end\r\n"
            "END:VEVENT"
        )

        # February has no 31st; the day clamps to the 28th.
        start, end = window(dt.date(2026, 2, 28))
        self.assertEqual(
            len(ics_feed.events_in_range(text, start, end, IST)), 1
        )

    def test_unsupported_freq_falls_back_to_one_instance(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:hourly\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T093000\r\n"
            "RRULE:FREQ=HOURLY;COUNT=5\r\n"
            "SUMMARY:Hourly thing\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        # Under-reporting is the safe failure: one instance, not five.
        self.assertEqual(len(events), 1)

    def test_recurrence_id_override_replaces_the_instance(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:series\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261101T093000\r\n"
            "RRULE:FREQ=DAILY\r\n"
            "SUMMARY:Normal title\r\n"
            "END:VEVENT",
            "BEGIN:VEVENT\r\n"
            "UID:series\r\n"
            "RECURRENCE-ID;TZID=Asia/Kolkata:20261110T093000\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T110000\r\n"
            "SUMMARY:Moved and renamed\r\n"
            "END:VEVENT",
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["summary"], "Moved and renamed")
        self.assertTrue(
            events[0]["start"]["dateTime"].startswith("2026-11-10T11:00")
        )


class TestOrdering(unittest.TestCase):

    def test_results_are_sorted_by_start(self):
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:late\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T160000\r\n"
            "SUMMARY:Afternoon\r\n"
            "END:VEVENT",
            "BEGIN:VEVENT\r\n"
            "UID:early\r\n"
            "DTSTART;TZID=Asia/Kolkata:20261110T090000\r\n"
            "SUMMARY:Morning\r\n"
            "END:VEVENT",
            "BEGIN:VEVENT\r\n"
            "UID:allday\r\n"
            "DTSTART;VALUE=DATE:20261110\r\n"
            "SUMMARY:All day\r\n"
            "END:VEVENT",
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(
            [e["summary"] for e in events],
            ["All day", "Morning", "Afternoon"],
        )


class TestRobustness(unittest.TestCase):

    def test_empty_feed(self):
        start, end = window(dt.date(2026, 11, 10))

        self.assertEqual(
            ics_feed.events_in_range(feed(), start, end, IST),
            [],
        )

    def test_garbage_input_does_not_raise(self):
        start, end = window(dt.date(2026, 11, 10))

        for junk in ("", "not an ics file", "BEGIN:VEVENT", "<html>hi</html>"):
            self.assertEqual(
                ics_feed.events_in_range(junk, start, end, IST),
                [],
                f"junk input produced events: {junk!r}",
            )

    def test_long_running_daily_series_is_bounded(self):
        # A daily event starting in 2010 must not hang when queried in 2026.
        text = feed(
            "BEGIN:VEVENT\r\n"
            "UID:ancient\r\n"
            "DTSTART;TZID=Asia/Kolkata:20100101T090000\r\n"
            "RRULE:FREQ=DAILY\r\n"
            "SUMMARY:Since forever\r\n"
            "END:VEVENT"
        )

        start, end = window(dt.date(2026, 11, 10))
        events = ics_feed.events_in_range(text, start, end, IST)

        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
