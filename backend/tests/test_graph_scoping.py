"""Tenant isolation of the graph view and of cognified (Cognee-derived) nodes."""
from __future__ import annotations

import asyncio
import sys
import types

import app.cognee_runtime.graph as graph
import app.cognee_runtime.ingest as ingest

NODES = [
    ("demo-sess", {"type": "AgentSession", "session_id": "demo-1", "task": "demo task", "namespace": "demo"}),
    ("demo-evt", {"type": "SessionEvent", "session_id": "demo-1", "content": "demo event"}),
    ("demo-chunk", {"type": "DocumentChunk", "text": "demo transcript", "belongs_to_set": ["cf_ns_demo"]}),
    ("acme-sess", {"type": "AgentSession", "session_id": "acme-1", "task": "acme task", "namespace": "acme"}),
    ("acme-evt", {"type": "SessionEvent", "session_id": "acme-1", "content": "acme private event"}),
    ("acme-chunk", {"type": "DocumentChunk", "text": "acme private transcript", "belongs_to_set": ["cf_ns_acme"]}),
    ("acme-entity", {"type": "Entity", "name": "acme-internal-service", "belongs_to_set": ["cf_ns_acme"]}),
    ("acme-rule", {"type": "Rule", "text": "acme rule", "belongs_to_set": ["coding_agent_rules_acme"]}),
    ("legacy-chunk", {"type": "DocumentChunk", "text": "untagged transcript from any tenant"}),
    ("legacy-entity", {"type": "Entity", "name": "untagged-entity"}),
    ("orphan-evt", {"type": "SessionEvent", "session_id": "missing", "content": "orphan event"}),
]
EDGES = [
    ("demo-evt", "demo-sess", "session"),
    ("acme-chunk", "acme-entity", "contains"),
    ("demo-chunk", "acme-entity", "contains"),
    ("legacy-chunk", "demo-chunk", "contains"),
]


def _view(monkeypatch, namespaces):
    async def fake_get_graph():
        return None, list(NODES), list(EDGES)

    monkeypatch.setattr(graph, "_get_graph", fake_get_graph)
    data = asyncio.run(graph.graph_view(namespaces=namespaces))
    return {n["id"] for n in data["nodes"]}, {(e["source"], e["target"]) for e in data["edges"]}


def test_anonymous_graph_view_shows_only_demo(monkeypatch):
    ids, edges = _view(monkeypatch, None)
    assert ids == {"demo-sess", "demo-evt", "demo-chunk"}
    assert edges == {("demo-evt", "demo-sess")}


def test_demo_reader_never_sees_other_tenants_or_untagged_nodes(monkeypatch):
    ids, _ = _view(monkeypatch, {"demo", "public"})
    assert ids == {"demo-sess", "demo-evt", "demo-chunk"}


def test_tenant_sees_only_its_own_nodes(monkeypatch):
    ids, edges = _view(monkeypatch, {"acme"})
    assert ids == {"acme-sess", "acme-evt", "acme-chunk", "acme-entity", "acme-rule"}
    assert edges == {("acme-chunk", "acme-entity")}


def test_ingest_tags_cognified_nodes_with_namespace(monkeypatch):
    calls = {}

    async def fake_add(data, dataset_name=None, node_set=None, **kwargs):
        calls["add"] = {"dataset_name": dataset_name, "node_set": node_set}

    async def fake_cognify(datasets=None, **kwargs):
        calls["cognify"] = datasets

    async def fake_add_data_points(nodes, *args, **kwargs):
        calls["data_points"] = len(nodes)

    fake_cognee = types.SimpleNamespace(add=fake_add, cognify=fake_cognify)
    fake_storage = types.ModuleType("cognee.tasks.storage")
    fake_storage.add_data_points = fake_add_data_points
    monkeypatch.setitem(sys.modules, "cognee", fake_cognee)
    monkeypatch.setitem(sys.modules, "cognee.tasks.storage", fake_storage)
    monkeypatch.setattr(ingest, "configure_cognee", lambda: None)

    session = {
        "session_id": "acme-1",
        "task": "t",
        "repo": {"name": "r"},
        "events": [{"kind": "note", "content": "hello"}],
        "memories": [{"text": "a fact", "subject": "s"}],
    }
    res = asyncio.run(ingest.ingest_session(session, cognify=True, namespace="acme"))
    assert res["cognified"] is True
    assert calls["add"]["node_set"] == ["cf_ns_acme"]
