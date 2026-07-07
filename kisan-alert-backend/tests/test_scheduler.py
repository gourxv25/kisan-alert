"""
Unit tests for app/services/scheduler.py

Covers:
  - check_and_alert: happy path (alert sent, skipped, error branches)
  - _build_alert_message: language template formatting
  - POST /admin/trigger-alerts endpoint
"""
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

backend_path = r"c:\Users\ssr\Desktop\Kisan-Alert\kisan-alert-backend"
sys.path.insert(0, backend_path)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── helpers ────────────────────────────────────────────────────────────────────

def _fake_farmer(phone="+919876543210", language="en"):
    return {"id": "farmer_1", "phone": phone, "language": language, "name": "Ramesh"}

def _fake_plot(farmer_id="farmer_1", crop="Rice", poly_id=None):
    return {"id": "plot_1", "farmer_id": farmer_id,
            "crop_current": crop, "poly_id": poly_id}


# ── 1. _build_alert_message ────────────────────────────────────────────────────

class TestBuildAlertMessage(unittest.TestCase):

    def test_english_template(self):
        from app.services.scheduler import _build_alert_message
        msg = _build_alert_message("en", rain_mm=3.5, crop="Wheat")
        self.assertIn("3.5", msg)
        self.assertIn("Wheat", msg)
        self.assertIn("irrigat", msg.lower())

    def test_telugu_template(self):
        from app.services.scheduler import _build_alert_message
        msg = _build_alert_message("te", rain_mm=7.0, crop="Rice")
        self.assertIn("7.0", msg)
        self.assertIn("Rice", msg)

    def test_hindi_template(self):
        from app.services.scheduler import _build_alert_message
        msg = _build_alert_message("hi", rain_mm=2.0, crop="Bajra")
        self.assertIn("2.0", msg)
        self.assertIn("Bajra", msg)

    def test_unknown_language_falls_back_to_english(self):
        from app.services.scheduler import _build_alert_message
        msg = _build_alert_message("xx", rain_mm=1.0, crop="Maize")
        self.assertIn("Maize", msg)
        self.assertIn("1.0", msg)

    def test_empty_crop_replaced_with_generic(self):
        from app.services.scheduler import _build_alert_message
        msg = _build_alert_message("en", rain_mm=5.0, crop="")
        # "crop" appears generically in the message
        self.assertIn("crop", msg.lower())


# ── 2. check_and_alert core logic ─────────────────────────────────────────────

