"""Mock weather service — canned per-scenario forecasts."""

from __future__ import annotations

from ..schemas import DayForecast, WeatherForecast

_FORECASTS: dict[str, WeatherForecast] = {
    "sunny_baseline": WeatherForecast(
        saturday=DayForecast(
            day="Saturday",
            condition="sunny",
            high_f=72,
            low_f=55,
            precip_chance=5,
            outdoor_friendly=True,
        ),
        sunday=DayForecast(
            day="Sunday",
            condition="sunny",
            high_f=74,
            low_f=58,
            precip_chance=10,
            outdoor_friendly=True,
        ),
    ),
    "rainy_weekend": WeatherForecast(
        saturday=DayForecast(
            day="Saturday",
            condition="rain",
            high_f=58,
            low_f=48,
            precip_chance=85,
            outdoor_friendly=False,
        ),
        sunday=DayForecast(
            day="Sunday",
            condition="rain",
            high_f=55,
            low_f=46,
            precip_chance=75,
            outdoor_friendly=False,
        ),
    ),
    "saturday_morning_conflict": WeatherForecast(
        saturday=DayForecast(
            day="Saturday",
            condition="cloudy",
            high_f=68,
            low_f=52,
            precip_chance=20,
            outdoor_friendly=True,
        ),
        sunday=DayForecast(
            day="Sunday",
            condition="sunny",
            high_f=71,
            low_f=55,
            precip_chance=5,
            outdoor_friendly=True,
        ),
    ),
}


def get_forecast(scenario_id: str) -> WeatherForecast:
    if scenario_id not in _FORECASTS:
        raise KeyError(f"No mock forecast for scenario {scenario_id!r}")
    return _FORECASTS[scenario_id]
