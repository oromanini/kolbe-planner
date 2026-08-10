import asyncio
import os
import re
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from backend import invoice_ai, server  # noqa: E402
from tests.fixtures import invoices  # noqa: E402


class FakeCursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, _limit):
        return [dict(item) for item in self.items]


class FakeResult:
    def __init__(self, deleted_count=0, matched_count=0):
        self.deleted_count = deleted_count
        self.matched_count = matched_count


class FakeCollection:
    def __init__(self):
        self.docs = []

    def _matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict) and "$ne" in value:
                if doc.get(key) == value["$ne"]:
                    return False
                continue
            if isinstance(value, dict) and "$regex" in value:
                flags = re.IGNORECASE if "i" in value.get("$options", "") else 0
                if not re.match(value["$regex"], str(doc.get(key, "")), flags):
                    return False
                continue
            if doc.get(key) != value:
                return False
        return True

    def _project(self, doc, projection):
        if not projection:
            return dict(doc)

        fields = {key: value for key, value in projection.items() if key != "_id"}
        if not fields:
            return dict(doc)

        if all(not value for value in fields.values()):
            # Projeção por exclusão: {"_id": 0, "raw_text": 0}.
            return {
                key: value
                for key, value in doc.items()
                if key != "_id" and key not in fields
            }

        return {key: doc[key] for key, value in fields.items() if value and key in doc}

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if self._matches(doc, query):
                return self._project(doc, projection)
        return None

    def find(self, query, projection=None):
        items = [
            self._project(doc, projection)
            for doc in self.docs
            if self._matches(doc, query)
        ]
        return FakeCursor(items)

    async def insert_one(self, doc):
        doc.setdefault("_id", "fake_object_id")
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                return FakeResult(matched_count=1)
        return FakeResult(matched_count=0)

    async def update_many(self, query, update):
        matched = 0
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update.get("$set", {}))
                matched += 1
        return FakeResult(matched_count=matched)

    async def delete_one(self, query):
        for idx, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs.pop(idx)
                return FakeResult(deleted_count=1)
        return FakeResult(deleted_count=0)

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]
        return FakeResult(deleted_count=before - len(self.docs))

    async def count_documents(self, query):
        return sum(1 for doc in self.docs if self._matches(doc, query))

    async def estimated_document_count(self):
        return len(self.docs)


class FakeDB:
    def __init__(self):
        self.financial_methods = FakeCollection()
        self.financial_categories = FakeCollection()
        self.expenses = FakeCollection()
        self.incomes = FakeCollection()
        self.savings = FakeCollection()
        self.invoice_reader_jobs = FakeCollection()
        self.invoice_reader_batches = FakeCollection()

    async def command(self, name):
        if name != "ping":
            raise ValueError("unsupported command")
        return {"ok": 1}


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    fake_db = FakeDB()

    async def fake_user(*_args, **_kwargs):
        return SimpleNamespace(user_id="user_1")

    monkeypatch.setattr(server, "db", fake_db)
    monkeypatch.setattr(server, "get_current_user", fake_user)
    return fake_db


def run(coro):
    return asyncio.run(coro)


def test_methods_get_and_create(fake_backend):
    methods = run(server.get_methods())
    assert [method["name"] for method in methods] == server.DEFAULT_FINANCIAL_METHODS

    with pytest.raises(HTTPException) as duplicate:
        run(server.create_method(server.MethodCreate(name="PIX")))
    assert duplicate.value.status_code == 409

    created = run(server.create_method(server.MethodCreate(name="Cartão corporativo")))
    assert created["name"] == "Cartão corporativo"
    assert "_id" not in created
    assert (
        len(fake_backend.financial_methods.docs)
        == len(server.DEFAULT_FINANCIAL_METHODS) + 1
    )


def test_categories_get_and_create_is_idempotent(fake_backend):
    created = run(
        server.create_category(server.CategoryCreate(name="Carro", icon="car"))
    )
    assert created["name"] == "Carro"
    assert "_id" not in created

    duplicated = run(
        server.create_category(server.CategoryCreate(name="Carro", icon="car"))
    )
    assert duplicated["name"] == "Carro"
    assert duplicated["category_id"] == created["category_id"]

    listing = run(server.get_categories())
    assert len(listing) == 1


def test_categories_normalize_whitespace_and_reuse_case_insensitive_duplicates(
    fake_backend,
):
    created = run(
        server.create_category(server.CategoryCreate(name="  Mercado  ", icon="cart"))
    )
    assert created["name"] == "Mercado"

    duplicated = run(
        server.create_category(server.CategoryCreate(name="mercado", icon="cart"))
    )
    assert duplicated["name"] == "Mercado"
    assert duplicated["category_id"] == created["category_id"]


def test_categories_create_different_names_do_not_collide(fake_backend):
    first = run(
        server.create_category(server.CategoryCreate(name="Categoria A", icon="a"))
    )
    second = run(
        server.create_category(
            server.CategoryCreate(name="Categoria 12345123123123", icon="b")
        )
    )

    assert first["category_id"] != second["category_id"]
    listing = run(server.get_categories())
    assert {item["name"] for item in listing} == {
        "Categoria A",
        "Categoria 12345123123123",
    }


