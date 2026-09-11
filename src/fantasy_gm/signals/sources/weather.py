"""
Weather source — Open-Meteo (keyless) + a bundled NFL stadium table.

Wind and precipitation move fantasy outcomes for kickers and passing games;
domes remove that variable entirely. We ship a compact stadium table
(coordinates + indoor flag) rather than take a dependency, and query Open-Meteo's
free forecast API for outdoor venues.

Best-effort: forecasts only exist for near-future games, so past/far games (and
any request error) return a WeatherReport with weather fields left None. Indoor
venues short-circuit to `is_dome=True` with no network call.
"""
from __future__ import annotations

import httpx

from fantasy_gm.models import WeatherReport

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# NFL team abbrev -> (stadium name, latitude, longitude, is_indoor).
# Indoor = fixed dome or a retractable roof that is usually closed; for those we
# treat wind/precip as a non-factor.
STADIUMS: dict[str, tuple[str, float, float, bool]] = {
    "ARI": ("State Farm Stadium", 33.5277, -112.2626, True),
    "ATL": ("Mercedes-Benz Stadium", 33.7554, -84.4008, True),
    "BAL": ("M&T Bank Stadium", 39.2780, -76.6227, False),
    "BUF": ("Highmark Stadium", 42.7738, -78.7870, False),
    "CAR": ("Bank of America Stadium", 35.2258, -80.8528, False),
    "CHI": ("Soldier Field", 41.8623, -87.6167, False),
    "CIN": ("Paycor Stadium", 39.0955, -84.5161, False),
    "CLE": ("Cleveland Browns Stadium", 41.5061, -81.6995, False),
    "DAL": ("AT&T Stadium", 32.7473, -97.0945, True),
    "DEN": ("Empower Field at Mile High", 39.7439, -105.0201, False),
    "DET": ("Ford Field", 42.3400, -83.0456, True),
    "GB": ("Lambeau Field", 44.5013, -88.0622, False),
    "HOU": ("NRG Stadium", 29.6847, -95.4107, True),
    "IND": ("Lucas Oil Stadium", 39.7601, -86.1639, True),
    "JAX": ("EverBank Stadium", 30.3239, -81.6373, False),
    "KC": ("Arrowhead Stadium", 39.0489, -94.4839, False),
    "LV": ("Allegiant Stadium", 36.0909, -115.1833, True),
    "LAC": ("SoFi Stadium", 33.9535, -118.3392, True),
    "LAR": ("SoFi Stadium", 33.9535, -118.3392, True),
    "MIA": ("Hard Rock Stadium", 25.9580, -80.2389, False),
    "MIN": ("U.S. Bank Stadium", 44.9736, -93.2575, True),
    "NE": ("Gillette Stadium", 42.0909, -71.2643, False),
    "NO": ("Caesars Superdome", 29.9511, -90.0812, True),
    "NYG": ("MetLife Stadium", 40.8135, -74.0745, False),
    "NYJ": ("MetLife Stadium", 40.8135, -74.0745, False),
    "PHI": ("Lincoln Financial Field", 39.9008, -75.1675, False),
    "PIT": ("Acrisure Stadium", 40.4468, -80.0158, False),
    "SF": ("Levi's Stadium", 37.4030, -121.9700, False),
    "SEA": ("Lumen Field", 47.5952, -122.3316, False),
    "TB": ("Raymond James Stadium", 27.9759, -82.5033, False),
    "TEN": ("Nissan Stadium", 36.1665, -86.7713, False),
    "WAS": ("Northwest Stadium", 38.9077, -76.8645, False),
}


def get_weather(team: str, week: int) -> WeatherReport | None:
    """Best-effort weather for a team's home stadium. None if team unknown."""
    info = STADIUMS.get(team)
    if info is None:
        return None
    name, lat, lon, indoor = info
    if indoor:
        return WeatherReport(nfl_team=team, stadium=name, is_dome=True, week=week)

    temp = wind = precip = None
    try:
        resp = httpx.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",
                "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
                "forecast_days": 7,
            },
            timeout=20,
        )
        resp.raise_for_status()
        hourly = resp.json().get("hourly", {})
        # Use a representative Sunday-afternoon-ish slot: the max wind and precip
        # over the forecast window are the fantasy-relevant worst case.
        winds = [w for w in (hourly.get("wind_speed_10m") or []) if w is not None]
        precips = [p for p in (hourly.get("precipitation_probability") or []) if p is not None]
        temps = [t for t in (hourly.get("temperature_2m") or []) if t is not None]
        if winds:
            wind = round(max(winds), 1)
        if precips:
            precip = round(max(precips) / 100.0, 2)
        if temps:
            temp = round(sum(temps) / len(temps), 1)
    except Exception:
        pass

    return WeatherReport(
        nfl_team=team, stadium=name, is_dome=False,
        temperature_f=temp, wind_mph=wind, precipitation_chance=precip, week=week,
    )
