"""Testes do motor de extração de faturas (Groq + conciliação genérica).

Nenhum teste chama a API: as respostas do Groq são mockadas trocando o módulo
`requests` em `sys.modules`, no mesmo padrão dos fakes já usados na suíte.
"""

import json
import os
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from backend import groq_client, invoice_ai  # noqa: E402
from tests.fixtures import invoices  # noqa: E402


class FakeResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def chat_completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class FakeRequests:
    """Substitui o módulo `requests`, guardando os payloads enviados."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


@pytest.fixture
def groq_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_KEY", raising=False)
    monkeypatch.delenv("GROQ_INVOICE_MODEL", raising=False)
    monkeypatch.delenv("GROQ_INVOICE_RESPONSE_FORMAT", raising=False)


def install_requests(monkeypatch, responses):
    fake = FakeRequests(responses)
    monkeypatch.setitem(sys.modules, "requests", fake)
    return fake


# ---------------------------------------------------------------------------
# Cliente Groq
# ---------------------------------------------------------------------------


def test_groq_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_KEY", raising=False)
    fake = install_requests(monkeypatch, [FakeResponse(chat_completion("{}"))])

    assert invoice_ai.extract_invoice_document("fatura") is None
    assert fake.calls == []


def test_groq_client_accepts_groq_key_env_var(monkeypatch):
    """O secret do GitHub Actions se chama GROQ_KEY."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_KEY", "secret-do-actions")
    fake = install_requests(
        monkeypatch,
        [FakeResponse(chat_completion(json.dumps(invoices.NEON.ai_document)))],
    )

    assert invoice_ai.extract_invoice_document(invoices.NEON.raw_text) is not None
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer secret-do-actions"


def test_groq_api_key_prefers_the_canonical_env_var(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "canonica")
    monkeypatch.setenv("GROQ_KEY", "do-actions")

    assert groq_client.get_groq_api_key() == "canonica"


def test_groq_client_sends_json_schema_and_parses_document(groq_env, monkeypatch):
    fake = install_requests(
        monkeypatch,
        [FakeResponse(chat_completion(json.dumps(invoices.NEON.ai_document)))],
    )

    document = invoice_ai.extract_invoice_document(invoices.NEON.raw_text)

    assert document is not None
    assert document["issuer"] == "Neon"
    assert len(document["items"]) == 4

    payload = fake.calls[0]["json"]
    assert fake.calls[0]["url"] == ("https://api.groq.com/openai/v1/chat/completions")
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert payload["model"] == groq_client.DEFAULT_GROQ_INVOICE_MODEL
    assert payload["response_format"]["type"] == "json_schema"
    assert (
        payload["response_format"]["json_schema"]["schema"]
        == invoice_ai.INVOICE_DOCUMENT_SCHEMA
    )
    # O texto da fatura vai como texto puro: a Groq não aceita PDF nativo.
    assert invoices.NEON.raw_text[:40] in payload["messages"][1]["content"]
    assert all(isinstance(message["content"], str) for message in payload["messages"])
    assert "base64" not in json.dumps(payload)


def test_groq_client_honours_model_env(groq_env, monkeypatch):
    monkeypatch.setenv("GROQ_INVOICE_MODEL", "moonshotai/kimi-k2-instruct-0905")
    fake = install_requests(
        monkeypatch,
        [FakeResponse(chat_completion(json.dumps(invoices.NEON.ai_document)))],
    )

    invoice_ai.extract_invoice_document(invoices.NEON.raw_text)

    assert fake.calls[0]["json"]["model"] == "moonshotai/kimi-k2-instruct-0905"


