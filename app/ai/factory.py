from app.ai.base import AiClient
from app.ai.openai_client import OpenAiClient
from app.ai.openrouter_client import OpenRouterClient
from app.config.settings import Settings


def create_ai_client(settings: Settings) -> AiClient:
    if settings.ai_provider == "openrouter":
        return OpenRouterClient(
            api_key=settings.openrouter_api_key,
            model=settings.ai_model,
        )
    return OpenAiClient(
        api_key=settings.openai_api_key,
        model=settings.ai_model,
    )