def test_categories_update_delete_and_force_delete_with_linked_expenses(fake_backend):
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_1",
            "user_id": "user_1",
            "name": "Mercado",
            "icon": "cart",
            "type": "expense",
        }
    )
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_2",
            "user_id": "user_1",
            "name": "Lazer",
            "icon": "smile",
            "type": "expense",
        }
    )
    fake_backend.expenses.docs.append(
        {
            "expense_id": "exp_1",
            "user_id": "user_1",
            "category": "Mercado",
            "month": "2026-03",
            "amount": 10,
        }
    )

    with pytest.raises(HTTPException) as conflict:
        run(
            server.update_category(
                "cat_1", server.CategoryUpdate(name="Lazer", icon="cart")
            )
        )
    assert conflict.value.status_code == 409

    updated = run(
        server.update_category(
            "cat_1", server.CategoryUpdate(name="Feira", icon="cart")
        )
    )
    assert updated["name"] == "Feira"
    assert fake_backend.expenses.docs[0]["category"] == "Feira"

    with pytest.raises(HTTPException) as blocked_delete:
        run(server.delete_category("cat_1"))
    assert blocked_delete.value.status_code == 409

    deleted = run(server.delete_category("cat_1", force=True))
    assert deleted["deleted_items"] == 1


def test_expenses_get_create_and_delete(fake_backend):
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_1",
            "user_id": "user_1",
            "name": "Transporte",
            "icon": "car",
            "type": "expense",
        }
    )

    with pytest.raises(HTTPException) as invalid:
        run(
            server.create_expense(
                server.ExpenseCreate(
                    name="Ônibus",
                    amount=7.5,
                    method_id="method_1",
                    category="Inexistente",
                    month="2026-03",
                )
            )
        )
    assert invalid.value.status_code == 400

    created = run(
        server.create_expense(
            server.ExpenseCreate(
                name="Ônibus",
                amount=7.5,
                method_id="method_1",
                category="Transporte",
                month="2026-03",
            )
        )
    )
    assert created["category"] == "Transporte"
    assert "_id" not in created

    monthly = run(server.get_expenses("2026-03"))
    assert len(monthly) == 1

    deleted = run(server.delete_expense(created["expense_id"]))
    assert deleted["message"] == "Deleted"

    with pytest.raises(HTTPException) as missing:
        run(server.delete_expense("exp_missing"))
    assert missing.value.status_code == 404


def test_expenses_accept_category_id_and_case_insensitive_name(fake_backend):
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_1",
            "user_id": "user_1",
            "name": "Transporte",
            "name_key": "transporte",
            "type": "expense",
        }
    )

    by_id = run(
        server.create_expense(
            server.ExpenseCreate(
                name="Metrô",
                amount=9,
                method_id="method_1",
                category="cat_1",
                month="2026-03",
            )
        )
    )
    assert by_id["category"] == "Transporte"

    by_case_insensitive_name = run(
        server.create_expense(
            server.ExpenseCreate(
                name="Táxi",
                amount=20,
                method_id="method_1",
                category=" transporte ",
                month="2026-03",
            )
        )
    )
    assert by_case_insensitive_name["category"] == "Transporte"


def test_incomes_get_create_and_delete(fake_backend):
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_inc_1",
            "user_id": "user_1",
            "name": "Salário",
            "name_key": "salário",
            "type": "income",
        }
    )

    created = run(
        server.create_income(
            server.IncomeCreate(
                name="Salário CLT",
                amount=3200,
                category="Salário",
                month="2026-03",
            )
        )
    )
    assert created["name"] == "Salário CLT"
    assert "_id" not in created

    updated = run(
        server.update_income(
            created["income_id"],
            server.IncomeUpdate(
                name="Salário + bônus",
                amount=3500,
                category="cat_inc_1",
                month="2026-03",
            ),
        )
    )
    assert updated["name"] == "Salário + bônus"
    assert updated["amount"] == 3500
    assert updated["category"] == "Salário"

    monthly = run(server.get_incomes("2026-03"))
    assert len(monthly) == 1

    deleted = run(server.delete_income(created["income_id"]))
    assert deleted["message"] == "Deleted"

    with pytest.raises(HTTPException) as missing:
        run(server.delete_income("inc_missing"))
    assert missing.value.status_code == 404


def test_income_update_rejects_invalid_category(fake_backend):
    fake_backend.incomes.docs.append(
        {
            "income_id": "inc_1",
            "user_id": "user_1",
            "name": "Freela",
            "amount": 1200,
            "category": "Projetos",
            "month": "2026-03",
        }
    )

    with pytest.raises(HTTPException) as invalid_category:
        run(
            server.update_income(
                "inc_1",
                server.IncomeUpdate(
                    name="Freela",
                    amount=1200,
                    category="Categoria inexistente",
                    month="2026-03",
                ),
            )
        )

    assert invalid_category.value.status_code == 400


