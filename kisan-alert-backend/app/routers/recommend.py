"""
Crop Recommendation API Router

POST /recommend/crop
    Body: CropRecommendationRequest
    Returns: CropRecommendationResponse

The endpoint:
  1. Fetches live field conditions via Agromonitoring (weather + satellite soil)
  2. Resolves agronomic soil nutrients from village defaults or SHC
  3. Passes everything to the Gemini advisor and returns structured JSON
"""

import types
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.weather import weather_service
from app.services.soil    import soil_service
from app.services.advisor import advisor_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommend", tags=["Crop Recommendation"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CropRecommendationRequest(BaseModel):
    """
    All fields except village_id / soil_data_ref are optional so the farmer
    can submit minimal data and still get a useful recommendation.
    """

    # -- Farm identification --
    village_id: Optional[str] = Field(
        default=None,
        description="Village ID to look up default soil data (e.g. 'village_001')",
        examples=["village_001"],
    )
    soil_data_ref: Optional[str] = Field(
        default=None,
        description=(
            "Soil Health Card ID (e.g. 'SHC-AP-GNT-2024-00142') OR "
            "'village_default:<village_id>' to use village averages"
        ),
        examples=["village_default:village_001"],
    )

    # -- Agromonitoring polygon override --
    poly_id: Optional[str] = Field(
        default=None,
        description=(
            "Agromonitoring polygon ID. Defaults to AGROMONITORING_POLYGON_ID from .env. "
            "Pass a different ID if the farm has its own registered polygon."
        ),
    )

    # -- Season & language --
    season: str = Field(
        default="kharif",
        description="Current/intended cropping season",
        pattern="^(kharif|rabi|zaid)$",
        examples=["kharif"],
    )
    language: str = Field(
        default="en",
        description="Response language: en (English) | hi (Hindi) | te (Telugu)",
        pattern="^(en|hi|te)$",
        examples=["en"],
    )

    # -- Historical context --
    previous_crops: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of crops grown in previous seasons (most recent first). "
            "Leave empty or null if unknown."
        ),
        examples=[["rice", "wheat"]],
    )

    # -- Farm details --
    farm_size_acres: Optional[float] = Field(
        default=None,
        description="Farm / plot size in acres",
        ge=0.1,
        examples=[2.5],
    )
    farmer_notes: Optional[str] = Field(
        default=None,
        description="Any additional context from the farmer (in any language)",
        max_length=500,
        examples=["My soil gets waterlogged during heavy rains"],
    )

    model_config = {"json_schema_extra": {
        "example": {
            "village_id":     "village_001",
            "soil_data_ref":  "village_default:village_001",
            "season":         "kharif",
            "language":       "en",
            "previous_crops": ["rice"],
            "farm_size_acres": 3.0,
            "farmer_notes":   "I have a borewell for irrigation",
        }
    }}


class CropRecommendationResponse(BaseModel):
    success:          bool
    field_snapshot:   dict = Field(description="Raw field conditions fetched from Agromonitoring")
    soil_nutrients:   Optional[dict] = Field(description="Soil nutrient data used for recommendation")
    recommendation:   dict = Field(description="Gemini crop recommendation (structured JSON)")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/crop",
    response_model=CropRecommendationResponse,
    summary="Get AI crop recommendation",
    description=(
        "Fetches live field conditions (weather, satellite soil, UV) from Agromonitoring "
        "and passes them — together with soil nutrients and historical crop data — to "
        "Gemini 2.0 Flash to generate a structured crop recommendation."
    ),
)
async def recommend_crop(request: CropRecommendationRequest):
    """
    Full pipeline:
      Agromonitoring field snapshot + SoilService nutrients -> Gemini -> JSON recommendation
    """

    # ---- Step 1: Fetch live field conditions --------------------------------
    logger.info("Fetching field snapshot for polygon: %s", request.poly_id or "default")
    field_snapshot = await weather_service.get_field_snapshot(poly_id=request.poly_id)

    if "error" in field_snapshot:
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch field conditions: {field_snapshot['error']}",
        )

    # ---- Step 2: Resolve soil nutrients -------------------------------------
    soil_nutrients: dict | None = None
    if request.village_id or request.soil_data_ref:
        # Build a minimal plot-like object from the request fields
        plot = types.SimpleNamespace(
            soil_data_ref = request.soil_data_ref,
            village_id    = request.village_id,
        )
        soil_nutrients = soil_service.get_soil_for_plot(plot)
        if soil_nutrients is None:
            logger.warning(
                "Could not resolve soil nutrients for village_id=%r, soil_data_ref=%r. "
                "Proceeding without NPK data.",
                request.village_id,
                request.soil_data_ref,
            )

    # ---- Step 3: Call Gemini advisor ----------------------------------------
    logger.info(
        "Requesting Gemini recommendation (season=%s, lang=%s, prev_crops=%s)",
        request.season,
        request.language,
        request.previous_crops,
    )
    recommendation = await advisor_service.get_crop_recommendation(
        field_snapshot  = field_snapshot,
        soil_nutrients  = soil_nutrients,
        season          = request.season,
        language        = request.language,
        previous_crops  = request.previous_crops,
        farm_size_acres = request.farm_size_acres,
        farmer_notes    = request.farmer_notes,
    )

    if "error" in recommendation and "raw_text" not in recommendation:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini advisor error: {recommendation['error']}",
        )

    return CropRecommendationResponse(
        success        = True,
        field_snapshot = field_snapshot,
        soil_nutrients = soil_nutrients,
        recommendation = recommendation,
    )
