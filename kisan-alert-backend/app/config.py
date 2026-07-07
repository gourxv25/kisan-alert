from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    GEMINI_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    AGROMONITORING_API_KEY: str = ""
    AGROMONITORING_POLYGON_ID: str = ""  # Default polygon for weather lookups
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""

    # Scheduler — drought alert threshold.
    # Plots with forecast rainfall below this value (mm over next 5 days) will
    # receive a WhatsApp irrigation advisory.
    LOW_RAIN_THRESHOLD_MM: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()