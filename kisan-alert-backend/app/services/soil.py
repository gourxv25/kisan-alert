"""
Soil service – resolves soil nutrient data for a farmer's plot.

Resolution order
----------------
1. If ``plot.soil_data_ref`` is a Soil Health Card (SHC) ID (i.e. it does NOT
   start with "village_default:"), the full SHC lookup is deferred (TODO).
2. Otherwise fall back to ``data/village_defaults.json`` keyed by
   ``plot.village_id``.

Returned dict schema (on success):
    {
        "n":              float,   # Nitrogen (kg/ha)
        "p":              float,   # Phosphorus (kg/ha)
        "k":              float,   # Potassium (kg/ha)
        "ph":             float,   # Soil pH
        "organic_carbon": float,   # Organic carbon (%)
        "source":         str      # "shc" | "village_default"
    }
Returns ``None`` when no data can be resolved.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Village-defaults file path ────────────────────────────────────────────────
# Resolved relative to this file so it works regardless of the CWD.
# __file__ = .../kisan-alert-backend/app/services/soil.py
# .parent        → .../kisan-alert-backend/app/services/
# .parent.parent → .../kisan-alert-backend/app/
# .parent.parent.parent → .../kisan-alert-backend/
_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "village_defaults.json"


def _load_village_defaults() -> dict[str, Any]:
    """Load village_defaults.json at module startup. Logs a warning if missing."""
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        villages: dict[str, Any] = raw.get("villages", {})
        logger.info("Loaded village soil defaults for %d village(s).", len(villages))
        return villages
    except FileNotFoundError:
        logger.error("village_defaults.json not found at %s", _DATA_FILE)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse village_defaults.json: %s", exc)
        return {}


# Module-level cache – loaded once on first import.
_VILLAGE_DEFAULTS: dict[str, Any] = _load_village_defaults()

# ── SHC ID detection ──────────────────────────────────────────────────────────
_VILLAGE_DEFAULT_PREFIX = "village_default:"


def _is_shc_id(ref: str) -> bool:
    """Return True when ref looks like an SHC ID rather than a village fallback key."""
    return bool(ref) and not ref.startswith(_VILLAGE_DEFAULT_PREFIX)


# ── Public API ────────────────────────────────────────────────────────────────

class SoilService:
    """Service to resolve soil nutrient data for a farmer's plot."""

    def get_soil_for_plot(self, plot: Any) -> dict[str, Any] | None:
        """
        Resolve soil data for *plot*.

        Parameters
        ----------
        plot:
            Any object (Pydantic model, dataclass, SimpleNamespace, …) that
            exposes ``soil_data_ref`` and ``village_id`` attributes.

        Returns
        -------
        dict | None
            Soil nutrient dict or ``None`` if no data could be resolved.
        """
        soil_ref: str | None = getattr(plot, "soil_data_ref", None)
        village_id: str | None = getattr(plot, "village_id", None)

        # ── Branch 1: SHC lookup ──────────────────────────────────────────
        if soil_ref and _is_shc_id(soil_ref):
            # TODO: Integrate Soil Health Card API / Supabase SHC table lookup.
            #       Return parsed N/P/K/pH/OC values with source="shc".
            logger.info(
                "SHC ID detected (%r) – lookup not yet implemented; returning None.",
                soil_ref,
            )
            return None

        # ── Branch 2: Village-default fallback ───────────────────────────
        if not village_id:
            logger.warning(
                "Plot has no SHC ref and no village_id – cannot resolve soil data."
            )
            return None

        village_data = _VILLAGE_DEFAULTS.get(village_id)
        if village_data is None:
            logger.warning(
                "village_id %r not found in village_defaults.json.", village_id
            )
            return None

        logger.info(
            "Resolved soil data for village_id=%r from village_defaults.", village_id
        )

        return {
            "n": village_data["n"],
            "p": village_data["p"],
            "k": village_data["k"],
            "ph": village_data["ph"],
            "organic_carbon": village_data["organic_carbon"],
            "source": "village_default",
        }


# ── Module-level singleton ────────────────────────────────────────────────────
soil_service = SoilService()