def test_savings_get_create_and_update(fake_backend):
    assert run(server.get_savings()) == []

    created = run(
        server.create_savings(
            server.SavingsCreate(name="Reserva", type="reserva", amount=100)
        )
    )
    assert created["amount"] == 100
    assert "_id" not in created

    updated = run(server.update_savings(created["savings_id"], amount=150))
    assert updated["amount"] == 150

    with pytest.raises(HTTPException) as missing:
        run(server.update_savings("sav_missing", amount=150))
    assert missing.value.status_code == 404


def test_summary_calculates_totals_and_breakdown(fake_backend):
    fake_backend.incomes.docs.extend(
        [
            {
                "income_id": "inc_1",
                "user_id": "user_1",
                "name": "Salário",
                "amount": 3000,
                "month": "2026-03",
            },
            {
                "income_id": "inc_2",
                "user_id": "user_1",
                "name": "Freela",
                "amount": 1000,
                "month": "2026-03",
            },
        ]
    )
    fake_backend.expenses.docs.extend(
        [
            {
                "expense_id": "exp_1",
                "user_id": "user_1",
                "name": "Mercado",
                "amount": 500,
                "category": "Casa",
                "month": "2026-03",
            },
            {
                "expense_id": "exp_2",
                "user_id": "user_1",
                "name": "Gasolina",
                "amount": 300,
                "category": "Carro",
                "month": "2026-03",
            },
            {
                "expense_id": "exp_3",
                "user_id": "user_1",
                "name": "Água",
                "amount": 200,
                "category": "Casa",
                "month": "2026-03",
            },
        ]
    )

    summary = run(server.get_summary("2026-03"))

    assert summary["total_income"] == 4000
    assert summary["total_expenses"] == 1000
    assert summary["balance"] == 3000
    assert summary["category_breakdown"] == {"Casa": 700, "Carro": 300}


def test_health_check_reports_ok(fake_backend):
    result = run(server.health_check())
    assert result["status"] == "ok"
    assert result["checks"]["mongo"] == "ok"
    assert result["checks"]["collections"] == "ok"


def test_detect_card_suffix_reads_masked_card_number():
    raw = """NUBANK
Cartão final 7071
"""

    assert server.detect_card_suffix(raw) == "7071"


def test_select_items_matching_expected_total_finds_subset_when_ai_overextracts():
    items = [
        {"description": "AZUL LINHAS", "amount": 530.33},
        {"description": "AZUL LINHAS", "amount": 126.44},
        {"description": "JIM.COM", "amount": 57.98},
        {"description": "AIRBNB", "amount": 33.08},
        {"description": "AZUL LINHAS", "amount": 128.98},
        {"description": "DEMais FATURAS", "amount": 876.81},
    ]

    selected = server.select_items_matching_expected_total(items, 876.81)

    assert selected is not None
    assert round(sum(item["amount"] for item in selected), 2) == 876.81
    assert len(selected) == 5


def test_invoice_reader_list_purges_only_resolved_documents(fake_backend):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=server.INVOICE_JOB_RETENTION_DAYS + 1)).isoformat()
    fake_backend.invoice_reader_jobs.docs.extend(
        [
            {
                "job_id": "invjob_waiting",
                "user_id": "user_1",
                "status": server.INVOICE_STATUS_AWAITING_REVIEW,
                "created_at": old,
                "finished_at": old,
            },
            {
                "job_id": "invjob_recent",
                "user_id": "user_1",
                "status": server.INVOICE_STATUS_APPROVED,
                "created_at": (now - timedelta(days=1)).isoformat(),
                "finished_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "job_id": "invjob_old_approved",
                "user_id": "user_1",
                "status": server.INVOICE_STATUS_APPROVED,
                "created_at": old,
                "finished_at": old,
            },
        ]
    )

    documents = run(server.get_invoice_reader_jobs(limit=10))

    # O documento aguardando revisão sobrevive por mais velho que seja: apagá-lo
    # tiraria da frente do usuário justamente o que ele precisa revisar.
    assert [item["job_id"] for item in documents] == [
        "invjob_recent",
        "invjob_waiting",
    ]
    assert all(
        doc["job_id"] != "invjob_old_approved"
        for doc in fake_backend.invoice_reader_jobs.docs
    )


def test_invoice_reader_list_hides_the_raw_pdf_text(fake_backend):
    fake_backend.invoice_reader_jobs.docs.append(
        {
            "job_id": "invjob_1",
            "user_id": "user_1",
            "status": server.INVOICE_STATUS_AWAITING_REVIEW,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_text": "texto extraído do PDF",
        }
    )

    documents = run(server.get_invoice_reader_jobs(limit=10))

    assert "raw_text" not in documents[0]


# ---------------------------------------------------------------------------
# Fluxo de revisão: analisar, aprovar, contestar, rejeitar
# ---------------------------------------------------------------------------


