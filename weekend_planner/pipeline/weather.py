"""Step 2 — Weather lookup. TOOL span."""

from __future__ import annotations

from openinference.semconv.trace import OpenInferenceSpanKindValues

from ..mocks.weather import get_forecast
from ..schemas import WeatherForecast
from ..tracing import set_output, set_tool, span


def lookup_weather(scenario_id: str) -> WeatherForecast:
    with span("weather_lookup", OpenInferenceSpanKindValues.TOOL) as s:
        set_tool(s, name="weather_forecast", parameters={"scenario_id": scenario_id})
        forecast = get_forecast(scenario_id)
        set_output(s, forecast.model_dump(mode="json"))
        return forecast