class TestCheckAndAlert(unittest.IsolatedAsyncioTestCase):

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_alert_sent_when_rain_below_threshold(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """Rain < 10 mm → alert sent, whatsapp called once."""
        mock_plots.return_value = [_fake_plot()]
        mock_weather.get_forecast = AsyncMock(
            return_value={"rainfall_next_5d_mm": 4.0, "avg_temp_c": 32.0}
        )
        mock_farmer.return_value = _fake_farmer(language="en")
        mock_send.return_value = {"sid": "SM123", "status": "queued"}

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["plots_checked"], 1)
        self.assertEqual(result["alerts_sent"], 1)
        self.assertEqual(result["alerts_skipped"], 0)
        self.assertEqual(result["errors"], 0)
        mock_send.assert_called_once()
        # message must mention rain and crop
        sent_body = mock_send.call_args[1]["body"]
        self.assertIn("4.0", sent_body)
        self.assertIn("Rice", sent_body)

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_no_alert_when_rain_above_threshold(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """Rain >= 10 mm → skipped, whatsapp NOT called."""
        mock_plots.return_value = [_fake_plot()]
        mock_weather.get_forecast = AsyncMock(
            return_value={"rainfall_next_5d_mm": 25.0, "avg_temp_c": 28.0}
        )
        mock_farmer.return_value = _fake_farmer()

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["alerts_sent"], 0)
        self.assertEqual(result["alerts_skipped"], 1)
        mock_send.assert_not_called()

    @patch("app.services.scheduler.get_all_plots")
    async def test_no_plots_returns_zero_counts(self, mock_plots):
        """Empty plot list → all zeros, no errors."""
        mock_plots.return_value = []
        from app.services.scheduler import check_and_alert
        result = await check_and_alert()
        self.assertEqual(result["plots_checked"], 0)
        self.assertEqual(result["errors"], 0)

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_weather_error_counted_as_error(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """Weather API returns an error dict → counted as error, no WhatsApp."""
        mock_plots.return_value = [_fake_plot()]
        mock_weather.get_forecast = AsyncMock(
            return_value={"error": "HTTP 403"}
        )

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["alerts_sent"], 0)
        mock_send.assert_not_called()

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_farmer_not_found_counted_as_error(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """Farmer lookup returns None → error, WhatsApp not sent."""
        mock_plots.return_value = [_fake_plot()]
        mock_weather.get_forecast = AsyncMock(
            return_value={"rainfall_next_5d_mm": 2.0, "avg_temp_c": 35.0}
        )
        mock_farmer.return_value = None  # farmer not found

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["alerts_sent"], 0)
        mock_send.assert_not_called()

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_multiple_plots_mixed_results(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """3 plots: 1 alert, 1 skipped, 1 weather error → correct counts."""
        mock_plots.return_value = [
            {"id": "p1", "farmer_id": "f1", "crop_current": "Rice",   "poly_id": None},
            {"id": "p2", "farmer_id": "f2", "crop_current": "Wheat",  "poly_id": None},
            {"id": "p3", "farmer_id": "f3", "crop_current": "Cotton", "poly_id": None},
        ]
        forecasts = [
            {"rainfall_next_5d_mm": 3.0,  "avg_temp_c": 34.0},   # p1 → alert
            {"rainfall_next_5d_mm": 20.0, "avg_temp_c": 29.0},   # p2 → skip
            {"error": "timeout"},                                   # p3 → error
        ]
        mock_weather.get_forecast = AsyncMock(side_effect=forecasts)
        mock_farmer.return_value = _fake_farmer()
        mock_send.return_value = {"sid": "SM999", "status": "queued"}

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["plots_checked"],  3)
        self.assertEqual(result["alerts_sent"],    1)
        self.assertEqual(result["alerts_skipped"], 1)
        self.assertEqual(result["errors"],         1)

    @patch("app.services.scheduler.send_whatsapp_message")
    @patch("app.services.scheduler.get_farmer_by_id")
    @patch("app.services.scheduler.weather_service")
    @patch("app.services.scheduler.get_all_plots")
    async def test_telugu_farmer_gets_telugu_message(
        self, mock_plots, mock_weather, mock_farmer, mock_send
    ):
        """Telugu farmer receives message with Telugu Unicode characters."""
        mock_plots.return_value = [_fake_plot(crop="Paddy")]
        mock_weather.get_forecast = AsyncMock(
            return_value={"rainfall_next_5d_mm": 1.0, "avg_temp_c": 36.0}
        )
        mock_farmer.return_value = _fake_farmer(language="te")
        mock_send.return_value = {"sid": "SM_TE", "status": "queued"}

        from app.services.scheduler import check_and_alert
        result = await check_and_alert()

        self.assertEqual(result["alerts_sent"], 1)
        sent_body = mock_send.call_args[1]["body"]
        # Telugu script has a recognisable Unicode range (U+0C00–U+0C7F)
        has_telugu = any("\u0c00" <= c <= "\u0c7f" for c in sent_body)
        self.assertTrue(has_telugu, f"Expected Telugu characters in: {sent_body!r}")


# ── 3. POST /admin/trigger-alerts ─────────────────────────────────────────────

class TestAdminTriggerEndpoint(unittest.TestCase):

    @patch("app.main.check_and_alert")
    def test_trigger_alerts_returns_summary(self, mock_job):
        """POST /admin/trigger-alerts returns the job result JSON."""
        import asyncio
        async def fake_job():
            return {
                "plots_checked": 5, "alerts_sent": 2,
                "alerts_skipped": 2, "errors": 1, "detail": [],
            }
        mock_job.side_effect = fake_job

        resp = client.post("/admin/trigger-alerts")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["plots_checked"], 5)
        self.assertEqual(body["alerts_sent"], 2)
        self.assertIn("detail", body)

    def test_trigger_alerts_no_body_required(self):
        """Endpoint accepts POST with no request body."""
        with patch("app.main.check_and_alert") as mock_job:
            async def fake_job():
                return {"plots_checked": 0, "alerts_sent": 0,
                        "alerts_skipped": 0, "errors": 0, "detail": []}
            mock_job.side_effect = fake_job
            resp = client.post("/admin/trigger-alerts")
            self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
