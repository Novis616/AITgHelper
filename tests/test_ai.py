from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import OpenAiClient, OpenRouterClient, create_ai_client, parse_intent_response
from app.ai.base import AiClient
from app.ai.prompt_builder import build_user_prompt
from app.config.settings import Settings
from app.models import Base
from app.repositories import AiRequestLogRepository
from app.repositories.database import create_engine, create_session_factory
from app.schemas import AiInterpretationInput, IntentResult
from app.services import AiInterpretationService


def run(coro):
    return asyncio.run(coro)


async def make_session(tmp_path: Path) -> AsyncSession:
    database_path = tmp_path / "ai.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session.info["engine"] = engine
    return session


async def close_session(session: AsyncSession) -> None:
    engine = session.info["engine"]
    await session.close()
    await engine.dispose()


class FakeAiClient(AiClient):
    provider = "fake"
    model = "fake-model"

    def __init__(self, result: IntentResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[AiInterpretationInput] = []

    async def interpret_message(self, input_data: AiInterpretationInput) -> IntentResult:
        self.calls.append(input_data)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def test_parse_intent_response_accepts_valid_json() -> None:
    result = parse_intent_response(
        '{"intent":"create_note","parameters":{"content":"Idea"},'
        '"confidence":0.87,"clarification_question":null}'
    )

    assert result.intent == "create_note"
    assert result.parameters == {"content": "Idea"}
    assert result.confidence == 0.87
    assert result.clarification_question is None


def test_parse_intent_response_falls_back_for_invalid_json() -> None:
    result = parse_intent_response("not json")

    assert result.intent == "unknown"
    assert result.confidence == 0.0
    assert result.clarification_question is not None


def test_create_ai_client_uses_configured_provider() -> None:
    openai_client = create_ai_client(
        Settings(ai_provider="openai", ai_model="gpt-test", openai_api_key="test-key")
    )
    openrouter_client = create_ai_client(
        Settings(
            ai_provider="openrouter",
            ai_model="router-test",
            openrouter_api_key="test-key",
        )
    )

    assert isinstance(openai_client, OpenAiClient)
    assert openai_client.model == "gpt-test"
    assert isinstance(openrouter_client, OpenRouterClient)
    assert openrouter_client.model == "router-test"


def test_build_user_prompt_includes_known_categories() -> None:
    prompt = build_user_prompt(
        AiInterpretationInput(
            telegram_id=1,
            text="Save OZON link",
            language="en",
            known_categories=["Shopping"],
        )
    )

    assert '"known_categories": ["Shopping"]' in prompt


def test_ai_interpretation_service_logs_success(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            fake_client = FakeAiClient(
                result=IntentResult(
                    intent="create_reminder",
                    parameters={"text": "Buy milk", "remind_at": "2026-07-29T09:00:00"},
                    confidence=0.93,
                    clarification_question=None,
                    raw_response='{"intent":"create_reminder"}',
                )
            )
            service = AiInterpretationService(
                session,
                ai_client=fake_client,
                settings=Settings(default_timezone="UTC"),
            )

            result = await service.interpret_message(
                AiInterpretationInput(
                    telegram_id=7001,
                    text="Remind me tomorrow to buy milk",
                    language="en",
                    timezone="UTC",
                )
            )

            assert result.intent == "create_reminder"
            assert fake_client.calls[0].text == "Remind me tomorrow to buy milk"

            logs = await AiRequestLogRepository(session).list_for_user(1)
            assert len(logs) == 1
            assert logs[0].provider == "fake"
            assert logs[0].normalized_intent == "create_reminder"
            assert logs[0].confidence == 0.93
            assert logs[0].error_text is None
        finally:
            await close_session(session)

    run(scenario())


def test_ai_interpretation_service_logs_fallback_on_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = AiInterpretationService(
                session,
                ai_client=FakeAiClient(error=RuntimeError("network is unavailable")),
                settings=Settings(default_timezone="UTC"),
            )

            result = await service.interpret_message(
                AiInterpretationInput(
                    telegram_id=7002,
                    text="Save this",
                    language="en",
                )
            )

            assert result.intent == "unknown"
            assert result.confidence == 0.0
            assert result.clarification_question is not None

            logs = await AiRequestLogRepository(session).list_for_user(1)
            assert len(logs) == 1
            assert logs[0].normalized_intent == "unknown"
            assert "network is unavailable" in (logs[0].error_text or "")
        finally:
            await close_session(session)

    run(scenario())


def test_ai_interpretation_service_stores_sensitive_log_fields_encrypted(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            raw_response = '{"intent":"create_note","parameters":{"content":"secret"}}'
            service = AiInterpretationService(
                session,
                ai_client=FakeAiClient(
                    result=IntentResult(
                        intent="create_note",
                        parameters={"content": "secret"},
                        confidence=0.88,
                        raw_response=raw_response,
                    )
                ),
                settings=Settings(default_timezone="UTC"),
            )

            await service.interpret_message(
                AiInterpretationInput(
                    telegram_id=7003,
                    text="Save secret idea",
                    language="en",
                )
            )

            raw = (
                await session.execute(
                    text(
                        "SELECT user_text, prompt, raw_response "
                        "FROM ai_request_logs WHERE id = 1"
                    )
                )
            ).mappings().one()
            for value in raw.values():
                assert value.startswith("enc:v1:")
            assert "Save secret idea" not in raw["user_text"]
            assert "secret" not in raw["raw_response"]

            logs = await AiRequestLogRepository(session).list_for_user(1)
            assert logs[0].user_text == "Save secret idea"
            assert logs[0].raw_response == raw_response
        finally:
            await close_session(session)

    run(scenario())
