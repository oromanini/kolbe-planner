import asyncio
import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from backend import groq_client, server  # noqa: E402
from tests.test_finance_endpoints import FakeDB  # noqa: E402


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    fake_db = FakeDB()

    async def fake_user(*_args, **_kwargs):
        return SimpleNamespace(user_id="user_1")

    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server, "read_db", fake_db)
    monkeypatch.setattr(server, "get_current_user", fake_user)
    monkeypatch.setattr(server, "_assistant_last_call", {})
    monkeypatch.setattr(groq_client, "is_groq_configured", lambda: True)
    return fake_db


def seed_finance(fake_db):
    months = server._recent_months(server.ASSISTANT_CONTEXT_MONTHS)
    fake_db.expenses.docs.extend(
        [
            {
                "user_id": "user_1",
                "month": months[0],
                "name": "Mercado",
                "amount": 800.0,
                "category": "Alimentação",
            },
            {
                "user_id": "user_1",
                "month": months[0],
                "name": "Uber",
                "amount": 120.0,
                "category": "Transporte",
            },
            {
                "user_id": "other",
                "month": months[0],
                "name": "Não meu",
                "amount": 999.0,
                "category": "Outros",
            },
        ]
    )
    fake_db.incomes.docs.append(
        {
            "user_id": "user_1",
            "month": months[0],
            "name": "Salário",
            "amount": 5000.0,
            "category": "Renda",
        }
    )


def test_context_aggregates_only_current_user(fake_backend):
    seed_finance(fake_backend)
    context = run(server.build_user_finance_context("user_1"))
    assert "Mercado" in context
    assert "Não meu" not in context
    assert "5000" in context
    assert "Alimentação" in context


def test_chat_happy_path(fake_backend, monkeypatch):
    seed_finance(fake_backend)
    captured = {}

    def fake_request_chat(*, messages, **_kwargs):
        captured["messages"] = messages
        return "Seu maior gasto é Alimentação (R$ 800)."

    monkeypatch.setattr(server.groq_client, "request_chat", fake_request_chat)

    payload = run(
        server.finance_assistant_chat(
            server.AssistantChatRequest(
                messages=[{"role": "user", "content": "Onde gasto mais?"}]
            )
        )
    )
    assert payload["reply"].startswith("Seu maior gasto")
    assert captured["messages"][0]["role"] == "system"
    assert "Alimentação" in captured["messages"][0]["content"]
    assert captured["messages"][-1]["content"] == "Onde gasto mais?"


def test_chat_falls_back_when_model_returns_none(fake_backend, monkeypatch):
    monkeypatch.setattr(server.groq_client, "request_chat", lambda **_k: None)
    payload = run(
        server.finance_assistant_chat(
            server.AssistantChatRequest(
                messages=[{"role": "user", "content": "oi"}]
            )
        )
    )
    assert payload["reply"] == server.ASSISTANT_UNAVAILABLE_REPLY


def test_chat_falls_back_when_groq_not_configured(fake_backend, monkeypatch):
    monkeypatch.setattr(server.groq_client, "is_groq_configured", lambda: False)
    payload = run(
        server.finance_assistant_chat(
            server.AssistantChatRequest(
                messages=[{"role": "user", "content": "oi"}]
            )
        )
    )
    assert payload["reply"] == server.ASSISTANT_UNAVAILABLE_REPLY


def test_chat_rejects_when_last_message_not_user(fake_backend, monkeypatch):
    monkeypatch.setattr(server.groq_client, "request_chat", lambda **_k: "x")
    with pytest.raises(HTTPException) as exc:
        run(
            server.finance_assistant_chat(
                server.AssistantChatRequest(
                    messages=[
                        {"role": "user", "content": "oi"},
                        {"role": "assistant", "content": "olá"},
                    ]
                )
            )
        )
    assert exc.value.status_code == 422


def test_chat_rejects_long_history(fake_backend, monkeypatch):
    monkeypatch.setattr(server.groq_client, "request_chat", lambda **_k: "x")
    messages = [
        {"role": "user", "content": f"m{i}"}
        for i in range(server.ASSISTANT_HISTORY_MAX_MESSAGES + 1)
    ]
    with pytest.raises(HTTPException) as exc:
        run(
            server.finance_assistant_chat(
                server.AssistantChatRequest(messages=messages)
            )
        )
    assert exc.value.status_code == 422


def test_chat_rate_limited_on_immediate_second_call(fake_backend, monkeypatch):
    monkeypatch.setattr(server.groq_client, "request_chat", lambda **_k: "ok")
    request = server.AssistantChatRequest(
        messages=[{"role": "user", "content": "oi"}]
    )
    run(server.finance_assistant_chat(request))
    with pytest.raises(HTTPException) as exc:
        run(server.finance_assistant_chat(request))
    assert exc.value.status_code == 429


def test_request_chat_without_key_returns_none(monkeypatch):
    monkeypatch.setattr(groq_client, "get_groq_api_key", lambda: "")
    assert (
        groq_client.request_chat(messages=[{"role": "user", "content": "oi"}]) is None
    )


def test_request_chat_success(monkeypatch):
    monkeypatch.setattr(groq_client, "get_groq_api_key", lambda: "key")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "resposta"}}]}

    import requests

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse())
    assert (
        groq_client.request_chat(messages=[{"role": "user", "content": "oi"}])
        == "resposta"
    )


def test_request_chat_retries_on_429(monkeypatch):
    monkeypatch.setattr(groq_client, "get_groq_api_key", lambda: "key")
    monkeypatch.setattr(groq_client, "_sleep", lambda _s: None)
    calls = {"n": 0}

    class Resp429:
        status_code = 429
        headers = {}

        def raise_for_status(self):
            raise AssertionError("não deveria chegar aqui")

        def json(self):
            return {}

    class RespOk:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*_a, **_k):
        calls["n"] += 1
        return Resp429() if calls["n"] == 1 else RespOk()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    assert (
        groq_client.request_chat(messages=[{"role": "user", "content": "oi"}]) == "ok"
    )
    assert calls["n"] == 2
