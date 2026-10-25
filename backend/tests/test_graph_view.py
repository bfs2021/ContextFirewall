"""Tests for graph_view namespace filtering and limit (#46)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.cognee_runtime.graph import graph_view


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_namespace_filter_applies_before_limit(monkeypatch):
    """A tenant's graph should not be emptied by other tenants' data volume."""
    raw_nodes = [
        (f"node-{i}", {"type": "Document", "name": f"doc-{i}", "namespace": "other"})
        for i in range(500)
    ] + [
        ("mine-1", {"type": "Document", "name": "mine-1", "namespace": "demo"}),
        ("mine-2", {"type": "Document", "name": "mine-2", "namespace": "demo"}),
    ]
    raw_edges = []

    async def fake_get_graph():
        return None, raw_nodes, raw_edges

    monkeypatch.setattr("app.cognee_runtime.graph._get_graph", fake_get_graph)
    result = _run(graph_view(limit=400, namespaces={"demo"}))
    assert len(result["nodes"]) == 2
    assert {n["id"] for n in result["nodes"]} == {"mine-1", "mine-2"}


def test_error_message_is_generic(monkeypatch):
    """repr(exc) can leak internal hostnames; the client sees a generic message."""
    async def fail():
        raise ConnectionError("redis://internal-host:6379 connection refused")

    monkeypatch.setattr("app.cognee_runtime.graph._get_graph", fail)
    result = _run(graph_view())
    assert "internal-host" not in result["error"]
    assert "redis" not in result["error"]
    assert "Failed" in result["error"]
