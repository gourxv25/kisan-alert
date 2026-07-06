"""
Weather service -- fetches weather, satellite soil, and UV data from Agromonitoring.

Endpoints used (all polygon-based):
  GET /agro/1.0/weather/forecast  -- 5-day / 3-hourly forecast
  GET /agro/1.0/weather           -- current conditions
  GET /agro/1.0/soil              -- satellite soil moisture + surface temperature
  GET /agro/1.0/uvi               -- UV index

Resolution order for polygon ID:
  1. poly_id argument passed to the method
  2. AGROMONITORING_POLYGON_ID from settings/.env

Temperature convention: all Kelvin values from API are converted to Celsius on output.
Soil moisture unit: m3/m3 (volumetric water content). Typical range: 0.05 (dry) - 0.50 (wet).
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL       = "https://api.agromonitoring.com/agro/1.0"
FORECAST_URL   = f"{BASE_URL}/weather/forecast"
CURRENT_URL    = f"{BASE_URL}/weather"
SOIL_SAT_URL   = f"{BASE_URL}/soil"
UVI_URL        = f"{BASE_URL}/uvi"
POLYGONS_URL   = f"{BASE_URL}/polygons"

KELVIN_OFFSET  = 273.15


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _k_to_c(kelvin: float) -> float:
    """Convert Kelvin to Celsius, rounded to 2 dp."""
    return round(kelvin - KELVIN_OFFSET, 2)


def _resolve_poly(poly_id: str | None) -> str | None:
    """Return poly_id arg, falling back to settings, or None if neither set."""
    return poly_id or settings.AGROMONITORING_POLYGON_ID or None


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> dict | list | None:
    """
    Perform a single GET and return parsed JSON, or a dict with an 'error' key
    on any failure -- never raises.
    """
    try:
        r = await client.get(url, params={**params, "appid": settings.AGROMONITORING_API_KEY})
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException:
        logger.warning("Timeout: %s", url)
        return {"error": "timeout"}
    except httpx.HTTPStatusError as exc:
        logger.error("HTTP %s from %s: %s", exc.response.status_code, url, exc.response.text)
        return {"error": f"HTTP {exc.response.status_code}"}
    except httpx.RequestError as exc:
        logger.error("Network error %s: %s", url, exc)
        return {"error": f"network: {exc}"}
    except ValueError:
        logger.error("JSON parse error from %s", url)
        return {"error": "json_parse"}


# ---------------------------------------------------------------------------
# WeatherService
# ---------------------------------------------------------------------------

class WeatherService:
    """
    Fetches weather, satellite soil, and UV data from Agromonitoring for a
    registered polygon. All public methods accept an optional poly_id override.
    """

    # ---- Composite snapshot (primary method for Gemini advisor) -------------

    async def get_field_snapshot(self, poly_id: str | None = None) -> dict:
        """
        Return a single, Gemini-ready dict combining:
          - 5-day forecast  (rainfall total, avg temperature)
          - Current weather (temperature, humidity, wind, cloud cover, condition)
          - Satellite soil  (surface temperature, soil temperature at 10 cm, moisture)
          - UV index

        On success the dict contains all keys below. Any sub-section that fails
        individually will have an 'error' key instead of its normal fields, so
        the advisor can still operate with partial data.

        Schema:
        {
            "forecast": {
                "rainfall_next_5d_mm": float,
                "avg_temp_c":          float,
                "condition_summary":   str
            },
            "current": {
                "temp_c":       float,
                "feels_like_c": float,
                "humidity_pct": int,
                "wind_speed_ms":float,
                "cloud_cover_pct": int,
                "condition":    str     # e.g. "overcast clouds"
            },
            "satellite_soil": {
                "surface_temp_c":  float,  # t0 -- land surface temperature
                "soil_temp_10cm_c":float,  # t10 -- soil temp at 10 cm depth
                "soil_moisture":   float,  # volumetric water content (m3/m3)
                "moisture_status": str     # "dry" | "adequate" | "wet" | "waterlogged"
            },
            "uv_index":      float,
            "uv_risk":       str    # "low" | "moderate" | "high" | "very_high" | "extreme"
        }
        """
        api_key = settings.AGROMONITORING_API_KEY
        if not api_key:
            return {"error": "AGROMONITORING_API_KEY is not set in environment."}

        pid = _resolve_poly(poly_id)
        if not pid:
            return {"error": "No polygon ID. Set AGROMONITORING_POLYGON_ID in .env."}

        params = {"polyid": pid}

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Fire all four requests concurrently
            import asyncio
            forecast_raw, current_raw, soil_raw, uvi_raw = await asyncio.gather(
                _get(client, FORECAST_URL, params),
                _get(client, CURRENT_URL,  params),
                _get(client, SOIL_SAT_URL, params),
                _get(client, UVI_URL,      params),
            )

        return {
            "forecast":       _parse_forecast(forecast_raw),
            "current":        _parse_current(current_raw),
            "satellite_soil": _parse_satellite_soil(soil_raw),
            **_parse_uvi(uvi_raw),
        }

    # ---- Individual methods (kept for direct use) ----------------------------

    async def get_forecast(
        self,
        lat: float | None = None,
        lng: float | None = None,
        poly_id: str | None = None,
    ) -> dict:
        """
        Return rainfall + avg temperature summary from the 5-day forecast.

        lat/lng are accepted for API-signature compatibility but ignored;
        Agromonitoring requires a polygon ID.
        """
        api_key = settings.AGROMONITORING_API_KEY
        if not api_key:
            return {"error": "AGROMONITORING_API_KEY is not set in environment."}
        pid = _resolve_poly(poly_id)
        if not pid:
            return {"error": "No polygon ID. Set AGROMONITORING_POLYGON_ID in .env."}

        async with httpx.AsyncClient(timeout=15.0) as client:
            raw = await _get(client, FORECAST_URL, {"polyid": pid})

        return _parse_forecast(raw)

    async def get_current_weather(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        poly_id: str | None = None,
    ) -> dict:
        """Return current weather conditions for the polygon."""
        api_key = settings.AGROMONITORING_API_KEY
        if not api_key:
            return {"error": "AGROMONITORING_API_KEY is not set in environment."}
        pid = _resolve_poly(poly_id)
        if not pid:
            return {"error": "No polygon ID. Set AGROMONITORING_POLYGON_ID in .env."}

        async with httpx.AsyncClient(timeout=15.0) as client:
            raw = await _get(client, CURRENT_URL, {"polyid": pid})

        return _parse_current(raw)

    async def get_satellite_soil(self, poly_id: str | None = None) -> dict:
        """
        Return satellite-derived soil moisture and surface/soil temperature.
        Sourced from MODIS / Copernicus -- updated every ~12 hours.
        """
        api_key = settings.AGROMONITORING_API_KEY
        if not api_key:
            return {"error": "AGROMONITORING_API_KEY is not set in environment."}
        pid = _resolve_poly(poly_id)
        if not pid:
            return {"error": "No polygon ID. Set AGROMONITORING_POLYGON_ID in .env."}

        async with httpx.AsyncClient(timeout=15.0) as client:
            raw = await _get(client, SOIL_SAT_URL, {"polyid": pid})

        return _parse_satellite_soil(raw)

    async def list_polygons(self) -> list[dict] | dict:
        """Return all registered polygons for the configured API key."""
        api_key = settings.AGROMONITORING_API_KEY
        if not api_key:
            return {"error": "AGROMONITORING_API_KEY is not set in environment."}

        async with httpx.AsyncClient(timeout=15.0) as client:
            raw = await _get(client, POLYGONS_URL, {})

        return raw if isinstance(raw, list) else {"error": "Unexpected response"}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_forecast(data: Any) -> dict:
    """Aggregate 3-hourly forecast points into a summary dict."""
    if not isinstance(data, list) or not data:
        return {"error": data.get("error", "unexpected_format") if isinstance(data, dict) else "no_data"}

    total_rain_mm = 0.0
    temp_sum_c    = 0.0
    point_count   = 0

    for pt in data:
        rain = pt.get("rain", {})
        total_rain_mm += rain.get("3h", 0.0) or rain.get("1h", 0.0)
        temp_k = pt.get("main", {}).get("temp", 0.0)
        if temp_k > 0:
            temp_sum_c  += temp_k - KELVIN_OFFSET
            point_count += 1

    avg_temp_c = (temp_sum_c / point_count) if point_count else 0.0

    return {
        "rainfall_next_5d_mm": round(total_rain_mm, 2),
        "avg_temp_c":          round(avg_temp_c,    2),
        "condition_summary":   _forecast_summary(total_rain_mm, avg_temp_c),
    }


def _parse_current(data: Any) -> dict:
    """Extract current weather fields."""
    if not isinstance(data, dict) or "error" in data:
        return {"error": data.get("error", "no_data") if isinstance(data, dict) else "no_data"}

    main    = data.get("main", {})
    wind    = data.get("wind", {})
    weather = data.get("weather", [{}])
    clouds  = data.get("clouds", {})

    return {
        "temp_c":         _k_to_c(main.get("temp",       0.0)),
        "feels_like_c":   _k_to_c(main.get("feels_like", 0.0)),
        "humidity_pct":   main.get("humidity", 0),
        "wind_speed_ms":  round(wind.get("speed", 0.0), 1),
        "cloud_cover_pct":clouds.get("all", 0),
        "condition":      weather[0].get("description", "unknown") if weather else "unknown",
    }


def _parse_satellite_soil(data: Any) -> dict:
    """
    Parse satellite soil response.

    Fields from Agromonitoring:
      t0       -- land surface temperature (K)
      t10      -- soil temperature at 10 cm depth (K)
      moisture -- volumetric water content (m3/m3)
    """
    if not isinstance(data, dict) or "error" in data:
        return {"error": data.get("error", "no_data") if isinstance(data, dict) else "no_data"}

    moisture = data.get("moisture", 0.0)

    return {
        "surface_temp_c":   _k_to_c(data.get("t0",  0.0)),
        "soil_temp_10cm_c": _k_to_c(data.get("t10", 0.0)),
        "soil_moisture":    round(moisture, 4),
        "moisture_status":  _moisture_label(moisture),
    }


def _parse_uvi(data: Any) -> dict:
    """Parse UV index response."""
    if not isinstance(data, dict) or "error" in data or "uvi" not in data:
        return {"uv_index": None, "uv_risk": "unknown"}

    uvi = data["uvi"]
    return {
        "uv_index": round(uvi, 1),
        "uv_risk":  _uvi_label(uvi),
    }


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _forecast_summary(rain_mm: float, avg_temp_c: float) -> str:
    if rain_mm < 10:
        rain_str = "Dry spell expected (< 10 mm)"
    elif rain_mm < 50:
        rain_str = f"Light rainfall (~{rain_mm:.0f} mm)"
    elif rain_mm < 150:
        rain_str = f"Moderate rainfall (~{rain_mm:.0f} mm)"
    else:
        rain_str = f"Heavy rainfall (~{rain_mm:.0f} mm) -- flood risk"

    if avg_temp_c >= 40:
        temp_str = f"extreme heat stress (avg {avg_temp_c:.1f} C)"
    elif avg_temp_c >= 35:
        temp_str = f"high temperatures (avg {avg_temp_c:.1f} C)"
    elif avg_temp_c >= 25:
        temp_str = f"warm conditions (avg {avg_temp_c:.1f} C)"
    elif avg_temp_c >= 15:
        temp_str = f"mild temperatures (avg {avg_temp_c:.1f} C)"
    else:
        temp_str = f"cool conditions (avg {avg_temp_c:.1f} C)"

    return f"{rain_str}; {temp_str}."


def _moisture_label(m: float) -> str:
    """
    Classify volumetric soil moisture (m3/m3).
    Typical thresholds for agricultural soils:
      < 0.10  : very dry  (below permanent wilting point for most crops)
      0.10-0.20: dry      (below field capacity; irrigation needed)
      0.20-0.35: adequate (near field capacity; good for most crops)
      0.35-0.45: wet      (saturated zone; anaerobic risk for roots)
      > 0.45  : waterlogged (runoff/drainage needed)
    """
    if m < 0.10:
        return "very_dry"
    elif m < 0.20:
        return "dry"
    elif m < 0.35:
        return "adequate"
    elif m < 0.45:
        return "wet"
    else:
        return "waterlogged"


def _uvi_label(uvi: float) -> str:
    if uvi < 3:
        return "low"
    elif uvi < 6:
        return "moderate"
    elif uvi < 8:
        return "high"
    elif uvi < 11:
        return "very_high"
    else:
        return "extreme"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
weather_service = WeatherService()
