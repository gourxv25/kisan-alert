class AdvisorService:
    """Service to generate agricultural advice using Google Gemini AI."""

    async def generate_advice(self, weather_data: dict, soil_data: dict, crop: str) -> str:
        """
        Generate contextual advice for the farmer based on weather, soil metrics, and crop type
        using Google's Gemini AI.
        """
        # TODO: Implement Gemini API prompt construction and generation
        return "Stub advice: Ensure proper irrigation during dry spells."