def test_groq_client_falls_back_to_json_mode_when_schema_is_rejected(
    groq_env, monkeypatch
):
    fake = install_requests(
        monkeypatch,
        [
            FakeResponse(
                {"error": {"message": "invalid json schema"}}, status_code=400
            ),
            FakeResponse(chat_completion(json.dumps(invoices.NEON.ai_document))),
        ],
    )

    document = invoice_ai.extract_invoice_document(invoices.NEON.raw_text)

    assert document is not None
    assert len(fake.calls) == 2
    assert fake.calls[0]["json"]["response_format"]["type"] == "json_schema"
    assert fake.calls[1]["json"]["response_format"] == {"type": "json_object"}


def test_groq_client_can_be_pinned_to_json_mode(groq_env, monkeypatch):
    monkeypatch.setenv("GROQ_INVOICE_RESPONSE_FORMAT", "json_object")
    fake = install_requests(
        monkeypatch,
        [FakeResponse(chat_completion(json.dumps(invoices.NEON.ai_document)))],
    )

    invoice_ai.extract_invoice_document(invoices.NEON.raw_text)

    assert len(fake.calls) == 1
    assert fake.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_groq_client_reads_json_wrapped_in_code_fence(groq_env, monkeypatch):
    fenced = (
        "Segue o resultado:\n```json\n"
        + json.dumps(invoices.NEON.ai_document)
        + "\n```"
    )
    install_requests(monkeypatch, [FakeResponse(chat_completion(fenced))])

    document = invoice_ai.extract_invoice_document(invoices.NEON.raw_text)

    assert document is not None
    assert document["issuer"] == "Neon"


def test_groq_client_gives_up_when_response_is_not_json(groq_env, monkeypatch):
    fake = install_requests(
        monkeypatch,
        [FakeResponse(chat_completion("não consegui ler essa fatura"))],
    )

    assert invoice_ai.extract_invoice_document(invoices.NEON.raw_text) is None
    # Uma tentativa em json_schema e outra em JSON mode antes de desistir.
    assert len(fake.calls) == 2


def test_groq_client_survives_network_error(groq_env, monkeypatch):
    class ExplodingRequests:
        @staticmethod
        def post(*_args, **_kwargs):
            raise ConnectionError("timeout")

    monkeypatch.setitem(sys.modules, "requests", ExplodingRequests)

    assert invoice_ai.extract_invoice_document(invoices.NEON.raw_text) is None


# ---------------------------------------------------------------------------
# Contrato de saída
# ---------------------------------------------------------------------------


def test_prompt_describes_the_contract_and_the_traps():
    prompt = invoice_ai.build_invoice_user_prompt("texto da fatura")

    for field in (
        "issuer",
        "doc_type",
        "totals",
        "label_original",
        "reconciliation_anchor",
        "original_currency",
        "confidence",
        "summary",
    ):
        assert field in prompt
    # JSON mode exige a palavra "JSON" na mensagem.
    assert "JSON" in prompt
    for item_type in invoice_ai.INVOICE_ITEM_TYPES:
        assert item_type in prompt


def test_prompt_truncates_long_documents(monkeypatch):
    monkeypatch.setenv("GROQ_INVOICE_MAX_CHARS", "50")

    prompt = invoice_ai.build_invoice_user_prompt("x" * 5000)

    assert "x" * 50 in prompt
    assert "x" * 51 not in prompt


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("R$ 1.584,50", 1584.50),
        ("1584.50", 1584.50),
        (68.49, 68.49),
        ("−45,00", -45.00),  # menos Unicode (U+2212)
        ("-45,00", -45.00),
        ("R$ −1.200,00", -1200.00),
        ("(45,00)", -45.00),
        ("", None),
        ("R$", None),
    ],
)
def test_parse_amount_handles_brl_and_unicode_minus(raw_value, expected):
    assert invoice_ai.parse_amount(raw_value) == expected


def test_normalize_document_rejects_payload_without_items():
    assert invoice_ai.normalize_invoice_document({"items": []}) is None
    assert invoice_ai.normalize_invoice_document("nope") is None


