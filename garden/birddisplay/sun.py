"""Sunrise/sunset from the standard sunrise equation (good to a minute or two)."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

_J2000 = 2451545.0
_J2000_ORDINAL = date(2000, 1, 1).toordinal()


def _from_julian(j: float) -> datetime:
    return datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=j - _J2000)


def sun_times(day: date, lat: float, lon: float) -> tuple[datetime | None, datetime | None]:
    """(sunrise, sunset) as aware UTC datetimes; None for polar day/night. lon is east-positive."""
    n = day.toordinal() - _J2000_ORDINAL + 0.0008
    j_star = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
    c = 1.9148 * math.sin(m) + 0.02 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    j_transit = _J2000 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(decl)) / (
        math.cos(phi) * math.cos(decl))
    if cos_w <= -1 or cos_w >= 1:
        return None, None
    w = math.degrees(math.acos(cos_w)) / 360.0
    return _from_julian(j_transit - w), _from_julian(j_transit + w)


def is_night(now: datetime, lat: float, lon: float) -> bool:
    """now is a naive local time (as the Pi's clock gives it)."""
    rise, set_ = sun_times(now.date(), lat, lon)
    if rise is None:
        # Polar: night if the sun is below the horizon at noon, i.e. winter.
        return now.month in (11, 12, 1) if lat > 0 else now.month in (5, 6, 7)
    local = now.astimezone()
    return not (rise <= local < set_)
