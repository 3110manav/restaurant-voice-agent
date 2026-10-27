"""The shared embedding rate-limit budget: bulk uploads, live edits and guests'
searches all draw on the same per-minute allowance (Gemini free tier: 100/min)."""
import time

import pytest

from app.menu import embedding


@pytest.fixture(autouse=True)
def clean_state():
    embedding._window.clear()
    embedding._query_cache.clear()
    yield
    embedding._window.clear()
    embedding._query_cache.clear()


def test_under_budget_does_not_wait(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    embedding._wait_for_budget(40, embedding.DOCUMENT_BUDGET)
    embedding._wait_for_budget(30, embedding.DOCUMENT_BUDGET)
    assert sleeps == []


def test_over_budget_waits_for_the_window_to_clear(monkeypatch):
    embedding._wait_for_budget(70, embedding.DOCUMENT_BUDGET)
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        embedding._window.clear()  # pretend the minute passed

    monkeypatch.setattr(time, "sleep", fake_sleep)
    embedding._wait_for_budget(40, embedding.DOCUMENT_BUDGET)
    assert len(slept) == 1 and slept[0] > 30


def test_queries_may_use_headroom_that_bulk_uploads_may_not(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: pytest.fail("a query shouldn't wait here"))
    embedding._wait_for_budget(embedding.DOCUMENT_BUDGET, embedding.DOCUMENT_BUDGET)  # bulk upload used its share
    embedding._wait_for_budget(1, embedding.QUERY_BUDGET)  # a guest's search still goes straight through


def test_documents_are_embedded_in_batches(monkeypatch):
    batches = []

    class FakeClient:
        def embed_documents(self, texts, task_type=None):
            batches.append((len(texts), task_type))
            return [[0.0]] * len(texts)

    monkeypatch.setattr(embedding, "_client", lambda: FakeClient())
    monkeypatch.setattr(embedding, "_wait_for_budget", lambda n, limit: None)
    out = embedding.embed_documents([f"t{i}" for i in range(95)])
    assert len(out) == 95 and batches == [(40, "RETRIEVAL_DOCUMENT"), (40, "RETRIEVAL_DOCUMENT"), (15, "RETRIEVAL_DOCUMENT")]


def test_query_embeddings_are_cached_across_phrasing_noise(monkeypatch):
    calls = []

    class FakeClient:
        def embed_query(self, text, task_type=None):
            calls.append((text, task_type))
            return [1.0, 2.0]

    monkeypatch.setattr(embedding, "_client", lambda: FakeClient())
    monkeypatch.setattr(embedding, "_wait_for_budget", lambda n, limit: None)
    a = embedding.embed_query("Something  SPICY")
    b = embedding.embed_query("something spicy")
    assert a == b and calls == [("something spicy", "RETRIEVAL_QUERY")]


def test_a_quota_error_is_retried_once(monkeypatch):
    attempts = []
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "ok"

    assert embedding._with_retry(flaky) == "ok" and len(attempts) == 2
