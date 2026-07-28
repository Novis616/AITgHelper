from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_request_log import AiRequestLog
from app.models.base import utc_now
from app.security.encryption import decrypt_text, encrypt_text


class AiRequestLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        provider: str,
        model: str,
        user_text: str,
        user_id: int | None = None,
        prompt: str | None = None,
        raw_response: str | None = None,
        normalized_intent: str | None = None,
        confidence: float | None = None,
        error_text: str | None = None,
    ) -> AiRequestLog:
        log = AiRequestLog(
            user_id=user_id,
            provider=provider,
            model=model,
            user_text=encrypt_text(user_text) or "",
            prompt=encrypt_text(prompt),
            raw_response=encrypt_text(raw_response),
            normalized_intent=normalized_intent,
            confidence=confidence,
            error_text=encrypt_text(error_text),
            created_at=utc_now(),
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def list_for_user(self, user_id: int, *, limit: int = 20) -> list[AiRequestLog]:
        stmt: Select[tuple[AiRequestLog]] = (
            select(AiRequestLog)
            .where(AiRequestLog.user_id == user_id)
            .order_by(desc(AiRequestLog.created_at), desc(AiRequestLog.id))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_plaintext_log(log) for log in result.scalars().all()]

    def _to_plaintext_log(self, log: AiRequestLog) -> AiRequestLog:
        return AiRequestLog(
            id=log.id,
            user_id=log.user_id,
            provider=log.provider,
            model=log.model,
            user_text=decrypt_text(log.user_text) or "",
            prompt=decrypt_text(log.prompt),
            raw_response=decrypt_text(log.raw_response),
            normalized_intent=log.normalized_intent,
            confidence=log.confidence,
            error_text=decrypt_text(log.error_text),
            created_at=log.created_at,
        )
