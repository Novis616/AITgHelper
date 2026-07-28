from __future__ import annotations

from abc import ABC, abstractmethod

from app.ai.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from app.ai.response_parser import parse_intent_response
from app.schemas.intent_result import AiInterpretationInput, IntentResult


class AiClient(ABC):
    provider: str
    model: str

    @abstractmethod
    async def interpret_message(self, input_data: AiInterpretationInput) -> IntentResult:
        """Interpret a user message into an MVP intent."""


class OpenAiCompatibleClient(AiClient):
    def build_prompt(self, input_data: AiInterpretationInput) -> str:
        return build_user_prompt(input_data)

    async def interpret_message(self, input_data: AiInterpretationInput) -> IntentResult:
        user_prompt = self.build_prompt(input_data)
        raw_response = await self.complete(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return parse_intent_response(raw_response)

    @abstractmethod
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return raw model text from an OpenAI-compatible chat endpoint."""
