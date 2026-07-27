from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_request_log import AiRequestLog
from app.models.base import utc_now


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
            user_text=user_text,
            prompt=prompt,
            raw_response=raw_response,
            normalized_intent=normalized_intent,
            confidence=confidence,
            error_text=error_text,
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
        return list(result.scalars().all())
