from __future__ import annotations

from openai import AsyncOpenAI, OpenAIError

from app.ai.base import OpenAiCompatibleClient
from app.ai.errors import AiClientError


class OpenRouterClient(OpenAiCompatibleClient):
    provider = "openrouter"

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._client = (
            AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            )
            if api_key
            else None
        )

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            raise AiClientError("OpenRouter API key is not configured")
        if not self.model:
            raise AiClientError("AI model is not configured")

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
        except OpenAIError as exc:
            raise AiClientError("OpenRouter request failed") from exc

        content = response.choices[0].message.content
        if not content:
            raise AiClientError("OpenRouter returned an empty response")
        return content
