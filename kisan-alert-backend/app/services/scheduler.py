"""
Scheduler service — proactive drought/irrigation alerts.

Job: check_and_alert()
  - Fetches every plot from Firestore
  - For each plot, fetches 5-day rainfall forecast from Agromonitoring
  - If forecast rainfall < LOW_RAIN_THRESHOLD_MM (default 10 mm), sends a
    WhatsApp message to the plot's farmer in their preferred language
  - Logs one line per plot regardless of whether an alert was sent

Scheduling:
  - Wired to APScheduler's AsyncIOScheduler (runs every 6 hours)
  - Also exposed via POST /admin/trigger-alerts for on-demand demo runs
"""

import asyncio
import logging
from typing import Optional

from app.config import settings
from app.services.db import get_all_plots, get_farmer_by_id
from app.services.weather import weather_service
from app.services.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)

# ── Alert message templates ────────────────────────────────────────────────────
# Keys must match the language codes stored on farmer documents.
_ALERT_TEMPLATES: dict[str, str] = {
    "te": (
        "⚠️ *వర్షపాత హెచ్చరిక*: వచ్చే 7 రోజుల్లో తక్కువ వర్షం ({rain_mm:.1f} mm) అంచనా. "
        "మీ *{crop}* పంటకు నీటిపారుదల చేయాలని పరిగణించండి."
    ),
    "hi": (
        "⚠️ *वर्षा चेतावनी*: अगले 7 दिनों में कम बारिश ({rain_mm:.1f} mm) की संभावना है। "
        "कृपया अपनी *{crop}* फसल की सिंचाई पर विचार करें।"
    ),
    "en": (
        "⚠️ *Low Rain Alert*: Only {rain_mm:.1f} mm of rainfall expected in the next 7 days. "
        "Consider irrigating your *{crop}* plot."
    ),
}

_DEFAULT_LANG = "en"


def _build_alert_message(language: str, rain_mm: float, crop: str) -> str:
    """Return a formatted alert string in the farmer's language."""
    template = _ALERT_TEMPLATES.get(language, _ALERT_TEMPLATES[_DEFAULT_LANG])
    crop_label = crop.strip() or "crop"
    return template.format(rain_mm=rain_mm, crop=crop_label)


# ── Core alert job ─────────────────────────────────────────────────────────────

