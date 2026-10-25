from __future__ import annotations

from app.auth import sanitize_namespace, write_allowed
from app.cognee_runtime.forget import orphan_node_ids
from app.cognee_runtime.recall import effective_namespace, in_namespace, namespace_nodeset


def test_effective_namespace_legacy_firewall_nodes_are_demo():
    for node_type in ("Repo", "AgentSession", "Memory"):
        assert effective_namespace({"type": node_type}) == "demo"
        assert effective_namespace({"type": node_type, "namespace": None}) == "demo"


def test_effective_namespace_unattributable_nodes_are_unreadable():
    assert effective_namespace({}) is None
    assert effective_namespace({"type": "Entity", "name": "taskflow-api"}) is None
    assert effective_namespace({"type": "DocumentChunk", "text": "x", "belongs_to_set": []}) is None
    # SessionEvent inherits its session's namespace; on its own it is not attributable.
    assert effective_namespace({"type": "SessionEvent"}) is None
    for allowed in (None, set(), {"demo"}, {"demo", "public"}):
        assert not in_namespace({"type": "DocumentChunk", "text": "tenant transcript"}, allowed)


def test_effective_namespace_reads_cognee_node_set_tags():
    assert namespace_nodeset("acme") == "cf_ns_acme"
    assert effective_namespace({"type": "Entity", "belongs_to_set": ["cf_ns_acme"]}) == "acme"
    assert effective_namespace({"type": "Entity", "belongs_to_set": '["cf_ns_acme"]'}) == "acme"
    assert effective_namespace({"type": "Entity", "belongs_to_set": [{"name": "cf_ns_demo"}]}) == "demo"
    assert effective_namespace({"type": "Rule", "belongs_to_set": ["coding_agent_rules_acme"]}) == "acme"
    assert effective_namespace({"type": "Rule", "belongs_to_set": ["coding_agent_rules"]}) == "demo"
    assert effective_namespace({"type": "Entity", "belongs_to_set": ["cf_ns_"]}) is None
    assert effective_namespace({"type": "Entity", "belongs_to_set": ["unrelated_set"]}) is None


def test_in_namespace_respects_demo_and_public():
    props = {"namespace": "public"}
    assert not in_namespace(props, {"demo"})
    assert in_namespace(props, {"demo", "public"})
    assert in_namespace({"type": "Memory"}, None)
    assert in_namespace({"type": "Memory"}, set())
    tagged = {"type": "Entity", "belongs_to_set": ["cf_ns_acme"]}
    assert in_namespace(tagged, {"acme"})
    assert not in_namespace(tagged, None)
    assert not in_namespace(tagged, {"demo", "public"})


def test_write_allowed_requires_exact_bearer_when_token_set(monkeypatch):
    monkeypatch.setenv("CF_WRITE_TOKEN", "secret-token")
    assert write_allowed("Bearer secret-token", "secret-token")
    assert not write_allowed(None, "secret-token")
    assert not write_allowed("Bearer wrong", "secret-token")
    assert not write_allowed("Token secret-token", "secret-token")


def test_write_allowed_opens_when_env_unset():
    assert write_allowed(None, None)
    assert write_allowed("anything", None)


def test_sanitize_namespace_normalizes_and_rejects_invalid():
    assert sanitize_namespace("Acme-Corp") == "acme-corp"
    assert sanitize_namespace("  tenant_1  ") == "tenant_1"
    assert sanitize_namespace("") is None
    assert sanitize_namespace(None) is None
    assert sanitize_namespace("bad ns") is None
    assert sanitize_namespace("drop;table") is None
    assert sanitize_namespace("a" * 65) is None
    assert sanitize_namespace("-leading") is None


def test_orphan_node_ids_cleans_session_events_and_repo_when_last_memory_removed():
    nodes = [
        ("repo-1", {"type": "Repo", "name": "demo-repo"}),
        ("sess-1", {"type": "AgentSession", "session_id": "s1", "task": "t1"}),
        ("evt-1", {"type": "SessionEvent", "session_id": "s1", "event_id": "s1:e1"}),
        ("evt-2", {"type": "SessionEvent", "session_id": "s1", "event_id": "s1:e2"}),
        ("mem-1", {"type": "Memory", "memory_id": "m1", "source_session_id": "s1"}),
    ]
    edges = [
        ("sess-1", "repo-1", "repo"),
        ("evt-1", "sess-1", "session"),
        ("evt-2", "sess-1", "session"),
    ]
    assert orphan_node_ids(nodes, edges, "mem-1") == {"sess-1", "evt-1", "evt-2", "repo-1"}


def test_orphan_node_ids_returns_empty_when_session_still_has_other_memory():
    nodes = [
        ("repo-1", {"type": "Repo", "name": "demo-repo"}),
        ("sess-1", {"type": "AgentSession", "session_id": "s1", "task": "t1"}),
        ("evt-1", {"type": "SessionEvent", "session_id": "s1", "event_id": "s1:e1"}),
        ("mem-1", {"type": "Memory", "memory_id": "m1", "source_session_id": "s1"}),
        ("mem-2", {"type": "Memory", "memory_id": "m2", "source_session_id": "s1"}),
    ]
    edges = [("sess-1", "repo-1", "repo")]
    assert orphan_node_ids(nodes, edges, "mem-1") == set()


def test_orphan_node_ids_keeps_repo_when_other_session_still_references_it():
    nodes = [
        ("repo-1", {"type": "Repo", "name": "demo-repo"}),
        ("sess-1", {"type": "AgentSession", "session_id": "s1", "task": "t1"}),
        ("sess-2", {"type": "AgentSession", "session_id": "s2", "task": "t2"}),
        ("evt-1", {"type": "SessionEvent", "session_id": "s1", "event_id": "s1:e1"}),
        ("mem-1", {"type": "Memory", "memory_id": "m1", "source_session_id": "s1"}),
    ]
    edges = [
        ("sess-1", "repo-1", "repo"),
        ("sess-2", "repo-1", "repo"),
        ("evt-1", "sess-1", "session"),
    ]
    assert orphan_node_ids(nodes, edges, "mem-1") == {"sess-1", "evt-1"}
