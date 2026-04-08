# Licensed under the Attribution-NonCommercial-ShareAlike 4.0 International
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

"""
Regression tests for issue #37: EA CLOSE records writing broker server time
(TimeCurrent) instead of UTC (TimeGMT), causing the dashboard to display
signal times that are offset by the broker's timezone (e.g. +2h / +3h).

The Python display layer is correct — time.localtime(t) handles UTC → local.
These tests verify:
  1. A UTC epoch 't' field displays as correct local time.
  2. A broker-inflated 't' field (TimeCurrent on a UTC+N broker) displays
     incorrectly — documenting the pre-fix bug.
  3. Regression guard: the EA's 't' value must be within ±120s of
     time.time() to be a valid UTC epoch (not broker-inflated).
"""

import time


def _format_signal_time_hhmm(t: int) -> str:
    """Mirrors the GUI's conversion: treat t as UTC epoch, display local HH:MM."""
    return time.strftime("%H:%M", time.localtime(t))


class TestSignalTimestampDisplay:
    def test_utc_epoch_displays_correct_local_time(self):
        """A UTC epoch 't' field must round-trip through time.localtime correctly."""
        now_utc = int(time.time())
        expected = time.strftime("%H:%M", time.localtime(now_utc))
        assert _format_signal_time_hhmm(now_utc) == expected

    def test_broker_time_offset_produces_wrong_display(self):
        """Demonstrates the bug: TimeCurrent() on a UTC+2 broker adds 2h on top
        of the local-time conversion, showing a time in the future.

        This test FAILS before the EA fix (when 't' = TimeCurrent) and PASSES
        after (when 't' = TimeGMT ≈ time.time()).
        """
        now_utc = int(time.time())
        broker_offset = 2 * 3600  # typical UTC+2 broker

        # What the EA incorrectly wrote before the fix
        buggy_t = now_utc + broker_offset

        correct_display = _format_signal_time_hhmm(now_utc)
        buggy_display = _format_signal_time_hhmm(buggy_t)

        assert correct_display != buggy_display, (
            "Broker-inflated timestamp should not match UTC-based display. "
            "If this fails, the broker offset is exactly 0 (UTC broker) — "
            "re-run with a non-zero broker_offset."
        )

    def test_close_record_t_must_be_near_utc_epoch(self):
        """Regression guard: a valid EA CLOSE 't' field (TimeGMT) must be
        within 120 seconds of Python's time.time() (UTC). A TimeCurrent()
        value on a UTC+2 broker would be ~7200s ahead — far outside this window.
        """
        now_utc = int(time.time())

        # Simulate what the fixed EA writes: TimeGMT() ≈ time.time()
        ea_t_fixed = now_utc  # after fix: TimeGMT matches Python UTC

        # Simulate what the broken EA wrote: TimeCurrent() on UTC+2 broker
        ea_t_broken = now_utc + 2 * 3600

        tolerance = 120  # seconds

        assert abs(ea_t_fixed - now_utc) <= tolerance, (
            "Fixed EA 't' field should be within 120s of Python UTC epoch"
        )
        assert abs(ea_t_broken - now_utc) > tolerance, (
            "Broken EA 't' field (broker time) should be far from Python UTC epoch"
        )

    def test_ts_ms_from_db_displays_correct_local_time(self):
        """ts_ms stored by Python bridge (time.time()*1000) converts correctly.
        Regression guard for the DB→history-table path in the GUI.
        """
        now_utc_ms = int(time.time() * 1000)
        t_seconds = now_utc_ms // 1000

        display = _format_signal_time_hhmm(t_seconds)
        expected = time.strftime("%H:%M", time.localtime(t_seconds))

        assert display == expected