class FakeUpload:
    def __init__(self, filename, content=b"%PDF-1.4", content_type="application/pdf"):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


def _seed_document(fake_backend, job_id, user_id="user_1", **overrides):
    record = server.build_invoice_document_record(
        user_id, "invlote_1", "2026-08", overrides.pop("filename", "documento.pdf")
    )
    record["job_id"] = job_id
    record.update(overrides)
    fake_backend.invoice_reader_jobs.docs.append(record)
    return record


def _get_document(fake_backend, job_id):
    return next(
        doc
        for doc in fake_backend.invoice_reader_jobs.docs
        if doc.get("job_id") == job_id
    )


def _mock_ai(monkeypatch, fixture, document=None):
    """Mocka a IA. Nenhum teste toca a API: só o contrato está sob teste."""
    calls = []

    def fake_extract(raw_text, **kwargs):
        calls.append({"raw_text": raw_text, "feedback": kwargs.get("feedback") or []})
        if document is not None:
            return document
        return invoice_ai.normalize_invoice_document(fixture.ai_document)

    monkeypatch.setattr(
        server, "extract_pdf_text", lambda _pdf: fixture.raw_text if fixture else ""
    )
    monkeypatch.setattr(server, "extract_invoice_document", fake_extract)
    return calls


def _analyze(
    fake_backend, monkeypatch, job_id, fixture, document=None, user_id="user_1"
):
    _seed_document(fake_backend, job_id, user_id=user_id)
    _mock_ai(monkeypatch, fixture, document)
    run(server.analyze_invoice_document(job_id, user_id, b"%PDF-1.4"))
    return _get_document(fake_backend, job_id)


def _capture_background_tasks(monkeypatch):
    """Segura as tasks de análise para o teste rodá-las quando quiser."""
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return SimpleNamespace(cancel=lambda: None)

    monkeypatch.setattr(server.asyncio, "create_task", fake_create_task)
    return scheduled


def _discard(scheduled):
    """Descarta análises agendadas que o teste não vai rodar."""
    while scheduled:
        scheduled.pop().close()


def test_analysis_holds_the_document_as_a_draft_without_writing_expenses(
    fake_backend, monkeypatch
):
    document = _analyze(fake_backend, monkeypatch, "doc_nubank", invoices.NUBANK)

    assert document["status"] == server.INVOICE_STATUS_AWAITING_REVIEW
    assert document["regime"] == server.REGIME_CARD
    assert document["reconciliation_status"] == "ok"
    assert document["reconciled"] is True
    assert document["ai_summary"] == invoices.NUBANK.ai_document["summary"]
    assert document["expected_total"] == 452.14
    assert [
        (item["name"], item["amount"]) for item in document["expense_plan"]
    ] == list(invoices.NUBANK.expected_purchases)
    # O rascunho fica no documento, não em expenses.
    assert fake_backend.expenses.docs == []
    assert fake_backend.financial_categories.docs == []


