"""
Tests del LLMClassifier — con un `chat` inyectado, sin red.
"""

from __future__ import annotations

import json

import pytest

from c4norm.classify import HeuristicClassifier, LLMClassifier, get_classifier
from c4norm.model import C4Type, Diagram, Edge, Node


def _diagram() -> Diagram:
    return Diagram(
        name="t",
        nodes=[
            Node(id="a", raw_label="Usuario", shape="rectangle"),
            Node(id="b", raw_label="API", shape="rectangle"),
        ],
        edges=[Edge(id="e1", source="a", target="b", raw_label="usa (HTTPS)")],
    )


def test_llm_retypes_nodes() -> None:
    def fake_chat(prompt: str) -> str:
        return json.dumps(
            {
                "nodes": {
                    "a": {"c4Type": "Person", "c4Name": "Usuario"},
                    "b": {"c4Type": "Container", "c4Name": "API", "c4Technology": "Python"},
                }
            }
        )

    d = _diagram()
    LLMClassifier(chat=fake_chat).classify(d, 2)
    assert d.node_by_id("a").c4_type is C4Type.PERSON
    assert d.node_by_id("b").c4_type is C4Type.CONTAINER
    assert d.node_by_id("b").c4_technology == "Python"


def test_invalid_type_keeps_heuristic() -> None:
    def fake_chat(prompt: str) -> str:
        return json.dumps({"nodes": {"a": {"c4Type": "Banana"}}})

    d = _diagram()
    LLMClassifier(chat=fake_chat).classify(d, 2)
    # shape=rectangle, nivel 2 -> la heurística da Container; el tipo inválido se ignora.
    assert d.node_by_id("a").c4_type is C4Type.CONTAINER


def test_retry_then_valid() -> None:
    calls = {"n": 0}

    def flaky_chat(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "esto no es json {{"
        return json.dumps({"nodes": {"a": {"c4Type": "Person"}}})

    d = _diagram()
    LLMClassifier(chat=flaky_chat, retries=2).classify(d, 2)
    assert calls["n"] == 2
    assert d.node_by_id("a").c4_type is C4Type.PERSON


def test_does_not_invent_nodes() -> None:
    def fake_chat(prompt: str) -> str:
        return json.dumps(
            {"nodes": {"a": {"c4Type": "Person"}, "ghost": {"c4Type": "Container"}}}
        )

    d = _diagram()
    LLMClassifier(chat=fake_chat).classify(d, 2)
    assert d.node_by_id("ghost") is None
    assert len(d.nodes) == 2


def test_invalid_json_after_retries_raises() -> None:
    d = _diagram()
    with pytest.raises(ValueError, match="inválida tras"):
        LLMClassifier(chat=lambda _p: "{{{", retries=1).classify(d, 2)


def test_llm_requires_key_without_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    d = _diagram()
    with pytest.raises(ValueError, match="C4NORM_LLM_API_KEY"):
        LLMClassifier().classify(d, 2)


def test_auto_falls_back_to_heuristic_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("C4NORM_LLM_API_KEY", raising=False)
    assert isinstance(get_classifier("auto"), HeuristicClassifier)


def test_auto_uses_llm_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("C4NORM_LLM_API_KEY", "x")
    clf = get_classifier("auto")
    assert isinstance(clf, LLMClassifier)
    assert clf.only_low_confidence is True


def test_batching_splits_large_diagrams() -> None:
    """Diagramas con más nodos que batch_size se procesan en varios lotes."""
    call_count = {"n": 0}
    received_ids: list[list[str]] = []

    def fake_chat(prompt: str) -> str:
        call_count["n"] += 1
        import json as _j

        data = _j.loads(prompt.split("NODOS:\n")[1].split("\n\nARISTAS:")[0])
        ids = [n["id"] for n in data]
        received_ids.append(ids)
        return _j.dumps({"nodes": {nid: {"c4Type": "Container"} for nid in ids}})

    nodes = [Node(id=f"n{i}", raw_label=f"Nodo {i}", shape="rectangle") for i in range(5)]
    d = Diagram(name="t", nodes=nodes)
    LLMClassifier(chat=fake_chat, batch_size=2).classify(d, 2)

    assert call_count["n"] == 3  # 5 nodos / lote-2 = 3 llamadas (2+2+1)
    total_ids = [nid for batch in received_ids for nid in batch]
    assert sorted(total_ids) == [f"n{i}" for i in range(5)]


def test_only_low_confidence_skips_explicit_nodes() -> None:
    seen: dict[str, str] = {}

    def fake_chat(prompt: str) -> str:
        seen["prompt"] = prompt
        return json.dumps({"nodes": {}})

    d = Diagram(
        name="t",
        nodes=[
            Node(id="exp", raw_label="X", explicit_c4_type="Person"),
            Node(id="guess", raw_label="Y", shape="rectangle"),
        ],
    )
    LLMClassifier(chat=fake_chat, only_low_confidence=True).classify(d, 2)
    # El prompt solo debe incluir el nodo de baja confianza ('guess'), no el explícito.
    assert '"id": "guess"' in seen["prompt"]
    assert '"id": "exp"' not in seen["prompt"]
