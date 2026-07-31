"""
Tests para la tanda de rendimiento de la auditoría:
  - Paralelización de lotes del LLM (ThreadPoolExecutor)
  - Configuración por entorno: batch_size, timeout, max_parallel
  - Correctitud: la paralelización no pierde ni duplica nodos
  - Latencia real de CLI y API (RNF-003: CLI <5s, API <2s) contra fixture real
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

from c4norm.classify import LLMClassifier
from c4norm.model import C4Type, Diagram, Node


def _nodes(n: int) -> list[Node]:
    return [Node(id=f"n{i}", raw_label=f"Nodo {i}", shape="rectangle") for i in range(n)]


def test_batches_run_in_parallel() -> None:
    """Con varios lotes, las llamadas al LLM se solapan en el tiempo (no secuenciales)."""
    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow_chat(prompt: str) -> str:
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.15)
        with lock:
            active["now"] -= 1
        ids = [n["id"] for n in json.loads(prompt.split("NODOS:\n")[1].split("\n\n")[0])]
        return json.dumps({"nodes": {nid: {"c4Type": "Container"} for nid in ids}})

    d = Diagram(name="t", nodes=_nodes(9))  # 9 nodos, batch_size=3 → 3 lotes
    LLMClassifier(chat=slow_chat, batch_size=3, max_parallel=3).classify(d, 2)

    # Si fuera secuencial, max concurrencia sería 1. Con paralelización, >1.
    assert active["max"] >= 2, f"Concurrencia máxima observada: {active['max']} (esperado ≥2)"


def test_parallel_batches_no_node_loss() -> None:
    """La paralelización combina todos los lotes sin perder ni duplicar nodos."""
    seen_ids: list[str] = []
    lock = threading.Lock()

    def chat(prompt: str) -> str:
        ids = [n["id"] for n in json.loads(prompt.split("NODOS:\n")[1].split("\n\n")[0])]
        with lock:
            seen_ids.extend(ids)
        return json.dumps({"nodes": {nid: {"c4Type": "Component"} for nid in ids}})

    d = Diagram(name="t", nodes=_nodes(25))  # 25 nodos, batch_size=10 → 3 lotes (10+10+5)
    LLMClassifier(chat=chat, batch_size=10, max_parallel=4).classify(d, 3)

    assert sorted(seen_ids) == sorted(f"n{i}" for i in range(25))
    # Todos re-tipados a Component
    for node in d.nodes:
        assert node.c4_type is C4Type.COMPONENT


def test_max_parallel_caps_concurrency() -> None:
    """max_parallel limita cuántos lotes corren a la vez."""
    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow_chat(prompt: str) -> str:
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.1)
        with lock:
            active["now"] -= 1
        ids = [n["id"] for n in json.loads(prompt.split("NODOS:\n")[1].split("\n\n")[0])]
        return json.dumps({"nodes": {nid: {} for nid in ids}})

    d = Diagram(name="t", nodes=_nodes(20))  # batch_size=2 → 10 lotes, max_parallel=2
    LLMClassifier(chat=slow_chat, batch_size=2, max_parallel=2).classify(d, 2)
    assert active["max"] <= 2, f"max_parallel=2 pero se observaron {active['max']} simultáneos"


def test_single_batch_does_not_use_pool() -> None:
    """Diagramas pequeños (≤ batch_size) usan una sola llamada, sin pool."""
    calls = {"n": 0}

    def chat(prompt: str) -> str:
        calls["n"] += 1
        ids = [n["id"] for n in json.loads(prompt.split("NODOS:\n")[1].split("\n\n")[0])]
        return json.dumps({"nodes": {nid: {} for nid in ids}})

    d = Diagram(name="t", nodes=_nodes(5))  # 5 ≤ batch_size 20
    LLMClassifier(chat=chat, batch_size=20).classify(d, 2)
    assert calls["n"] == 1


# =============================================================================
# Config por entorno
# =============================================================================

def test_llm_reads_env_config(monkeypatch) -> None:
    monkeypatch.setenv("C4NORM_LLM_BATCH_SIZE", "7")
    monkeypatch.setenv("C4NORM_LLM_TIMEOUT", "45")
    monkeypatch.setenv("C4NORM_LLM_MAX_PARALLEL", "2")
    clf = LLMClassifier()
    assert clf.batch_size == 7
    assert clf.timeout == 45
    assert clf.max_parallel == 2


def test_llm_env_config_invalid_falls_back(monkeypatch) -> None:
    """Valores no numéricos en entorno caen al default sin romper."""
    monkeypatch.setenv("C4NORM_LLM_BATCH_SIZE", "no-es-numero")
    clf = LLMClassifier()
    assert clf.batch_size == 20


def test_vision_reads_env_timeout(monkeypatch) -> None:
    from c4norm.vision import VisionExtractor

    monkeypatch.setenv("C4NORM_VISION_TIMEOUT", "30")
    ext = VisionExtractor()
    assert ext.timeout == 30


def test_explicit_args_override_env(monkeypatch) -> None:
    monkeypatch.setenv("C4NORM_LLM_BATCH_SIZE", "7")
    clf = LLMClassifier(batch_size=50)
    assert clf.batch_size == 50  # el argumento explícito gana sobre el entorno


# =============================================================================
# RNF-003: Performance — CLI <5s, API <2s (diagrama simple, sin LLM/red)
# =============================================================================

_FIXTURE_SIMPLE = Path(__file__).parent / "fixtures" / "crudo_ia_2_simple.drawio.xml"


def test_cli_latency() -> None:
    """`python -m c4norm <crudo> -o <salida>` sobre un diagrama simple tarda <5s."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out_perf_cli.drawio.xml"
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "c4norm", str(_FIXTURE_SIMPLE), "--level", "2", "-o", str(out_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        elapsed = time.perf_counter() - start

        assert result.returncode == 0, f"CLI falló: stderr={result.stderr}"
        assert out_path.is_file()
        assert elapsed < 5.0, f"CLI tardó {elapsed:.3f}s (esperado <5s)"


def test_api_latency() -> None:
    """POST /api/v1/diagram/normalize sobre un diagrama simple tarda <2s (sin LLM)."""
    from fastapi.testclient import TestClient

    from api.main import _clear_rate_limit_state, app

    _clear_rate_limit_state()
    client = TestClient(app)
    raw_xml = _FIXTURE_SIMPLE.read_text(encoding="utf-8")

    start = time.perf_counter()
    response = client.post("/api/v1/diagram/normalize", json={"xml_content": raw_xml, "c4_level": 2})
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, f"API falló: {response.text}"
    assert elapsed < 2.0, f"API tardó {elapsed:.3f}s (esperado <2s)"
