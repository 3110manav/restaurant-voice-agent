"""An order must be saved even when a database migration hasn't been applied yet."""
import app.erp as erp


class FakeTable:
    def __init__(self, rejects):
        self.rejects, self.saved = rejects, []

    def insert(self, row):
        self.row = row
        return self

    def execute(self):
        bad = self.rejects & set(self.row)
        if bad:
            raise RuntimeError(f"column {sorted(bad)[0]} does not exist")
        self.saved.append(self.row)
        return type("R", (), {"data": [{"id": "o1", **self.row}]})()


class FakeClient:
    def __init__(self, rejects):
        self.orders = FakeTable(rejects)

    def table(self, name):
        return self.orders


EXTRA = {"customer_id": "c1", "caller_phone": "+919876543210", "short_code": "K7M2P", "rx_path": "whatsapp"}


def place(monkeypatch, rejects):
    fake = FakeClient(rejects)
    monkeypatch.setattr(erp, "_client", fake)
    row = erp.record_order("s1", "store", [], 10.0, restaurant_id="r1", extra=dict(EXTRA))
    return row, fake.orders.saved


def test_with_every_migration_applied_the_whole_order_is_saved(monkeypatch):
    row, saved = place(monkeypatch, set())
    assert row["id"] == "o1" and saved[0]["short_code"] == "K7M2P" and saved[0]["customer_id"] == "c1"


def test_without_migration_003_the_customer_columns_are_still_saved(monkeypatch):
    row, saved = place(monkeypatch, {"short_code", "rx_path"})
    assert saved[0]["customer_id"] == "c1" and "short_code" not in saved[0]


def test_without_migration_002_the_bare_order_is_still_saved(monkeypatch):
    row, saved = place(monkeypatch, {"short_code", "rx_path", "customer_id", "caller_phone"})
    assert row is not None and "customer_id" not in saved[0] and saved[0]["total"] == 10.0


def test_an_order_that_cannot_be_saved_returns_none_without_raising(monkeypatch):
    row, saved = place(monkeypatch, {"session_id"})
    assert row is None and saved == []