def test_normalize_document_drops_broken_items_and_keeps_duplicates():
    document = invoice_ai.normalize_invoice_document(
        {
            "issuer": "Neon",
            "totals": [{"label_original": "Total de compras", "value": "R$ 30,00"}],
            "reconciliation_anchor": {
                "label_original": "Total de compras",
                "reason": "total das compras",
            },
            "items": [
                {"description": "PADARIA", "amount": "R$ 10,00", "type": "compra"},
                {"description": "PADARIA", "amount": "R$ 10,00", "type": "compra"},
                {"description": "PADARIA", "amount": "R$ 10,00", "type": "compra"},
                {"description": "", "amount": 5.0, "type": "compra"},
                {"description": "ZERADO", "amount": 0, "type": "compra"},
                {"description": "SEM VALOR", "amount": "abc", "type": "compra"},
                "isso não é um item",
            ],
            "confidence": 3,
        }
    )

    # Lançamentos idênticos são lançamentos distintos: nada de deduplicação.
    assert [item["description"] for item in document["items"]] == [
        "PADARIA",
        "PADARIA",
        "PADARIA",
    ]
    # A âncora sem valor é preenchida pelo total de mesmo rótulo.
    assert document["reconciliation_anchor"]["value"] == 30.00
    assert document["confidence"] == 1.0


def test_normalize_document_normalizes_types_and_signs():
    document = invoice_ai.normalize_invoice_document(
        {
            "items": [
                {"description": "PAGAMENTO", "amount": 100.0, "type": "pagamento"},
                {"description": "ESTORNO", "amount": 45.0, "type": "estorno"},
                {"description": "COMPRA NEGATIVA", "amount": -20.0, "type": "compra"},
                {"description": "DESCONHECIDO", "amount": 10.0, "type": "misterio"},
            ],
            "reconciliation_anchor": {"label_original": "Total", "value": 10.0},
        }
    )

    by_description = {item["description"]: item for item in document["items"]}
    assert by_description["PAGAMENTO"]["amount"] == -100.0
    assert by_description["ESTORNO"]["amount"] == -45.0
    # Uma "compra" negativa é, na prática, um estorno.
    assert by_description["COMPRA NEGATIVA"]["type"] == "estorno"
    assert by_description["DESCONHECIDO"]["type"] == "compra"


def test_normalize_document_ignores_anchor_without_usable_value():
    document = invoice_ai.normalize_invoice_document(
        {
            "items": [{"description": "PADARIA", "amount": 10.0, "type": "compra"}],
            "totals": [{"label_original": "Total a pagar", "value": 10.0}],
            "reconciliation_anchor": {"label_original": "Total de compras"},
        }
    )

    assert document["reconciliation_anchor"] is None
    assert invoice_ai.reconcile_invoice_document(document)["status"] == "no_anchor"


# ---------------------------------------------------------------------------
# Conciliação genérica
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture", invoices.ALL_FIXTURES, ids=lambda fixture: fixture.name
)
def test_fixture_documents_are_grounded_in_their_raw_text(fixture):
    """Todo valor esperado precisa existir no texto de entrada da fixture."""
    for _description, amount in fixture.expected_purchases:
        assert invoices.format_brl(amount) in fixture.raw_text
    assert invoices.format_brl(fixture.anchor_total) in fixture.raw_text
    for item in fixture.ai_document["items"]:
        assert invoices.format_brl(item["amount"]) in fixture.raw_text


@pytest.mark.parametrize(
    "fixture", invoices.ALL_FIXTURES, ids=lambda fixture: fixture.name
)
def test_reconciliation_over_fixtures(fixture):
    document = invoice_ai.normalize_invoice_document(fixture.ai_document)
    assert document is not None

    result = invoice_ai.reconcile_invoice_document(document)

    assert result["status"] == fixture.expected_status
    assert result["anchor_total"] == fixture.anchor_total
    assert result["anchor_label"] == fixture.anchor_label
    assert [
        (item["description"], item["amount"]) for item in result["purchase_items"]
    ] == list(fixture.expected_purchases)

    selected_amounts = {item["amount"] for item in result["purchase_items"]}
    for forbidden in fixture.forbidden_amounts:
        assert forbidden not in selected_amounts


