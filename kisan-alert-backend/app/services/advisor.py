"""
Crop Recommendation Advisor -- uses Google Gemini to generate structured
crop recommendations from field snapshot data (weather + satellite soil)
combined with agronomic soil nutrients and optional historical crop data.

Gemini model: gemini-2.0-flash  (fast, free-tier friendly)

Output contract (JSON):
{
    "recommendations": [
        {
            "crop":           str,    # e.g. "Rice (IR-64)"
            "reason":         str,    # why this crop suits current conditions
            "sowing_window":  str,    # e.g. "15 Jul -- 10 Aug"
            "water_need":     str,    # e.g. "High (1000-1200 mm/season)"
            "expected_yield": str,    # e.g. "5-6 tonnes/ha"
            "warnings":       list[str]  # any risk flags
        }
    ],
    "irrigation_advice":   str,
    "fertiliser_advice":   str,
    "general_advisory":    str,
    "data_quality_notes":  list[str]  # flagged missing or low-confidence inputs
}
"""

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import settings

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"  # Confirmed available for this API key

# Season labels used in the prompt
SEASON_LABELS = {
    "kharif": "Kharif (Jun-Oct, monsoon)",
    "rabi":   "Rabi (Nov-Mar, winter/spring)",
    "zaid":   "Zaid (Apr-Jun, summer)",
}


# ---------------------------------------------------------------------------
# AdvisorService
# ---------------------------------------------------------------------------

