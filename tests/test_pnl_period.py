# test_pnl_period.py — TDD tests for Issue #21
# Add period selector (Today / 7 Days / 30 Days / All Time) to PnL display
#
# Licensed under the Attribution-NonCommercial-ShareAlike 4.0 International
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

import sys
import time
import importlib
import pytest

from PySide6.QtWidgets import QApplication
from persistence import HistoryStore, NewSignal


# ── Qt bootstrap ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_store(tmp_path):
    return HistoryStore(tmp_path / "test_pnl.sqlite3")


def _add_closed(store, pnl: float, outcome: str, closed_ts_ms: int, channel: str = "chA") -> int:
    sig_id = store.add_signal(NewSignal(
        ts_ms=closed_ts_ms - 1000,
        channel=channel,
        raw_text="BUY XAUUSD",
        symbol="XAUUSD",
        side="BUY",
    ))
    store.close_result(sig_id, realized_pnl=pnl, outcome=outcome, ts_ms=closed_ts_ms)
    return sig_id


def _gui_module():
    return importlib.import_module("fluent_copier_new_gui")


# ── Cycle 1: total_pnl() ─────────────────────────────────────────────────────

class TestTotalPnl:

    def test_total_pnl_all_time_returns_sum(self, tmp_path):
        store = _make_store(tmp_path)
        now = int(time.time() * 1000)
        _add_closed(store, 100.0, "WIN", now - 5000)
        _add_closed(store, 200.0, "WIN", now - 4000)
        _add_closed(store, -50.0, "LOSS", now - 3000)
        assert store.total_pnl() == pytest.approx(250.0)

    def test_total_pnl_empty_db_returns_zero(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.total_pnl() == 0.0

    def test_total_pnl_since_ms_filters_old_results(self, tmp_path):
        store = _make_store(tmp_path)
        _add_closed(store, 100.0, "WIN", 1_000)   # old
        _add_closed(store, 200.0, "WIN", 2_000)   # boundary — included
        _add_closed(store, 300.0, "WIN", 3_000)   # recent
        result = store.total_pnl(since_ms=2_000)
        assert result == pytest.approx(500.0)      # 200 + 300

    def test_total_pnl_since_ms_no_matches_returns_zero(self, tmp_path):
        store = _make_store(tmp_path)
        _add_closed(store, 100.0, "WIN", 1_000)
        assert store.total_pnl(since_ms=9_999_999) == 0.0


# ── Cycle 2: channel_stats_since() ───────────────────────────────────────────

class TestChannelStatsSince:

    def test_channel_stats_since_none_returns_all(self, tmp_path):
        store = _make_store(tmp_path)
        now = int(time.time() * 1000)
        _add_closed(store, 100.0, "WIN", now - 1000, channel="chA")
        _add_closed(store, -50.0, "LOSS", now - 500, channel="chA")
        rows = store.channel_stats_since(since_ms=None)
        assert len(rows) == 1
        chA = rows[0]
        assert chA["channel"] == "chA"
        assert chA["wins"] == 1
        assert chA["losses"] == 1

    def test_channel_stats_since_filters_by_time(self, tmp_path):
        store = _make_store(tmp_path)
        _add_closed(store, 100.0, "WIN", 1_000, channel="chA")   # too old
        _add_closed(store, 200.0, "WIN", 3_000, channel="chA")   # in range
        _add_closed(store, 50.0,  "WIN", 3_500, channel="chB")   # in range
        rows = store.channel_stats_since(since_ms=2_000)
        channels = {r["channel"] for r in rows}
        assert "chA" in channels
        assert "chB" in channels
        chA = next(r for r in rows if r["channel"] == "chA")
        assert chA["wins"] == 1   # only the 3_000 result, not the 1_000 one

    def test_channel_stats_since_empty_range_returns_empty(self, tmp_path):
        store = _make_store(tmp_path)
        _add_closed(store, 100.0, "WIN", 1_000)
        rows = store.channel_stats_since(since_ms=9_999_999)
        assert rows == []

    def test_channel_stats_since_total_pnl_in_result(self, tmp_path):
        store = _make_store(tmp_path)
        _add_closed(store, 100.0, "WIN", 1_000, channel="chA")
        _add_closed(store, 200.0, "WIN", 2_000, channel="chA")
        rows = store.channel_stats_since(since_ms=None)
        chA = next(r for r in rows if r["channel"] == "chA")
        assert chA["total_pnl"] == pytest.approx(300.0)


# ── Cycle 3: GUI widgets ──────────────────────────────────────────────────────

class TestHistoryPagePnlSelector:

    @pytest.fixture(autouse=True)
    def setup(self, qapp, tmp_path):
        mod = _gui_module()
        self.HistoryPage = mod.HistoryPage
        self.store = _make_store(tmp_path)

    def _new_page(self):
        return self.HistoryPage()

    def test_history_page_has_period_combo(self):
        """HistoryPage must have a periodCombo with 4 items."""
        page = self._new_page()
        assert hasattr(page, "periodCombo"), "HistoryPage must have periodCombo attribute"
        combo = page.periodCombo
        texts = [combo.itemText(i) for i in range(combo.count())]
        assert set(texts) == {"Today", "7 Days", "30 Days", "All Time"}, (
            f"Expected 4 period options, got: {texts}"
        )

    def test_history_page_has_pnl_label(self):
        """HistoryPage must have a pnlLabel showing total PnL."""
        page = self._new_page()
        assert hasattr(page, "pnlLabel"), "HistoryPage must have pnlLabel attribute"

    def test_hydrate_shows_total_pnl(self):
        """After hydrate, pnlLabel must reflect total realized PnL for selected period."""
        now = int(time.time() * 1000)
        _add_closed(self.store, 150.0, "WIN", now - 1000)
        _add_closed(self.store, -50.0, "LOSS", now - 500)
        page = self._new_page()
        # Set to All Time
        for i in range(page.periodCombo.count()):
            if page.periodCombo.itemText(i) == "All Time":
                page.periodCombo.setCurrentIndex(i)
        page.hydrate_from_store(self.store)
        text = page.pnlLabel.text()
        assert "100" in text.replace(",", ""), f"pnlLabel should show ~100.00, got: {text!r}"

    def test_period_all_time_shows_all_pnl(self):
        """'All Time' period includes all results regardless of date."""
        _add_closed(self.store, 500.0, "WIN", 1_000)   # very old
        _add_closed(self.store, 200.0, "WIN", 2_000)
        page = self._new_page()
        for i in range(page.periodCombo.count()):
            if page.periodCombo.itemText(i) == "All Time":
                page.periodCombo.setCurrentIndex(i)
        page.hydrate_from_store(self.store)
        text = page.pnlLabel.text()
        assert "700" in text.replace(",", ""), f"All Time should show 700.00, got: {text!r}"

    def test_period_filter_excludes_old_results(self):
        """Switching to '7 Days' should exclude results older than 7 days."""
        now = int(time.time() * 1000)
        old_ts = now - 8 * 86400 * 1000      # 8 days ago — outside 7-day window
        recent_ts = now - 2 * 86400 * 1000   # 2 days ago — inside
        _add_closed(self.store, 999.0, "WIN", old_ts)
        _add_closed(self.store, 100.0, "WIN", recent_ts)
        page = self._new_page()
        for i in range(page.periodCombo.count()):
            if page.periodCombo.itemText(i) == "7 Days":
                page.periodCombo.setCurrentIndex(i)
        page.hydrate_from_store(self.store)
        text = page.pnlLabel.text()
        assert "100" in text.replace(",", ""), (
            f"7 Days should show only 100.00 (not 1099), got: {text!r}"
        )
        assert "999" not in text.replace(",", ""), (
            f"7 Days must exclude the 8-day-old result, got: {text!r}"
        )
