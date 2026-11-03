"""A small in-memory stand-in for the Supabase client, with just the calls app/phone/repository.py uses,
including place_phone_order's all-or-nothing behaviour."""
import copy
import itertools
import uuid


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters = []
        self.action, self.payload = "select", None
        self.ordering, self.max_rows = None, None

    def select(self, _columns="*"):
        return self

    def insert(self, row):
        self.action, self.payload = "insert", row
        return self

    def upsert(self, row, on_conflict="id"):
        self.action, self.payload, self.conflict = "upsert", row, on_conflict
        return self

    def update(self, fields):
        self.action, self.payload = "update", fields
        return self

    def eq(self, column, value):
        self.filters.append(lambda row: row.get(column) == value)
        return self

    def in_(self, column, values):
        self.filters.append(lambda row: row.get(column) in values)
        return self

    def lte(self, column, value):
        self.filters.append(lambda row: row.get(column) is not None and row[column] <= value)
        return self

    def lt(self, column, value):
        self.filters.append(lambda row: row.get(column) is not None and row[column] < value)
        return self

    def order(self, column, desc=False):
        self.ordering = (column, desc)
        return self

    def limit(self, count):
        self.max_rows = count
        return self

    def _matching(self):
        return [row for row in self.db.tables.setdefault(self.table, []) if all(f(row) for f in self.filters)]

    def execute(self):
        if self.db.failing:
            raise RuntimeError("database is down")
        if self.action == "insert":
            row = {**self.db.defaults(self.table), **copy.deepcopy(self.payload)}
            self.db.tables.setdefault(self.table, []).append(row)
            return _Result([copy.deepcopy(row)])
        if self.action == "upsert":
            for row in self.db.tables.setdefault(self.table, []):
                if row.get(self.conflict) == self.payload[self.conflict]:
                    row.update(copy.deepcopy(self.payload))
                    return _Result([copy.deepcopy(row)])
            self.action = "insert"
            return self.execute()
        if self.action == "update":
            matched = self._matching()
            for row in matched:
                row.update(copy.deepcopy(self.payload))
            return _Result(copy.deepcopy(matched))
        rows = self._matching()
        if self.ordering:
            rows = sorted(rows, key=lambda row: str(row.get(self.ordering[0])), reverse=self.ordering[1])
        return _Result(copy.deepcopy(rows[: self.max_rows] if self.max_rows else rows))


class _Rpc:
    def __init__(self, db, params):
        self.db, self.params = db, params

    def execute(self):
        if self.db.failing:
            raise RuntimeError("database is down")
        order = copy.deepcopy(self.params["p_order"])
        orders = self.db.tables.setdefault("orders", [])
        if not any(row["id"] == order["id"] for row in orders):
            orders.append({"status": "placed", "payment_status": "unpaid", **order})
            for message in self.params["p_messages"]:
                self.db.tables.setdefault("message_outbox", []).append(
                    {
                        **self.db.defaults("message_outbox"),
                        **copy.deepcopy(message),
                        "order_id": order["id"],
                        "call_id": order.get("call_id"),
                    }
                )
        return _Result(order["id"])


class FakeSupabase:
    def __init__(self):
        self.tables = {}
        self.failing = False
        self._clock = itertools.count()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        assert name == "place_phone_order"
        return _Rpc(self, params)

    def defaults(self, table):
        row = {"id": str(uuid.uuid4())}
        if table == "message_outbox":
            row.update(
                status="pending", attempts=0, last_error=None, wa_message_id=None, delivery_status=None,
                next_attempt_at="2000-01-01T00:00:00+00:00", claimed_at=None, order_id=None, call_id=None,
                created_at=f"{next(self._clock):012d}",
            )
        return row