def test_approving_a_card_invoice_creates_one_expense_per_purchase(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_itau", invoices.ITAU)

    approved = run(server.approve_invoice_reader_document("doc_itau"))

    assert approved["status"] == server.INVOICE_STATUS_APPROVED
    assert len(approved["created_expense_ids"]) == 3
    created = [(doc["name"], doc["amount"]) for doc in fake_backend.expenses.docs]
    assert created == list(invoices.ITAU.expected_purchases)
    assert all(doc["month"] == "2026-08" for doc in fake_backend.expenses.docs)
    # Cartão mantém o comportamento anterior: categoria por emissor e sufixo.
    assert [doc["name"] for doc in fake_backend.financial_categories.docs] == [
        "Itaú final 4321"
    ]
    assert all(
        doc["category"] == "Itaú final 4321" and doc["subcategory"] == "fatura-cartao"
        for doc in fake_backend.expenses.docs
    )


def test_approving_a_card_invoice_uses_the_credit_card_method(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_itau", invoices.ITAU)

    run(server.approve_invoice_reader_document("doc_itau"))

    method = next(
        doc
        for doc in fake_backend.financial_methods.docs
        if doc["name"] == "crédito a vista"
    )
    assert all(
        doc["method_id"] == method["method_id"] for doc in fake_backend.expenses.docs
    )


def test_approving_a_light_bill_creates_a_single_expense_with_the_ai_category(
    fake_backend, monkeypatch
):
    document = _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)

    assert document["regime"] == server.REGIME_SINGLE_CHARGE
    assert document["doc_type"] == "conta_luz"
    assert document["amount_total"] == 187.40

    run(server.approve_invoice_reader_document("doc_luz"))

    assert len(fake_backend.expenses.docs) == 1
    expense = fake_backend.expenses.docs[0]
    assert expense["amount"] == 187.40
    assert expense["category"] == "Luz"
    assert expense["subcategory"] == "conta-luz"
    assert expense["month"] == "2026-08"
    assert expense["name"] == "Conta de luz Energia Aurora - 2026-07"
    assert [doc["name"] for doc in fake_backend.financial_categories.docs] == ["Luz"]


def test_approving_a_bill_never_uses_the_credit_card_naming(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)

    run(server.approve_invoice_reader_document("doc_luz"))

    expense = fake_backend.expenses.docs[0]
    assert "final" not in expense["category"]
    assert expense["subcategory"] != "fatura-cartao"
    method = next(
        doc
        for doc in fake_backend.financial_methods.docs
        if doc["method_id"] == expense["method_id"]
    )
    assert method["name"] == "boleto"


def test_approving_a_bill_without_itemization_creates_one_expense(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_cond", invoices.CONDOMINIO)

    run(server.approve_invoice_reader_document("doc_cond"))

    assert len(fake_backend.expenses.docs) == 1
    expense = fake_backend.expenses.docs[0]
    assert expense["amount"] == 640.00
    assert expense["category"] == "Condomínio"
    assert expense["subcategory"] == "condominio"


def test_bill_falls_back_to_a_category_derived_from_the_doc_type(
    fake_backend, monkeypatch
):
    payload = {**invoices.CONTA_LUZ.ai_document}
    payload.pop("suggested_category")
    document = invoice_ai.normalize_invoice_document(payload)

    _analyze(
        fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ, document=document
    )
    run(server.approve_invoice_reader_document("doc_luz"))

    assert fake_backend.expenses.docs[0]["category"] == "Luz"


def test_approving_twice_does_not_duplicate_expenses(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)

    first = run(server.approve_invoice_reader_document("doc_luz"))
    second = run(server.approve_invoice_reader_document("doc_luz"))

    assert len(fake_backend.expenses.docs) == 1
    assert first["created_expense_ids"] == second["created_expense_ids"]
    assert second["status"] == server.INVOICE_STATUS_APPROVED


def test_approving_a_card_invoice_twice_does_not_duplicate_expenses(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_itau", invoices.ITAU)

    run(server.approve_invoice_reader_document("doc_itau"))
    run(server.approve_invoice_reader_document("doc_itau"))

    assert len(fake_backend.expenses.docs) == 3


def test_card_invoice_keeps_the_subset_sum_and_the_charge_gap(
    fake_backend, monkeypatch
):
    over = _analyze(fake_backend, monkeypatch, "doc_over", invoices.ITAU_OVEREXTRACTED)
    assert over["reconciliation_status"] == "adjusted"
    assert over["parsed_total"] == 426.80

    gap = _analyze(fake_backend, monkeypatch, "doc_gap", invoices.NEON_GAP)
    assert gap["reconciliation_status"] == "gap_covered"
    assert gap["non_purchase_total"] == 0.27

    run(server.approve_invoice_reader_document("doc_over"))
    run(server.approve_invoice_reader_document("doc_gap"))

    assert len(fake_backend.expenses.docs) == 6


# ---------------------------------------------------------------------------
# O portão: nada vira gasto sem conferência aritmética, nos dois regimes
# ---------------------------------------------------------------------------


def _mismatching_card_document():
    return invoice_ai.normalize_invoice_document(
        {**invoices.NEON.ai_document, "items": invoices.NEON.ai_document["items"][:2]}
    )


def _mismatching_bill_document():
    return invoice_ai.normalize_invoice_document(
        {
            **invoices.CONTA_LUZ.ai_document,
            "items": invoices.CONTA_LUZ.ai_document["items"][:3],
        }
    )


def _anchorless(fixture):
    return invoice_ai.normalize_invoice_document(
        {**fixture.ai_document, "reconciliation_anchor": None}
    )


@pytest.mark.parametrize(
    "fixture,document,expected_status",
    [
        (invoices.NEON, _mismatching_card_document(), "mismatch"),
        (invoices.CONTA_LUZ, _mismatching_bill_document(), "mismatch"),
        (invoices.NEON, _anchorless(invoices.NEON), "no_anchor"),
        (invoices.CONTA_LUZ, _anchorless(invoices.CONTA_LUZ), "no_anchor"),
    ],
    ids=["cartao_mismatch", "conta_mismatch", "cartao_sem_ancora", "conta_sem_ancora"],
)
def test_gate_blocks_approval_when_reconciliation_does_not_close(
    fake_backend, monkeypatch, fixture, document, expected_status
):
    held = _analyze(fake_backend, monkeypatch, "doc_gate", fixture, document=document)

    # O documento chega à revisão sinalizado, para o usuário não aprovar às cegas.
    assert held["status"] == server.INVOICE_STATUS_AWAITING_REVIEW
    assert held["reconciliation_status"] == expected_status
    assert held["reconciled"] is False
    assert held["review_warning"]

    with pytest.raises(HTTPException) as blocked:
        run(server.approve_invoice_reader_document("doc_gate"))

    assert blocked.value.status_code == 409
    assert fake_backend.expenses.docs == []
    assert _get_document(fake_backend, "doc_gate")["status"] == (
        server.INVOICE_STATUS_AWAITING_REVIEW
    )


def test_analysis_fails_when_the_ai_reads_nothing(fake_backend, monkeypatch):
    document = _analyze(
        fake_backend, monkeypatch, "doc_empty", invoices.NEON, document=None
    )
    assert document["status"] == server.INVOICE_STATUS_AWAITING_REVIEW

    _seed_document(fake_backend, "doc_null")
    _mock_ai(monkeypatch, invoices.NEON)
    monkeypatch.setattr(server, "extract_invoice_document", lambda _txt, **_kw: None)
    run(server.analyze_invoice_document("doc_null", "user_1", b"%PDF-1.4"))

    failed = _get_document(fake_backend, "doc_null")
    assert failed["status"] == server.INVOICE_STATUS_FAILED
    assert "Adicione os gastos manualmente" in failed["errors"][0]
    assert fake_backend.expenses.docs == []


def test_approval_is_refused_for_a_document_that_is_not_under_review(
    fake_backend, monkeypatch
):
    _seed_document(
        fake_backend, "doc_analyzing", status=server.INVOICE_STATUS_ANALYZING
    )

    with pytest.raises(HTTPException) as blocked:
        run(server.approve_invoice_reader_document("doc_analyzing"))

    assert blocked.value.status_code == 409


# ---------------------------------------------------------------------------
# Contestação e rejeição
# ---------------------------------------------------------------------------


def test_contesting_reprocesses_with_the_user_message_as_context(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)
    scheduled = _capture_background_tasks(monkeypatch)

    contested = run(
        server.contest_invoice_reader_document(
            "doc_luz",
            server.InvoiceContestRequest(message="isso é conta de água, não de luz"),
        )
    )

    assert contested["status"] == server.INVOICE_STATUS_CONTESTED
    assert contested["attempts"] == 1
    assert (
        contested["contestations"][0]["message"] == "isso é conta de água, não de luz"
    )
    assert fake_backend.expenses.docs == []

    # O reprocessamento manda a contestação junto e devolve o novo parecer.
    water = invoice_ai.normalize_invoice_document(
        {
            **invoices.CONTA_LUZ.ai_document,
            "doc_type": "conta_agua",
            "suggested_category": "Água",
            "summary": "parece ser uma conta de água",
        }
    )
    calls = _mock_ai(monkeypatch, invoices.CONTA_LUZ, document=water)
    for coro in scheduled:
        run(coro)

    assert calls[0]["feedback"] == ["isso é conta de água, não de luz"]
    reanalyzed = _get_document(fake_backend, "doc_luz")
    assert reanalyzed["status"] == server.INVOICE_STATUS_AWAITING_REVIEW
    assert reanalyzed["doc_type"] == "conta_agua"
    assert reanalyzed["ai_summary"] == "parece ser uma conta de água"

    run(server.approve_invoice_reader_document("doc_luz"))
    assert fake_backend.expenses.docs[0]["category"] == "Água"
    assert fake_backend.expenses.docs[0]["subcategory"] == "conta-agua"


def test_contesting_reuses_the_stored_pdf_text_and_stacks_the_history(
    fake_backend, monkeypatch
):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)
    scheduled = _capture_background_tasks(monkeypatch)

    for message in ("o valor certo é 447,99", "a categoria devia ser Moradia"):
        run(
            server.contest_invoice_reader_document(
                "doc_luz", server.InvoiceContestRequest(message=message)
            )
        )
        calls = _mock_ai(monkeypatch, invoices.CONTA_LUZ)
        run(scheduled.pop(0))

    # Sem novo upload: o texto do PDF guardado é reaproveitado.
    assert calls[-1]["raw_text"] == invoices.CONTA_LUZ.raw_text
    assert calls[-1]["feedback"] == [
        "o valor certo é 447,99",
        "a categoria devia ser Moradia",
    ]
    assert _get_document(fake_backend, "doc_luz")["attempts"] == 2


def test_contesting_stops_at_the_attempt_cap(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)
    scheduled = _capture_background_tasks(monkeypatch)

    for attempt in range(server.INVOICE_MAX_CONTESTATIONS):
        run(
            server.contest_invoice_reader_document(
                "doc_luz", server.InvoiceContestRequest(message=f"tentativa {attempt}")
            )
        )
        _mock_ai(monkeypatch, invoices.CONTA_LUZ)
        run(scheduled.pop(0))

    with pytest.raises(HTTPException) as capped:
        run(
            server.contest_invoice_reader_document(
                "doc_luz", server.InvoiceContestRequest(message="mais uma vez")
            )
        )

    assert capped.value.status_code == 409
    assert str(server.INVOICE_MAX_CONTESTATIONS) in capped.value.detail
    assert _get_document(fake_backend, "doc_luz")["attempts"] == (
        server.INVOICE_MAX_CONTESTATIONS
    )


def test_contesting_an_approved_document_is_refused(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)
    run(server.approve_invoice_reader_document("doc_luz"))

    with pytest.raises(HTTPException) as refused:
        run(
            server.contest_invoice_reader_document(
                "doc_luz", server.InvoiceContestRequest(message="errado")
            )
        )

    assert refused.value.status_code == 409
    assert len(fake_backend.expenses.docs) == 1


def test_contesting_requires_a_message(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)

    with pytest.raises(HTTPException) as empty:
        run(
            server.contest_invoice_reader_document(
                "doc_luz", server.InvoiceContestRequest(message="   ")
            )
        )

    assert empty.value.status_code == 400


def test_contesting_a_failed_reading_is_allowed(fake_backend, monkeypatch):
    _seed_document(
        fake_backend,
        "doc_failed",
        status=server.INVOICE_STATUS_FAILED,
        errors=["A IA não conseguiu ler o documento."],
        raw_text=invoices.CONDOMINIO.raw_text,
    )
    scheduled = _capture_background_tasks(monkeypatch)

    run(
        server.contest_invoice_reader_document(
            "doc_failed",
            server.InvoiceContestRequest(message="é um boleto de condomínio"),
        )
    )
    _mock_ai(monkeypatch, invoices.CONDOMINIO)
    run(scheduled.pop(0))

    assert _get_document(fake_backend, "doc_failed")["status"] == (
        server.INVOICE_STATUS_AWAITING_REVIEW
    )


def test_rejecting_discards_without_writing_anything(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)

    rejected = run(server.reject_invoice_reader_document("doc_luz"))

    assert rejected["status"] == server.INVOICE_STATUS_REJECTED
    assert fake_backend.expenses.docs == []
    assert fake_backend.financial_categories.docs == []

    with pytest.raises(HTTPException) as blocked:
        run(server.approve_invoice_reader_document("doc_luz"))
    assert blocked.value.status_code == 409


def test_rejecting_an_approved_document_is_refused(fake_backend, monkeypatch):
    _analyze(fake_backend, monkeypatch, "doc_luz", invoices.CONTA_LUZ)
    run(server.approve_invoice_reader_document("doc_luz"))

    with pytest.raises(HTTPException) as refused:
        run(server.reject_invoice_reader_document("doc_luz"))

    assert refused.value.status_code == 409
    assert len(fake_backend.expenses.docs) == 1


# ---------------------------------------------------------------------------
# Upload em lote e isolamento entre usuários
# ---------------------------------------------------------------------------


def test_upload_creates_a_batch_with_one_document_per_pdf(fake_backend, monkeypatch):
    scheduled = _capture_background_tasks(monkeypatch)

    batch = run(
        server.create_invoice_reader_job(
            requested_month="2026-08",
            files=[FakeUpload("luz.pdf"), FakeUpload("condominio.pdf")],
        )
    )

    assert batch["batch_id"].startswith("invlote_")
    assert [item["filename"] for item in batch["documents"]] == [
        "luz.pdf",
        "condominio.pdf",
    ]
    assert all(
        item["status"] == server.INVOICE_STATUS_ANALYZING for item in batch["documents"]
    )
    assert all(item["batch_id"] == batch["batch_id"] for item in batch["documents"])
    assert "raw_text" not in batch["documents"][0]
    assert len(fake_backend.invoice_reader_jobs.docs) == 2
    assert fake_backend.invoice_reader_batches.docs[0]["document_ids"] == [
        item["job_id"] for item in batch["documents"]
    ]
    assert len(scheduled) == 2

    _mock_ai(monkeypatch, invoices.CONTA_LUZ)
    for coro in scheduled:
        run(coro)

    documents = run(server.get_invoice_reader_jobs(limit=10))
    assert all(
        item["status"] == server.INVOICE_STATUS_AWAITING_REVIEW for item in documents
    )
    assert fake_backend.expenses.docs == []


def test_upload_still_accepts_a_single_file_field(fake_backend, monkeypatch):
    scheduled = _capture_background_tasks(monkeypatch)

    batch = run(
        server.create_invoice_reader_job(
            requested_month="2026-08", file=FakeUpload("fatura.pdf")
        )
    )

    assert [item["filename"] for item in batch["documents"]] == ["fatura.pdf"]
    _discard(scheduled)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"requested_month": "agosto", "files": [FakeUpload("a.pdf")]}, "Mês inválido"),
        ({"requested_month": "2026-08", "files": []}, "ao menos um arquivo"),
        (
            {
                "requested_month": "2026-08",
                "files": [
                    FakeUpload("a.pdf"),
                    FakeUpload("b.txt", content_type="text/plain"),
                ],
            },
            "Apenas arquivos PDF",
        ),
        (
            {
                "requested_month": "2026-08",
                "files": [FakeUpload("a.pdf"), FakeUpload("vazio.pdf", content=b"")],
            },
            "vazio",
        ),
    ],
    ids=["mes_invalido", "sem_arquivo", "nao_pdf", "pdf_vazio"],
)
def test_upload_validates_the_whole_batch_before_creating_anything(
    fake_backend, monkeypatch, kwargs, message
):
    _capture_background_tasks(monkeypatch)

    with pytest.raises(HTTPException) as invalid:
        run(server.create_invoice_reader_job(**kwargs))

    assert invalid.value.status_code == 400
    assert message in invalid.value.detail
    assert fake_backend.invoice_reader_jobs.docs == []
    assert fake_backend.invoice_reader_batches.docs == []


