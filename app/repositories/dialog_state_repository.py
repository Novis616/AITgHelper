from datetime import datetime
from typing import Any

from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dialog_state import DialogState
from app.security.encryption import encrypt_json


class DialogStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        state_type: str,
        payload: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
        status: str = "active",
    ) -> DialogState:
        state = DialogState(
            user_id=user_id,
            state_type=state_type,
            payload=encrypt_json(payload),
            expires_at=expires_at,
            status=status,
        )
        self.session.add(state)
        await self.session.flush()
        return state

    async def get_active_for_user(self, user_id: int) -> DialogState | None:
        stmt: Select[tuple[DialogState]] = (
            select(DialogState)
            .where(DialogState.user_id == user_id)
            .where(DialogState.status == "active")
            .order_by(desc(DialogState.updated_at), desc(DialogState.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_payload(
        self,
        state: DialogState,
        payload: dict[str, Any],
    ) -> DialogState:
        state.payload = encrypt_json(payload)
        await self.session.flush()
        return state

    async def complete(self, state: DialogState) -> DialogState:
        state.status = "completed"
        await self.session.flush()
        return state

    async def cancel(self, state: DialogState) -> DialogState:
        state.status = "cancelled"
        await self.session.flush()
        return state
