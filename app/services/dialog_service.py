from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.config.settings import Settings, get_settings
from app.repositories import DialogStateRepository, UserRepository
from app.schemas.dialog_state import CreateDialogStateInput, DialogStateRead


class DialogService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.states = DialogStateRepository(session)

    async def create_dialog_state(
        self,
        data: CreateDialogStateInput,
    ) -> DialogStateRead:
        state_type = data.state_type.strip()
        if not state_type:
            raise ValidationError("state_type must not be empty")

        user = await self.users.get_or_create(
            telegram_id=data.telegram_id,
            language=data.language,
            timezone=data.timezone or self.settings.default_timezone,
        )
        active = await self.states.get_active_for_user(user.id)
        if active is not None:
            await self.states.cancel(active)

        state = await self.states.create(
            user_id=user.id,
            state_type=state_type,
            payload=data.payload,
            expires_at=data.expires_at,
            status="active",
        )
        await self.session.commit()
        return DialogStateRead.model_validate(state)

    async def get_active_dialog_state(
        self,
        *,
        telegram_id: int,
    ) -> DialogStateRead | None:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return None
        state = await self.states.get_active_for_user(user.id)
        if state is None:
            return None
        return DialogStateRead.model_validate(state)

    async def update_payload(
        self,
        *,
        telegram_id: int,
        payload: dict[str, Any],
    ) -> DialogStateRead:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Active dialog state not found")
        state = await self.states.get_active_for_user(user.id)
        if state is None:
            raise NotFoundError("Active dialog state not found")
        state = await self.states.update_payload(state, payload)
        await self.session.commit()
        return DialogStateRead.model_validate(state)

    async def complete_dialog_state(self, *, telegram_id: int) -> DialogStateRead:
        return await self._finish_active(telegram_id=telegram_id, action="complete")

    async def cancel_dialog_state(self, *, telegram_id: int) -> DialogStateRead:
        return await self._finish_active(telegram_id=telegram_id, action="cancel")

    async def _finish_active(
        self,
        *,
        telegram_id: int,
        action: str,
    ) -> DialogStateRead:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Active dialog state not found")
        state = await self.states.get_active_for_user(user.id)
        if state is None:
            raise NotFoundError("Active dialog state not found")

        if action == "complete":
            state = await self.states.complete(state)
        else:
            state = await self.states.cancel(state)
        await self.session.commit()
        return DialogStateRead.model_validate(state)
