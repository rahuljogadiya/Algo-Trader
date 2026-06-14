from datetime import datetime, timedelta

from AlgoTradingNSEFO.src.core.clock import MarketClock, parse_time_hhmm


def test_is_within_first_minutes_logic():
    clock = MarketClock()

    # Market open is 09:15 in MarketClock
    open_dt = datetime(2026, 6, 14, 9, 15, 0)
    # first 15 minutes: 09:15:00 to 09:29:59 inclusive
    assert clock.is_within_first_minutes(
        15, ref=open_dt + timedelta(seconds=1)) is True
    assert clock.is_within_first_minutes(
        15, ref=open_dt + timedelta(minutes=14, seconds=59)) is True
    assert clock.is_within_first_minutes(
        15, ref=open_dt + timedelta(minutes=15, seconds=0)) is False


def test_cutoff_time_reached():
    clock = MarketClock()
    cutoff = parse_time_hhmm("14:45")

    ref_before = datetime(2026, 6, 14, 14, 44, 59)
    ref_after = datetime(2026, 6, 14, 14, 45, 0)

    assert clock.cutoff_time_reached(cutoff, ref=ref_before) is False
    assert clock.cutoff_time_reached(cutoff, ref=ref_after) is True


def test_square_off_reached():
    clock = MarketClock()
    sq = parse_time_hhmm("15:20")

    ref_before = datetime(2026, 6, 14, 15, 19, 59)
    ref_after = datetime(2026, 6, 14, 15, 20, 0)

    assert clock.square_off_reached(sq, ref=ref_before) is False
    assert clock.square_off_reached(sq, ref=ref_after) is True