def test_a_user_never_reads_or_acts_on_another_users_document(
    fake_backend, monkeypatch
):
    _analyze(
        fake_backend,
        monkeypatch,
        "doc_de_outro",
        invoices.CONTA_LUZ,
        user_id="user_2",
    )
    _analyze(fake_backend, monkeypatch, "doc_meu", invoices.CONDOMINIO)

    # A sessão é sempre user_1 (fixture fake_backend).
    visible = run(server.get_invoice_reader_jobs(limit=10))
    assert [item["job_id"] for item in visible] == ["doc_meu"]

    for call in (
        server.approve_invoice_reader_document("doc_de_outro"),
        server.reject_invoice_reader_document("doc_de_outro"),
        server.contest_invoice_reader_document(
            "doc_de_outro", server.InvoiceContestRequest(message="não é meu")
        ),
    ):
        with pytest.raises(HTTPException) as forbidden:
            run(call)
        assert forbidden.value.status_code == 404

    # O documento do outro usuário continua intacto e sem gastos gravados.
    assert _get_document(fake_backend, "doc_de_outro")["status"] == (
        server.INVOICE_STATUS_AWAITING_REVIEW
    )
    assert fake_backend.expenses.docs == []


def test_batches_are_scoped_per_user(fake_backend, monkeypatch):
    scheduled = _capture_background_tasks(monkeypatch)

    batch = run(
        server.create_invoice_reader_job(
            requested_month="2026-08", files=[FakeUpload("luz.pdf")]
        )
    )

    assert fake_backend.invoice_reader_batches.docs[0]["user_id"] == "user_1"
    assert all(
        doc["user_id"] == "user_1" for doc in fake_backend.invoice_reader_jobs.docs
    )
    assert batch["documents"][0]["user_id"] == "user_1"
    _discard(scheduled)


