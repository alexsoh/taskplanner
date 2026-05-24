from __future__ import annotations

from datetime import timezone

from tp.tzutil import profile_timezone


def test_profile_timezone_utc_without_zoneinfo_db() -> None:
    tz = profile_timezone("UTC")
    assert tz is timezone.utc


def test_profile_timezone_unknown_falls_back_to_utc() -> None:
    tz = profile_timezone("Not/A_Real_Zone")
    assert tz is timezone.utc
