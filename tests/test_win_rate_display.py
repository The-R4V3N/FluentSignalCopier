# test_win_rate_display.py — TDD tests for Issue #22
# Win rate in % does not show in the Windows GUI
#
# Licensed under the Fluent Signal Copier Limited Use License v1.0
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

import sys
import time
import importlib
import pytest

from PySide6.QtWidgets import QApplication


# ── Qt bootstrap ──────────────────────────────────────────────────────────────
# QApplication must exist before any QWidget is instantiated.

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    yield app


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gui_module():
    return importlib.import_module("fluent_copier_new_gui")


def _win_pct_cell(page) -> str:
    """Return the Win % column (index 2) text from the first populated summary row."""
    table = page.summaryTable
    for r in range(table.rowCount()):
        item = table.item(r, 2)
        if item is not None:
            return item.text()
    return ""


def _make_store(tmp_path):
    from persistence import HistoryStore
    return HistoryStore(tmp_path / "test_history.sqlite3")


def _add_signal(store, channel="channelA"):
    from persistence import NewSignal
    sig = NewSignal(
        ts_ms=int(time.time() * 1000),
        channel=channel,
        raw_text="BUY XAUUSD",
        symbol="XAUUSD",
        side="BUY",
    )
    return store.add_signal(sig)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWinRateDisplay:

    @pytest.fixture(autouse=True)
    def setup(self, qapp, tmp_path):
        mod = _gui_module()
        self.HistoryPage = mod.HistoryPage
        self.store = _make_store(tmp_path)

    def _new_page(self):
        return self.HistoryPage()

    # ── Test 1: hydrate_from_store must populate self.stats win/loss ──────────

    def test_hydrate_populates_stats_with_db_wins_losses(self):
        """After hydrate_from_store, self.stats must contain win/loss counts from DB."""
        id1 = _add_signal(self.store)
        self.store.close_result(id1, realized_pnl=100.0, outcome="WIN")
        id2 = _add_signal(self.store)
        self.store.close_result(id2, realized_pnl=200.0, outcome="WIN")
        id3 = _add_signal(self.store)
        self.store.close_result(id3, realized_pnl=-50.0, outcome="LOSS")

        page = self._new_page()
        page.hydrate_from_store(self.store)

        assert "channelA" in page.stats, "stats must contain channelA after hydrate"
        assert page.stats["channelA"]["win"] == 2, "expected 2 wins in stats"
        assert page.stats["channelA"]["loss"] == 1, "expected 1 loss in stats"

    # ── Test 2: Win % survives _refresh_summary ───────────────────────────────

    def test_win_rate_survives_refresh_summary(self):
        """Win % column must show X.X% after hydrate_from_store + _refresh_summary."""
        id1 = _add_signal(self.store)
        self.store.close_result(id1, realized_pnl=100.0, outcome="WIN")
        id2 = _add_signal(self.store)
        self.store.close_result(id2, realized_pnl=200.0, outcome="WIN")
        id3 = _add_signal(self.store)
        self.store.close_result(id3, realized_pnl=-50.0, outcome="LOSS")

        page = self._new_page()
        page.hydrate_from_store(self.store)
        page._refresh_summary()  # wipes Win % before the fix

        cell = _win_pct_cell(page)
        assert "%" in cell, f"Win % should show a percentage, got: {cell!r}"
        assert cell == "66.7%", f"Expected '66.7%', got: {cell!r}"

    # ── Test 3: Win % survives _refresh_tables (filter change trigger) ────────

    def test_win_rate_survives_filter_refresh(self):
        """Win % must still show after _refresh_tables (simulates filter typing)."""
        id1 = _add_signal(self.store)
        self.store.close_result(id1, realized_pnl=50.0, outcome="WIN")
        id2 = _add_signal(self.store)
        self.store.close_result(id2, realized_pnl=-30.0, outcome="LOSS")

        page = self._new_page()
        page.hydrate_from_store(self.store)
        page._refresh_tables()  # simulates channelFilter.textChanged signal

        cell = _win_pct_cell(page)
        assert "%" in cell, f"Win % should survive filter refresh, got: {cell!r}"
        assert cell == "50.0%", f"Expected '50.0%', got: {cell!r}"

    # ── Test 4: Win % shows "—" when no outcomes (regression guard) ───────────

    def test_win_rate_dash_when_no_outcomes(self):
        """Win % must show '—' when signals exist but no closed results."""
        _add_signal(self.store)
        _add_signal(self.store)

        page = self._new_page()
        page.hydrate_from_store(self.store)
        page._refresh_summary()

        cell = _win_pct_cell(page)
        assert cell == "—", f"Expected '—' when no outcomes, got: {cell!r}"

    # ── Test 5: Live CLOSE event merges with DB-seeded stats ─────────────────

    def test_live_event_merges_with_db_stats(self):
        """A live CLOSE event should add to DB-seeded win/loss, not overwrite it."""
        id1 = _add_signal(self.store)
        self.store.close_result(id1, realized_pnl=100.0, outcome="WIN")
        # DB state: 1 win, 0 losses → 100%

        page = self._new_page()
        page.hydrate_from_store(self.store)

        live_event = {
            "source": "channelA",
            "action": "CLOSE",
            "t": int(time.time()),
            "symbol": "XAUUSD",
            "side": "BUY",
            "profit": -25.0,  # a loss
        }
        page.on_signal(live_event, update_ui=False)
        page._refresh_summary()

        # After merge: 1 win + 1 loss = 50.0%
        cell = _win_pct_cell(page)
        assert cell == "50.0%", f"Expected '50.0%' after merge, got: {cell!r}"