def test_bank_specific_parsers_are_gone():
    removed = [
        "detect_bank_name",
        "extract_expected_total",
        "extract_invoice_items",
        "extract_non_purchase_invoice_items",
        "_parse_invoice_entries",
        "INVOICE_NON_PURCHASE_FLAGS",
        "extract_invoice_items_with_ai",
        "extract_invoice_items_from_pdf_with_ai",
        "run_invoice_ai_payload",
        # O job que extraía e gravava direto deu lugar ao fluxo de revisão.
        "process_invoice_reader_job",
    ]

    assert [name for name in removed if hasattr(server, name)] == []


def test_batch_analysis_caps_concurrent_groq_calls(fake_backend, monkeypatch):
    """Uma pasta com N contas não pode disparar N chamadas de uma vez.

    O free tier da Groq limita tokens por minuto na organização: sem teto, o
    lote inteiro volta em 429 e o usuário vê metade dos documentos falhando.
    """
    import threading

    monkeypatch.setenv("GROQ_INVOICE_MAX_CONCURRENCY", "2")
    server._invoice_ai_semaphores.clear()

    lock = threading.Lock()
    state = {"running": 0, "peak": 0}

    def fake_extract(_raw_text, **_kwargs):
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        time.sleep(0.02)
        with lock:
            state["running"] -= 1
        return invoice_ai.normalize_invoice_document(invoices.CONTA_LUZ.ai_document)

    monkeypatch.setattr(server, "extract_pdf_text", lambda _pdf: "conta")
    monkeypatch.setattr(server, "extract_invoice_document", fake_extract)

    job_ids = [f"doc_lote_{index}" for index in range(6)]
    for job_id in job_ids:
        _seed_document(fake_backend, job_id)

    async def analyze_all():
        await asyncio.gather(
            *[
                server.analyze_invoice_document(job_id, "user_1", b"%PDF-1.4")
                for job_id in job_ids
            ]
        )

    run(analyze_all())

    assert state["peak"] <= 2
    assert all(
        _get_document(fake_backend, job_id)["status"]
        == server.INVOICE_STATUS_AWAITING_REVIEW
        for job_id in job_ids
    )


def test_invoice_ai_concurrency_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("GROQ_INVOICE_MAX_CONCURRENCY", "nao-e-numero")
    assert (
        server.get_invoice_ai_max_concurrency()
        == server.DEFAULT_INVOICE_AI_MAX_CONCURRENCY
    )

    monkeypatch.setenv("GROQ_INVOICE_MAX_CONCURRENCY", "0")
    assert (
        server.get_invoice_ai_max_concurrency()
        == server.DEFAULT_INVOICE_AI_MAX_CONCURRENCY
    )

    monkeypatch.setenv("GROQ_INVOICE_MAX_CONCURRENCY", "5")
    assert server.get_invoice_ai_max_concurrency() == 5
