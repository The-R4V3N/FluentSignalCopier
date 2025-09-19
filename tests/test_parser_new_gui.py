# test_parser_new_gui.py
import re
import math
import importlib


# Import directly from your GUI file; __main__ section won't run on import
mod = importlib.import_module("fluent_copier_new_gui")
parse_message = mod.parse_message
normalize_symbol = mod.normalize_symbol

def _nums_equal(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol

def test_simple_market_buy_with_hyphen_tps_and_sl():
    txt = """Buy  XAUUSD+
    Sl-3276
    Tp1-3535
    Tp2-3538
    Tp3-3543
    Tp4-3552
    """
    p = parse_message(txt)
    assert p and p["kind"] == "OPEN"
    assert p["side"] == "BUY"
    assert p["symbol"] == "XAUUSD+"
    assert p["order_type"] == "MARKET"
    assert p["entry"] is None
    assert _nums_equal(p["sl"], 3276)
    assert p["tps"] == [3535.0, 3538.0, 3543.0, 3552.0]
    assert _nums_equal(p["tp"], 3535.0)

def test_pending_limit_header_with_inline_price_and_separators():
    txt = "#XAUUSD+ BUY LIMIT @ 3,402\nSTOPLOSS : 3,391\nTP1 = 3,415\nTP2 -> 3,421"
    p = parse_message(txt)
    assert p and p["kind"] == "OPEN"
    assert p["order_type"] == "LIMIT"
    assert _nums_equal(p["entry"], 3402)
    assert _nums_equal(p["sl"], 3391)
    assert p["tps"] == [3415.0, 3421.0]

def test_sell_now_market():
    txt = "XAUUSD+ SELL NOW\nSL @ 3465\nTP 3440\nTP 3430\nTP 3420"
    p = parse_message(txt)
    assert p and p["kind"] == "OPEN"
    assert p["symbol"] == "XAUUSD+"
    assert p["side"] == "SELL"
    assert p["order_type"] == "MARKET"
    assert p["entry"] is None
    assert _nums_equal(p["sl"], 3465)
    assert p["tps"] == [3420.0, 3430.0, 3440.0]  # sorted ascending

def test_risky_message_is_skipped():
    txt = "Very Risky setup\nBUY XAUUSD+ @ 3500\nSL 3490\nTP 3510"
    p = parse_message(txt)
    assert p is None

def test_close_any_detects_symbol():
    txt = "Close all XAUUSD+ positions now"
    p = parse_message(txt)
    assert p and p["kind"] == "CLOSE"
    assert p["symbol"] == "XAUUSD+"

def test_modify_tp_variants():
    txt = "XAUUSD+\nMove TP2 to 3520\nTP3 moved to 3530"
    p = parse_message(txt)
    assert p and p["kind"] == "MODIFY_TP"
    mv = sorted(p["tp_moves"], key=lambda x: x["slot"])
    assert mv == [{"slot": 2, "to": 3520.0}, {"slot": 3, "to": 3530.0}]

def test_aliases_normalize_to_XAUUSD_plus():
    for alias in ["XAU", "GOLD", "XAUSD", "XAUUSD+"]:
        assert normalize_symbol(alias) == "XAUUSD+"
