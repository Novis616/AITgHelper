from __future__ import annotations

from openai import AsyncOpenAI, OpenAIError

from app.ai.base import OpenAiCompatibleClient
from app.ai.errors import AiClientError


class OpenAiClient(OpenAiCompatibleClient):
    provider = "openai"

    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._client is None:
            raise AiClientError("OpenAI API key is not configured")
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
            raise AiClientError("OpenAI request failed") from exc

        content = response.choices[0].message.content
        if not content:
            raise AiClientError("OpenAI returned an empty response")
        return content
