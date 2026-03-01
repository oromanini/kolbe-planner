import asyncio
import os
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
        items = [self._project(doc, projection) for doc in self.docs if self._matches(doc, query)]
        return FakeCursor(items)

    async def insert_one(self, doc):
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


class FakeDB:
    def __init__(self):
        self.financial_methods = FakeCollection()
        self.financial_categories = FakeCollection()
        self.expenses = FakeCollection()
        self.incomes = FakeCollection()
        self.savings = FakeCollection()


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
    assert len(fake_backend.financial_methods.docs) == len(server.DEFAULT_FINANCIAL_METHODS) + 1


def test_categories_get_and_create_and_duplicate_conflict(fake_backend):
    created = run(server.create_category(server.CategoryCreate(name="Carro", icon="car")))
    assert created["name"] == "Carro"

    with pytest.raises(HTTPException) as exc:
        run(server.create_category(server.CategoryCreate(name="Carro", icon="car")))
    assert exc.value.status_code == 409

    listing = run(server.get_categories())
    assert len(listing) == 1


def test_categories_update_delete_and_force_delete_with_linked_expenses(fake_backend):
    fake_backend.financial_categories.docs.append({"category_id": "cat_1", "user_id": "user_1", "name": "Mercado", "icon": "cart"})
    fake_backend.financial_categories.docs.append({"category_id": "cat_2", "user_id": "user_1", "name": "Lazer", "icon": "smile"})
    fake_backend.expenses.docs.append({"expense_id": "exp_1", "user_id": "user_1", "category": "Mercado", "month": "2026-03", "amount": 10})

    with pytest.raises(HTTPException) as conflict:
        run(server.update_category("cat_1", server.CategoryUpdate(name="Lazer", icon="cart")))
    assert conflict.value.status_code == 409

    updated = run(server.update_category("cat_1", server.CategoryUpdate(name="Feira", icon="cart")))
    assert updated["name"] == "Feira"
    assert fake_backend.expenses.docs[0]["category"] == "Feira"

    with pytest.raises(HTTPException) as blocked_delete:
        run(server.delete_category("cat_1"))
    assert blocked_delete.value.status_code == 409

    deleted = run(server.delete_category("cat_1", force=True))
    assert deleted["deleted_expenses"] == 1


def test_expenses_get_create_and_delete(fake_backend):
    fake_backend.financial_categories.docs.append({"category_id": "cat_1", "user_id": "user_1", "name": "Transporte", "icon": "car"})

    with pytest.raises(HTTPException) as invalid:
        run(
            server.create_expense(
                server.ExpenseCreate(
                    name="Ônibus", amount=7.5, method_id="method_1", category="Inexistente", month="2026-03"
                )
            )
        )
    assert invalid.value.status_code == 400

    created = run(
        server.create_expense(
            server.ExpenseCreate(name="Ônibus", amount=7.5, method_id="method_1", category="Transporte", month="2026-03")
        )
    )
    assert created["category"] == "Transporte"

    monthly = run(server.get_expenses("2026-03"))
    assert len(monthly) == 1

    deleted = run(server.delete_expense(created["expense_id"]))
    assert deleted["message"] == "Deleted"

    with pytest.raises(HTTPException) as missing:
        run(server.delete_expense("exp_missing"))
    assert missing.value.status_code == 404


def test_incomes_get_create_and_delete(fake_backend):
    created = run(server.create_income(server.IncomeCreate(name="Salário", amount=3200, month="2026-03")))
    assert created["name"] == "Salário"

    monthly = run(server.get_incomes("2026-03"))
    assert len(monthly) == 1

    deleted = run(server.delete_income(created["income_id"]))
    assert deleted["message"] == "Deleted"

    with pytest.raises(HTTPException) as missing:
        run(server.delete_income("inc_missing"))
    assert missing.value.status_code == 404


def test_savings_get_create_and_update(fake_backend):
    assert run(server.get_savings()) == []

    created = run(server.create_savings(server.SavingsCreate(name="Reserva", type="reserva", amount=100)))
    assert created["amount"] == 100

    updated = run(server.update_savings(created["savings_id"], amount=150))
    assert updated["amount"] == 150

    with pytest.raises(HTTPException) as missing:
        run(server.update_savings("sav_missing", amount=150))
    assert missing.value.status_code == 404


def test_summary_calculates_totals_and_breakdown(fake_backend):
    fake_backend.incomes.docs.extend(
        [
            {"income_id": "inc_1", "user_id": "user_1", "name": "Salário", "amount": 3000, "month": "2026-03"},
            {"income_id": "inc_2", "user_id": "user_1", "name": "Freela", "amount": 1000, "month": "2026-03"},
        ]
    )
    fake_backend.expenses.docs.extend(
        [
            {"expense_id": "exp_1", "user_id": "user_1", "name": "Mercado", "amount": 500, "category": "Casa", "month": "2026-03"},
            {"expense_id": "exp_2", "user_id": "user_1", "name": "Gasolina", "amount": 300, "category": "Carro", "month": "2026-03"},
            {"expense_id": "exp_3", "user_id": "user_1", "name": "Água", "amount": 200, "category": "Casa", "month": "2026-03"},
        ]
    )

    summary = run(server.get_summary("2026-03"))

    assert summary["total_income"] == 4000
    assert summary["total_expenses"] == 1000
    assert summary["balance"] == 3000
    assert summary["category_breakdown"] == {"Casa": 700, "Carro": 300}
