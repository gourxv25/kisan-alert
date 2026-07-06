# -*- coding: utf-8 -*-
"""
test_services.py -- Manual smoke-test for WeatherService and SoilService.

Run from the kisan-alert-backend/ directory:
    python test_services.py

Tests
-----
1. WeatherService.get_field_snapshot() -- full field conditions (all 4 endpoints)
2. WeatherService.get_forecast()       -- forecast only (backward compat)
3. WeatherService.get_satellite_soil() -- satellite soil only
4. SoilService.get_soil_for_plot()     -- 4 sub-cases (village default, unknown, SHC, all 3)
"""

import asyncio
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(name)s - %(message)s")

from app.services.weather import weather_service
from app.services.soil import soil_service

SEP  = "=" * 60
THIN = "-" * 60


def _make_plot(soil_data_ref, village_id):
    return types.SimpleNamespace(soil_data_ref=soil_data_ref, village_id=village_id)

def _print_section(title):
    print("\n" + SEP)
    print("  " + title)
    print(SEP)

def _pretty(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) if obj is not None else "None"

def _check_no_error(result, label):
    if isinstance(result, dict) and "error" in result:
        print(f"  [!] {label} returned error: {result['error']}")
        return False
    print(f"  [OK] {label}")
    return True


# ---------------------------------------------------------------------------
# Weather tests
# ---------------------------------------------------------------------------

async def test_weather():

    # ---- Test 1: Full field snapshot ----------------------------------------
    _print_section("1a. WeatherService.get_field_snapshot() -- all data combined")
    print("\n-> Fetching forecast + current weather + satellite soil + UV concurrently ...")
    snapshot = await weather_service.get_field_snapshot()
    print("\nResult:")
    print(_pretty(snapshot))

    ok = True
    ok &= _check_no_error(snapshot.get("forecast"),       "forecast")
    ok &= _check_no_error(snapshot.get("current"),        "current weather")
    ok &= _check_no_error(snapshot.get("satellite_soil"), "satellite soil")
    if snapshot.get("uv_index") is not None:
        print(f"  [OK] uv_index = {snapshot['uv_index']} ({snapshot.get('uv_risk')})")

    if ok:
        # Spot-check the most important fields Gemini will use
        fc  = snapshot["forecast"]
        cur = snapshot["current"]
        sat = snapshot["satellite_soil"]
        assert isinstance(fc["rainfall_next_5d_mm"], float)
        assert isinstance(fc["avg_temp_c"], float)
        assert isinstance(cur["humidity_pct"], int)
        assert isinstance(sat["soil_moisture"], float)
        assert sat["moisture_status"] in ("very_dry","dry","adequate","wet","waterlogged")
        print("\n[OK] All key fields present and correct types.")

    # ---- Test 2: Individual forecast (backward compat) ----------------------
    _print_section("1b. WeatherService.get_forecast() -- individual call")
    fc_only = await weather_service.get_forecast()
    print(_pretty(fc_only))
    _check_no_error(fc_only, "forecast standalone")

    # ---- Test 3: Satellite soil standalone ----------------------------------
    _print_section("1c. WeatherService.get_satellite_soil() -- individual call")
    soil_sat = await weather_service.get_satellite_soil()
    print(_pretty(soil_sat))
    _check_no_error(soil_sat, "satellite soil standalone")

    # ---- Gemini context preview ---------------------------------------------
    _print_section("1d. What Gemini will receive (field_snapshot as crop context)")
    if "error" not in snapshot.get("forecast", {}):
        fc  = snapshot["forecast"]
        cur = snapshot["current"]
        sat = snapshot["satellite_soil"]
        uvi = snapshot.get("uv_index", "N/A")
        print(f"""
  Field conditions for crop recommendation:
  ------------------------------------------
  5-day forecast  : {fc['condition_summary']}
  Current temp    : {cur['temp_c']} C  (feels like {cur['feels_like_c']} C)
  Humidity        : {cur['humidity_pct']}%   Wind: {cur['wind_speed_ms']} m/s
  Sky condition   : {cur['condition']}  (cloud cover {cur['cloud_cover_pct']}%)
  Soil moisture   : {sat['soil_moisture']} m3/m3  [{sat['moisture_status'].upper()}]
  Surface temp    : {sat['surface_temp_c']} C
  Soil temp 10cm  : {sat['soil_temp_10cm_c']} C
  UV index        : {uvi}  [{snapshot.get('uv_risk', '').upper()}]
""")


# ---------------------------------------------------------------------------
# Soil tests
# ---------------------------------------------------------------------------

def test_soil():
    _print_section("2a. SoilService -- known village_id (village_001 - Narsapuram, WG)")
    result_a = soil_service.get_soil_for_plot(
        _make_plot("village_default:village_001", "village_001")
    )
    print(_pretty(result_a))
    assert result_a is not None
    assert result_a["source"] == "village_default"
    assert {"n","p","k","ph","organic_carbon","source"}.issubset(result_a.keys())
    print("[OK] Village default resolved with all expected keys.")

    _print_section("2b. SoilService -- unknown village_id")
    result_b = soil_service.get_soil_for_plot(_make_plot(None, "village_999"))
    print("Result:", result_b)
    assert result_b is None
    print("[OK] Returned None for unknown village_id.")

    _print_section("2c. SoilService -- SHC ref (lookup deferred)")
    result_c = soil_service.get_soil_for_plot(
        _make_plot("SHC-AP-GNT-2024-00142", "village_001")
    )
    print("Result:", result_c)
    assert result_c is None
    print("[OK] Returned None for SHC ref (TODO deferred).")

    _print_section("2d. SoilService -- all 3 seeded villages")
    for vid in ("village_001", "village_002", "village_003"):
        data = soil_service.get_soil_for_plot(
            _make_plot(f"village_default:{vid}", vid)
        )
        assert data is not None
        print(
            "  {:12s} -> N={:>5}  P={:>4}  K={:>5}  pH={:.1f}  OC={:.2f}%  source={}".format(
                vid, data["n"], data["p"], data["k"],
                data["ph"], data["organic_carbon"], data["source"]
            )
        )
    print("[OK] All 3 villages resolved correctly.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    print("\nKisan Alert -- Service Smoke Tests")
    print(THIN)
    await test_weather()
    test_soil()
    print("\n" + THIN)
    print("[OK] All smoke tests complete.")
    print(THIN)

if __name__ == "__main__":
    asyncio.run(main())