class AdvisorService:
    """Generate structured crop recommendations using Gemini AI."""

    def __init__(self):
        self._model = None  # lazy-init on first call

    def _get_client(self) -> genai.Client:
        if self._model is None:
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is not set in environment.")
            self._model = genai.Client(api_key=api_key)
        return self._model

    # ---- Main method --------------------------------------------------------

    async def get_crop_recommendation(
        self,
        field_snapshot: dict,           # from weather_service.get_field_snapshot()
        soil_nutrients: dict | None,    # from soil_service.get_soil_for_plot()
        season: str = "kharif",         # kharif | rabi | zaid
        language: str = "en",           # en | hi | te
        previous_crops: list[str] | None = None,  # e.g. ["rice", "cotton"]
        farm_size_acres: float | None = None,
        farmer_notes: str | None = None,  # any free-text notes from farmer
    ) -> dict:
        """
        Build a Gemini prompt from all available field data and return a
        structured crop recommendation dict.

        Parameters
        ----------
        field_snapshot  : dict from weather_service.get_field_snapshot()
        soil_nutrients  : dict from soil_service.get_soil_for_plot(), or None
        season          : "kharif" | "rabi" | "zaid"
        language        : ISO 639-1 code for response language
        previous_crops  : list of crop names grown in prior seasons, or None
        farm_size_acres : optional farm size in acres
        farmer_notes    : optional free-text from the farmer (in any language)
        """
        try:
            client = self._get_client()
        except RuntimeError as e:
            return {"error": str(e)}

        # Build the prompt
        prompt = _build_prompt(
            field_snapshot  = field_snapshot,
            soil_nutrients  = soil_nutrients,
            season          = season,
            language        = language,
            previous_crops  = previous_crops,
            farm_size_acres = farm_size_acres,
            farmer_notes    = farmer_notes,
        )

        logger.info(
            "Sending crop recommendation prompt to Gemini (%s, season=%s, lang=%s)",
            GEMINI_MODEL, season, language,
        )

        try:
            response = await client.aio.models.generate_content(
                model    = GEMINI_MODEL,
                contents = prompt,
                config   = genai_types.GenerateContentConfig(
                    temperature = 0.3,
                    top_p       = 0.9,
                    # No max_output_tokens cap -- let Gemini return the full response
                ),
            )
            raw_text = response.text
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            return {"error": f"Gemini API error: {exc}"}

        # Parse the JSON response
        result = _extract_json(raw_text)
        if result is None:
            logger.warning("Gemini returned non-JSON. Raw: %s", raw_text[:500])
            return {
                "error":    "Gemini returned an unstructured response.",
                "raw_text": raw_text,
            }

        logger.info("Crop recommendation generated successfully.")
        return result

    async def generate_advice(self, weather_data: dict, soil_data: dict, crop: str) -> str:
        """
        Legacy method stub -- kept for backward compatibility with existing routers.
        Delegates to get_crop_recommendation with minimal inputs.
        """
        snapshot = {"current": weather_data, "forecast": {}, "satellite_soil": {}}
        result = await self.get_crop_recommendation(
            field_snapshot = snapshot,
            soil_nutrients = soil_data,
            farmer_notes   = f"Farmer is asking about {crop}",
        )
        if "error" in result:
            return f"Could not generate advice: {result['error']}"
        return result.get("general_advisory", "No advice generated.")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    field_snapshot:  dict,
    soil_nutrients:  dict | None,
    season:          str,
    language:        str,
    previous_crops:  list[str] | None,
    farm_size_acres: float | None,
    farmer_notes:    str | None,
) -> str:
    """Assemble the full Gemini prompt as a single formatted string."""

    season_label   = SEASON_LABELS.get(season, season)
    lang_label     = {"en": "English", "hi": "Hindi", "te": "Telugu"}.get(language, "English")

    # ---- Section 1: Weather forecast ----------------------------------------
    fc = field_snapshot.get("forecast", {})
    if "error" in fc:
        fc_block = "  [Weather forecast data unavailable]"
    else:
        fc_block = (
            f"  5-day rainfall total : {fc.get('rainfall_next_5d_mm', 'N/A')} mm\n"
            f"  Average temperature  : {fc.get('avg_temp_c', 'N/A')} C\n"
            f"  Condition summary    : {fc.get('condition_summary', 'N/A')}"
        )

    # ---- Section 2: Current weather -----------------------------------------
    cur = field_snapshot.get("current", {})
    if "error" in cur:
        cur_block = "  [Current weather data unavailable]"
    else:
        cur_block = (
            f"  Temperature          : {cur.get('temp_c', 'N/A')} C "
            f"(feels like {cur.get('feels_like_c', 'N/A')} C)\n"
            f"  Humidity             : {cur.get('humidity_pct', 'N/A')}%\n"
            f"  Wind speed           : {cur.get('wind_speed_ms', 'N/A')} m/s\n"
            f"  Cloud cover          : {cur.get('cloud_cover_pct', 'N/A')}%\n"
            f"  Condition            : {cur.get('condition', 'N/A')}"
        )

    # ---- Section 3: Satellite soil ------------------------------------------
    sat = field_snapshot.get("satellite_soil", {})
    if "error" in sat:
        sat_block = "  [Satellite soil data unavailable]"
    else:
        sat_block = (
            f"  Soil moisture        : {sat.get('soil_moisture', 'N/A')} m3/m3 "
            f"[{sat.get('moisture_status', 'N/A').upper()}]\n"
            f"  Surface temperature  : {sat.get('surface_temp_c', 'N/A')} C\n"
            f"  Soil temp at 10 cm   : {sat.get('soil_temp_10cm_c', 'N/A')} C"
        )

    # ---- Section 4: UV ------------------------------------------------------
    uv_block = (
        f"  UV index             : {field_snapshot.get('uv_index', 'N/A')} "
        f"[{field_snapshot.get('uv_risk', 'N/A').upper()}]"
    )

    # ---- Section 5: Agronomic soil nutrients --------------------------------
    if soil_nutrients and "error" not in soil_nutrients:
        src = soil_nutrients.get("source", "unknown")
        nut_block = (
            f"  Nitrogen (N)         : {soil_nutrients.get('n', 'N/A')} kg/ha\n"
            f"  Phosphorus (P)       : {soil_nutrients.get('p', 'N/A')} kg/ha\n"
            f"  Potassium (K)        : {soil_nutrients.get('k', 'N/A')} kg/ha\n"
            f"  Soil pH              : {soil_nutrients.get('ph', 'N/A')}\n"
            f"  Organic carbon       : {soil_nutrients.get('organic_carbon', 'N/A')} %\n"
            f"  Data source          : {src}"
        )
    else:
        nut_block = "  [Soil nutrient data unavailable -- using general regional averages]"

    # ---- Section 6: Farm context --------------------------------------------
    prev_str  = ", ".join(previous_crops) if previous_crops else "None provided (assume no rotation constraint)"
    size_str  = f"{farm_size_acres} acres" if farm_size_acres else "Not specified"
    notes_str = farmer_notes or "None"

    # ---- Assemble -----------------------------------------------------------
    prompt = f"""You are an expert agricultural advisor specializing in Indian farming systems, 
particularly in Andhra Pradesh, Madhya Pradesh, and neighbouring states.

Your task: Generate a detailed, actionable CROP RECOMMENDATION for a farmer based on 
the real-time field data provided below.

== FARM CONTEXT ==
  Season               : {season_label}
  Farm size            : {size_str}
  Previous crops grown : {prev_str}
  Farmer notes         : {notes_str}

== WEATHER FORECAST (next 5 days) ==
{fc_block}

== CURRENT WEATHER CONDITIONS ==
{cur_block}

== SATELLITE SOIL CONDITIONS (from MODIS/Copernicus) ==
{sat_block}

{uv_block}

== AGRONOMIC SOIL HEALTH (NPK / pH) ==
{nut_block}

== YOUR INSTRUCTIONS ==
1. Recommend the TOP 3 most suitable crops for this farm RIGHT NOW.
2. For each crop, explain WHY it suits the current conditions (weather + soil).
3. Factor in crop rotation -- avoid recommending the same crop as previous season if possible.
4. Give irrigation advice based on soil moisture and forecast rainfall.
5. Give fertiliser advice based on N, P, K levels and crop requirements.
6. Flag any risks (heat stress, flood risk, disease pressure from high humidity, etc).
7. Be practical and specific -- give sowing windows, expected yield ranges, water requirements.

== OUTPUT FORMAT ==
Respond ONLY with a single valid JSON object. Do NOT wrap it in markdown code blocks.
Do NOT add any text outside the JSON.

{{
  "recommendations": [
    {{
      "crop":           "<crop name and variety>",
      "reason":         "<why this crop suits current conditions>",
      "sowing_window":  "<date range, e.g. 15 Jul - 10 Aug>",
      "water_need":     "<water requirement, e.g. High - 1000 mm/season>",
      "expected_yield": "<yield range, e.g. 5-6 tonnes/ha>",
      "warnings":       ["<risk 1>", "<risk 2>"]
    }}
  ],
  "irrigation_advice":  "<specific advice based on soil moisture and forecast>",
  "fertiliser_advice":  "<specific NPK advice based on soil nutrient levels>",
  "general_advisory":   "<overall advisory in 2-3 sentences>",
  "data_quality_notes": ["<any flagged missing data or low-confidence inputs>"]
}}

Respond in {lang_label}.
"""

    return prompt


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    """
    Extract JSON object from Gemini response text.
    Handles:
      - Markdown code fences (```json ... ```)
      - Leading/trailing whitespace
      - Truncated JSON (attempts best-effort recovery)
    """
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$",          "", text, flags=re.MULTILINE)
    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding the outermost {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Last resort: attempt to close truncated JSON
    # Find the last complete top-level key-value and close the object
    truncated = text
    for closing in ["]}", "}", '"]}']:
        try:
            return json.loads(truncated + closing)
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
advisor_service = AdvisorService()
