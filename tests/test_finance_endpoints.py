import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_database")

from backend import server  # noqa: E402


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
        if projection.get("_id") == 0 and len(projection) == 1:
            return dict(doc)
        projected = {}
        for key, value in projection.items():
            if key == "_id":
                continue
            if value and key in doc:
                projected[key] = doc[key]
        return projected

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
        {"category_id": "cat_1", "user_id": "user_1", "name": "Mercado", "icon": "cart"}
    )
    fake_backend.financial_categories.docs.append(
        {"category_id": "cat_2", "user_id": "user_1", "name": "Lazer", "icon": "smile"}
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
    assert deleted["deleted_expenses"] == 1


def test_expenses_get_create_and_delete(fake_backend):
    fake_backend.financial_categories.docs.append(
        {
            "category_id": "cat_1",
            "user_id": "user_1",
            "name": "Transporte",
            "icon": "car",
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
    created = run(
        server.create_income(
            server.IncomeCreate(name="Salário", amount=3200, month="2026-03")
        )
    )
    assert created["name"] == "Salário"
    assert "_id" not in created

    monthly = run(server.get_incomes("2026-03"))
    assert len(monthly) == 1

    deleted = run(server.delete_income(created["income_id"]))
    assert deleted["message"] == "Deleted"

    with pytest.raises(HTTPException) as missing:
        run(server.delete_income("inc_missing"))
    assert missing.value.status_code == 404


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


def test_invoice_reader_extractors_parse_examples():
    nubank_line = "12 FEV iFood - NuPay R$ 61,89"
    itau_line = "04/07 AZUL LINHAS IP 8/12 530,33"
    raw = f"""NUBANK
Cartão final 7071
Total da fatura R$ 591,89
{nubank_line}
{itau_line}
"""

    items = server.extract_invoice_items(raw)
    assert any(
        item["name"] == "iFood - NuPay" and item["amount"] == 61.89 for item in items
    )
    assert any(
        "AZUL LINHAS IP 8/12" in item["name"] and item["amount"] == 530.33
        for item in items
    )
    assert server.extract_expected_total(raw) == 591.89
    assert server.detect_bank_name(raw) == "Nubank"
    assert server.detect_card_suffix(raw) == "7071"


def test_extract_expected_total_prefers_invoice_total_over_payment_and_financed_total():
    raw = """
O total da sua fatura é:
R$ 876,81
Pagamento via conta -1.312,97
Valor total financiado R$789,13
"""

    assert server.extract_expected_total(raw) == 876.81


def test_select_items_matching_expected_total_finds_subset_when_ai_overextracts():
    items = [
        {"name": "AZUL LINHAS", "amount": 530.33},
        {"name": "AZUL LINHAS", "amount": 126.44},
        {"name": "JIM.COM", "amount": 57.98},
        {"name": "AIRBNB", "amount": 33.08},
        {"name": "AZUL LINHAS", "amount": 128.98},
        {"name": "DEMais FATURAS", "amount": 876.81},
    ]

    selected = server.select_items_matching_expected_total(items, 876.81)

    assert selected is not None
    assert round(sum(item["amount"] for item in selected), 2) == 876.81
    assert len(selected) == 5


def test_invoice_reader_job_list_hides_expired_finished_jobs(fake_backend):
    now = datetime.now(timezone.utc)
    fake_backend.invoice_reader_jobs.docs.append(
        {
            "job_id": "invjob_1",
            "user_id": "user_1",
            "status": "queued",
            "created_at": (now - timedelta(minutes=2)).isoformat(),
            "finished_at": None,
        }
    )
    fake_backend.invoice_reader_jobs.docs.append(
        {
            "job_id": "invjob_2",
            "user_id": "user_1",
            "status": "completed",
            "created_at": (now - timedelta(minutes=1)).isoformat(),
            "finished_at": (now - timedelta(minutes=1)).isoformat(),
        }
    )
    fake_backend.invoice_reader_jobs.docs.append(
        {
            "job_id": "invjob_3",
            "user_id": "user_1",
            "status": "failed",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
            "finished_at": (now - timedelta(minutes=10)).isoformat(),
        }
    )

    jobs = run(server.get_invoice_reader_jobs(limit=10))
    assert [job["job_id"] for job in jobs] == ["invjob_2", "invjob_1"]
    assert all(
        doc["job_id"] != "invjob_3" for doc in fake_backend.invoice_reader_jobs.docs
    )


def test_invoice_reader_ai_extractor_uses_openai_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output_text": '{"items":[{"name":"AZUL LINHAS IP 8/12","amount":530.33},{"name":"JIM.COM *3726A4/05","amount":57.98}]}'
            }

    class FakeRequests:
        @staticmethod
        def post(*_args, **_kwargs):
            return FakeResponse()

    import sys

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)

    items = server.extract_invoice_items_with_ai("fatura exemplo")
    assert len(items) == 2
    assert items[0]["name"] == "AZUL LINHAS IP 8/12"
    assert items[0]["amount"] == 530.33


def test_invoice_reader_pdf_ai_extractor_sends_pdf_file(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": '{"items":[{"name":"COMPRA","amount":10.5}]}'}

    class FakeRequests:
        @staticmethod
        def post(*_args, **kwargs):
            captured["json"] = kwargs.get("json", {})
            return FakeResponse()

    import sys

    monkeypatch.setitem(sys.modules, "requests", FakeRequests)

    items = server.extract_invoice_items_from_pdf_with_ai(b"%PDF-1.4", "fat.pdf", 10.5)
    assert items == [{"name": "COMPRA", "amount": 10.5}]

    payload = captured["json"]
    file_part = payload["input"][1]["content"][0]
    assert file_part["type"] == "input_file"
    assert file_part["filename"] == "fat.pdf"
    assert file_part["file_data"].startswith("data:application/pdf;base64,")


def test_invoice_reader_prefers_pdf_ai_as_primary_parser(fake_backend, monkeypatch):
    fake_backend.financial_methods.docs.append(
        {"method_id": "method_credit", "user_id": "user_1", "name": "Crédito à vista"}
    )

    raw_ai_calls = {"count": 0}
    regex_calls = {"count": 0}

    monkeypatch.setattr(server, "extract_pdf_text", lambda _pdf: "fatura")
    monkeypatch.setattr(server, "extract_expected_total", lambda _txt: 530.33)

    monkeypatch.setattr(
        server,
        "extract_invoice_items_from_pdf_with_ai",
        lambda *_args, **_kwargs: [{"name": "PDF AI ITEM", "amount": 530.33}],
    )

    def fake_raw_ai(_txt, _expected=None):
        raw_ai_calls["count"] += 1
        return [{"name": "RAW AI ITEM", "amount": 530.33}]

    def fake_regex(_txt):
        regex_calls["count"] += 1
        return [{"name": "REGEX ITEM", "amount": 530.33}]

    monkeypatch.setattr(server, "extract_invoice_items_with_ai", fake_raw_ai)
    monkeypatch.setattr(server, "extract_invoice_items", fake_regex)

    run(
        server.process_invoice_reader_job(
            "job_1", "user_1", "2026-03", "fat.pdf", b"pdf"
        )
    )

    assert raw_ai_calls["count"] == 0
    assert regex_calls["count"] == 0
    assert len(fake_backend.expenses.docs) == 1
    assert fake_backend.expenses.docs[0]["name"] == "PDF AI ITEM"


def test_invoice_reader_fails_when_ai_total_does_not_match(fake_backend, monkeypatch):
    fake_backend.financial_methods.docs.append(
        {"method_id": "method_credit", "user_id": "user_1", "name": "Crédito à vista"}
    )
    fake_backend.invoice_reader_jobs.docs.append(
        {"job_id": "job_2", "user_id": "user_1", "status": "queued"}
    )

    monkeypatch.setattr(server, "extract_pdf_text", lambda _pdf: "fatura")
    monkeypatch.setattr(server, "extract_expected_total", lambda _txt: 100.00)
    monkeypatch.setattr(
        server,
        "extract_invoice_items_with_ai",
        lambda _txt, _expected=None: [{"name": "AI ITEM", "amount": 90.00}],
    )

    run(
        server.process_invoice_reader_job(
            "job_2", "user_1", "2026-03", "fat.pdf", b"pdf"
        )
    )

    assert len(fake_backend.expenses.docs) == 0
    job = next(
        doc
        for doc in fake_backend.invoice_reader_jobs.docs
        if doc.get("job_id") == "job_2"
    )
    assert job["status"] == "failed"
    assert "Adicione os gastos manualmente" in job["errors"][0]


def test_invoice_reader_fails_when_all_parsers_return_no_items(
    fake_backend, monkeypatch
):
    fake_backend.financial_methods.docs.append(
        {"method_id": "method_credit", "user_id": "user_1", "name": "Crédito à vista"}
    )
    fake_backend.invoice_reader_jobs.docs.append(
        {"job_id": "job_3", "user_id": "user_1", "status": "queued"}
    )

    monkeypatch.setattr(server, "extract_pdf_text", lambda _pdf: "fatura")
    monkeypatch.setattr(server, "extract_expected_total", lambda _txt: 100.00)
    monkeypatch.setattr(
        server, "extract_invoice_items_from_pdf_with_ai", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        server, "extract_invoice_items_with_ai", lambda _txt, _expected=None: []
    )
    monkeypatch.setattr(server, "extract_invoice_items", lambda _txt: [])

    run(
        server.process_invoice_reader_job(
            "job_3", "user_1", "2026-03", "fat.pdf", b"pdf"
        )
    )

    assert len(fake_backend.expenses.docs) == 0
    job = next(
        doc
        for doc in fake_backend.invoice_reader_jobs.docs
        if doc.get("job_id") == "job_3"
    )
    assert job["status"] == "failed"
    assert "Adicione os gastos manualmente" in job["errors"][0]