async def check_and_alert() -> dict:
    """
    Main scheduler job.

    Iterates over all plots and sends a WhatsApp drought alert to the
    plot's farmer when forecast rainfall is below LOW_RAIN_THRESHOLD_MM.

    Returns a summary dict useful for the /admin/trigger-alerts endpoint:
      {
          "plots_checked": int,
          "alerts_sent":   int,
          "alerts_skipped":int,   # sufficient rain expected
          "errors":        int,   # weather fetch or WhatsApp failures
          "detail":        list[dict]  # per-plot log lines
      }
    """
    threshold = settings.LOW_RAIN_THRESHOLD_MM
    logger.info(
        "check_and_alert: starting run. threshold=%.1f mm", threshold
    )

    plots   = get_all_plots()
    total   = len(plots)
    sent    = 0
    skipped = 0
    errors  = 0
    detail: list[dict] = []

    if not plots:
        logger.info("check_and_alert: no plots found, nothing to do.")
        return {
            "plots_checked": 0,
            "alerts_sent": 0,
            "alerts_skipped": 0,
            "errors": 0,
            "detail": [],
        }

    for plot in plots:
        plot_id     = plot.get("id", "unknown")
        farmer_id   = plot.get("farmer_id", "")
        crop        = plot.get("crop_current", "crop") or "crop"
        poly_id     = plot.get("poly_id") or None  # optional Agromonitoring polygon

        entry = {
            "plot_id":   plot_id,
            "farmer_id": farmer_id,
            "crop":      crop,
            "action":    None,
            "rain_mm":   None,
            "error":     None,
        }

        # ── 1. Fetch weather forecast ─────────────────────────────────────────
        try:
            forecast = await weather_service.get_forecast(poly_id=poly_id)
        except Exception as exc:
            logger.error(
                "check_and_alert [plot=%s]: weather fetch failed: %s", plot_id, exc
            )
            entry["action"] = "error"
            entry["error"]  = f"weather_fetch: {exc}"
            errors += 1
            detail.append(entry)
            continue

        # Forecast may have returned an error dict (no API key, bad polygon, etc.)
        if "error" in forecast:
            logger.warning(
                "check_and_alert [plot=%s]: forecast error: %s", plot_id, forecast["error"]
            )
            entry["action"] = "error"
            entry["error"]  = forecast["error"]
            errors += 1
            detail.append(entry)
            continue

        rain_mm = forecast.get("rainfall_next_5d_mm", 0.0)
        entry["rain_mm"] = rain_mm

        # ── 2. Check threshold ────────────────────────────────────────────────
        if rain_mm >= threshold:
            logger.info(
                "check_and_alert [plot=%s]: %.1f mm >= %.1f mm threshold — no alert.",
                plot_id, rain_mm, threshold,
            )
            entry["action"] = "skipped"
            skipped += 1
            detail.append(entry)
            continue

        # ── 3. Look up farmer for phone number and language ───────────────────
        farmer: Optional[dict] = None
        if farmer_id:
            try:
                farmer = get_farmer_by_id(farmer_id)
            except Exception as exc:
                logger.error(
                    "check_and_alert [plot=%s]: farmer lookup failed: %s", plot_id, exc
                )

        if not farmer:
            logger.warning(
                "check_and_alert [plot=%s]: farmer '%s' not found — cannot send alert.",
                plot_id, farmer_id,
            )
            entry["action"] = "error"
            entry["error"]  = f"farmer_not_found: {farmer_id}"
            errors += 1
            detail.append(entry)
            continue

        farmer_phone    = farmer.get("phone", "")
        farmer_language = farmer.get("language", "en")

        if not farmer_phone:
            logger.warning(
                "check_and_alert [plot=%s]: farmer has no phone — skipping.", plot_id
            )
            entry["action"] = "error"
            entry["error"]  = "no_phone"
            errors += 1
            detail.append(entry)
            continue

        # ── 4. Build and send the alert ───────────────────────────────────────
        message = _build_alert_message(
            language=farmer_language,
            rain_mm=rain_mm,
            crop=crop,
        )

        try:
            result = send_whatsapp_message(to_phone=farmer_phone, body=message)
            sid    = result.get("sid", "unknown")
            status = result.get("status", "unknown")
            logger.info(
                "check_and_alert [plot=%s]: alert sent to %s | rain=%.1f mm | "
                "sid=%s status=%s",
                plot_id, farmer_phone, rain_mm, sid, status,
            )
            entry["action"] = "alert_sent"
            sent += 1
        except Exception as exc:
            logger.error(
                "check_and_alert [plot=%s]: WhatsApp send failed: %s", plot_id, exc
            )
            entry["action"] = "error"
            entry["error"]  = f"whatsapp_send: {exc}"
            errors += 1

        detail.append(entry)

    logger.info(
        "check_and_alert: done. plots=%d sent=%d skipped=%d errors=%d",
        total, sent, skipped, errors,
    )

    return {
        "plots_checked":  total,
        "alerts_sent":    sent,
        "alerts_skipped": skipped,
        "errors":         errors,
        "detail":         detail,
    }


# ── APScheduler setup (imported by main.py) ────────────────────────────────────

def create_scheduler():
    """
    Create and return a configured AsyncIOScheduler.

    The caller (main.py lifespan) is responsible for starting and shutting
    it down so the scheduler shares the same asyncio event loop as FastAPI.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_alert,
        trigger="interval",
        hours=6,
        id="drought_alert",
        replace_existing=True,
        max_instances=1,        # never run two overlapping instances
        misfire_grace_time=300, # allow up to 5 min late start after restart
    )
    return scheduler