def test_nubank_fixture_covers_the_multiline_block_traps():
    document = invoice_ai.normalize_invoice_document(invoices.NUBANK.ai_document)
    by_description = {item["description"]: item for item in document["items"]}

    # Parcelamento: vale a última linha do bloco (a parcela), não o total.
    assert by_description["MERCADO SAO JOSE - Parcela 2 de 6"]["amount"] == 33.53
    assert by_description["MERCADO SAO JOSE - Parcela 2 de 6"]["type"] == "parcela"
    # Explicação do bloco não vira item nem substitui o valor lançado.
    assert by_description["POSTO EXEMPLO"]["amount"] == 177.98
    assert not any(
        item["amount"] in {156.90, 1.55, 19.53} for item in document["items"]
    )
    # Arredondamento de um centavo: vale o valor lançado, não a explicação.
    assert by_description["ASSINATURA STREAM"]["amount"] == 172.14
    # Estorno com menos Unicode continua negativo e fora das compras.
    assert by_description["ESTORNO LOJA DEZ"]["amount"] == -45.00
    assert by_description["Servico Online *Xy12ab34"]["original_currency"] == "USD"


def test_nubank_anchor_is_the_purchases_total_not_the_amount_due():
    document = invoice_ai.normalize_invoice_document(invoices.NUBANK.ai_document)

    labels = [total["label_original"] for total in document["totals"]]
    assert labels.count("Total a pagar") == 1
    assert document["reconciliation_anchor"]["label_original"] == (
        "Total de compras de todos os cartões"
    )
    assert document["reconciliation_anchor"]["value"] == 452.14
    # O total a pagar existe no documento, mas não é a âncora de compras.
    assert any(total["value"] == 407.14 for total in document["totals"])


def test_reconciliation_reports_mismatch_when_nothing_explains_the_gap():
    document = invoice_ai.normalize_invoice_document(
        {
            "items": [
                {"description": "PADARIA", "amount": 10.0, "type": "compra"},
                {"description": "MERCADO", "amount": 20.0, "type": "compra"},
            ],
            "reconciliation_anchor": {"label_original": "Total", "value": 100.0},
        }
    )

    result = invoice_ai.reconcile_invoice_document(document)

    assert result["status"] == "mismatch"
    assert result["purchase_total"] == 30.0
    assert result["gap"] == 70.0


def test_reconciliation_works_in_integer_cents():
    """Valores que somam com erro em ponto flutuante ainda conciliam."""
    document = invoice_ai.normalize_invoice_document(
        {
            "items": [
                {"description": "A", "amount": 0.1, "type": "compra"},
                {"description": "B", "amount": 0.2, "type": "compra"},
            ],
            "reconciliation_anchor": {"label_original": "Total", "value": 0.3},
        }
    )

    assert 0.1 + 0.2 != 0.3
    assert invoice_ai.reconcile_invoice_document(document)["status"] == "ok"


def test_reconciliation_ignores_credits_when_summing_purchases():
    document = invoice_ai.normalize_invoice_document(
        {
            "items": [
                {"description": "COMPRA", "amount": 100.0, "type": "compra"},
                {"description": "PAGAMENTO", "amount": 80.0, "type": "pagamento"},
                {"description": "ESTORNO", "amount": 20.0, "type": "estorno"},
            ],
            "reconciliation_anchor": {
                "label_original": "Total compras",
                "value": 100.0,
            },
        }
    )

    result = invoice_ai.reconcile_invoice_document(document)

    assert result["status"] == "ok"
    assert [item["description"] for item in result["purchase_items"]] == ["COMPRA"]
