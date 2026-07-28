from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import AiClient, create_ai_client
from app.ai.errors import AiClientError
from app.ai.prompt_builder import build_user_prompt
from app.config.settings import Settings, get_settings
from app.repositories import AiRequestLogRepository, UserRepository
from app.schemas.intent_result import AiInterpretationInput, IntentResult


class AiInterpretationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ai_client: AiClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ai_client = ai_client or create_ai_client(self.settings)
        self.users = UserRepository(session)
        self.logs = AiRequestLogRepository(session)

    async def interpret_message(
        self,
        input_data: AiInterpretationInput,
    ) -> IntentResult:
        user = await self.users.get_or_create(
            telegram_id=input_data.telegram_id,
            language=input_data.language or "ru",
            timezone=input_data.timezone or self.settings.default_timezone,
        )
        prompt = build_user_prompt(input_data)
        error_text: str | None = None

        try:
            result = await self.ai_client.interpret_message(input_data)
        except AiClientError as exc:
            error_text = str(exc)
            result = self._fallback_result()
        except Exception as exc:
            error_text = f"{exc.__class__.__name__}: {exc}"
            result = self._fallback_result()

        await self.logs.create(
            user_id=user.id,
            provider=self.ai_client.provider,
            model=self.ai_client.model,
            user_text=input_data.text,
            prompt=prompt,
            raw_response=result.raw_response,
            normalized_intent=result.intent,
            confidence=result.confidence,
            error_text=error_text,
        )
        await self.session.commit()
        return result

    def _fallback_result(self) -> IntentResult:
        return IntentResult(
            intent="unknown",
            parameters={},
            confidence=0.0,
            clarification_question=(
                "Сейчас не получилось разобрать запрос через AI. "
                "Можешь написать явно: сохранить заметку или создать напоминание?"
            ),
        )
