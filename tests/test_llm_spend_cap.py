"""
Tests del cap de gasto fail-closed del LLMClassifier (HU-ARQ-D1, FinOps).

El LLM es de pago; la unidad de costo es UNA petición ``/chat/completions`` (un
``chat(prompt)``). Estos dientes prueban que, agotado el tope configurado, el
clasificador JAMÁS emite —ni paga— una llamada por encima del cap, y que degrada
de forma audible (nunca silenciosa).

Diente que muerde (rojo-es-rojo): la aserción "el chat inyectado se invocó EXACTAMENTE
``max_calls`` veces" cae si se quita el guard de ``_chat_fn`` (sin cap → 5 invocaciones).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from c4norm.classify import LLMClassifier, LLMSpendCapError
from c4norm.model import C4Type, Diagram, Node

if TYPE_CHECKING:
    from collections.abc import Callable


def _five_node_diagram() -> Diagram:
    # 5 rectángulos de nivel 2 -> la heurística les da Container.
    return Diagram(
        name="t",
        nodes=[Node(id=f"n{i}", raw_label=f"Nodo {i}", shape="rectangle") for i in range(5)],
    )


def _counting_chat() -> tuple[list[int], Callable[[str], str]]:
    """Devuelve (contador, chat). El chat re-tipa a Person todo id que reciba."""
    calls = [0]

    def chat(prompt: str) -> str:
        calls[0] += 1
        data = json.loads(prompt.split("NODOS:\n")[1].split("\n\nARISTAS:")[0])
        ids = [n["id"] for n in data]
        return json.dumps({"nodes": {nid: {"c4Type": "Person"} for nid in ids}})

    return calls, chat


def test_default_cap_is_finite() -> None:
    """El cap default es FINITO (nunca ilimitado, aunque el operador lo olvide)."""
    clf = LLMClassifier(chat=lambda _p: "{}")
    assert clf.max_calls == 64
    assert clf.on_cap == "fail"


def test_cap_fail_mode_never_pays_beyond_limit() -> None:
    """on_cap='fail': lanza al agotarse y el chat NUNCA se invoca más de max_calls."""
    calls, chat = _counting_chat()
    d = _five_node_diagram()
    # batch_size=1 -> 5 lotes; max_parallel=1 -> orden determinista; cap=2.
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=1, max_calls=2)

    with pytest.raises(LLMSpendCapError) as exc_info:
        clf.classify(d, 2)

    assert exc_info.value.max_calls == 2
    # DIENTE: jamás se paga por encima del cap. Sin guard, esto sería 5.
    assert calls[0] == 2


def test_cap_degrade_mode_keeps_heuristic_audibly() -> None:
    """on_cap='degrade': sin excepción, conserva heurística y avisa (nunca silencioso)."""
    calls, chat = _counting_chat()
    d = _five_node_diagram()
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=1, max_calls=2, on_cap="degrade")

    with pytest.warns(UserWarning, match="heurística"):
        clf.classify(d, 2)

    # No pagó de más...
    assert calls[0] == 2
    # ...y NINGÚN nodo quedó re-tipado a Person: se conserva la heurística (Container).
    for node in d.nodes:
        assert node.c4_type is C4Type.CONTAINER


def test_under_cap_applies_retyping_no_regression() -> None:
    """Bajo el cap, el re-tipado se aplica normalmente (sin regresión)."""
    calls, chat = _counting_chat()
    d = _five_node_diagram()
    clf = LLMClassifier(chat=chat, batch_size=2, max_parallel=1, max_calls=100)

    clf.classify(d, 2)

    assert calls[0] == 3  # 5 nodos / lote-2 = 3 llamadas, todas bajo el cap
    for node in d.nodes:
        assert node.c4_type is C4Type.PERSON


def test_budget_resets_between_runs() -> None:
    """El contador se reinicia por corrida: dos classify() consecutivos no se acumulan."""
    calls, chat = _counting_chat()
    clf = LLMClassifier(chat=chat, batch_size=2, max_parallel=1, max_calls=100)

    clf.classify(_five_node_diagram(), 2)  # 3 llamadas
    clf.classify(_five_node_diagram(), 2)  # otras 3, sin arrastrar el conteo previo

    assert calls[0] == 6


def test_invalid_on_cap_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="C4NORM_LLM_ON_CAP"):
        LLMClassifier(chat=lambda _p: "{}", on_cap="ignore")


def test_env_configures_cap_and_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("C4NORM_LLM_MAX_CALLS", "1")
    monkeypatch.setenv("C4NORM_LLM_ON_CAP", "degrade")
    calls, chat = _counting_chat()
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=1)
    assert clf.max_calls == 1
    assert clf.on_cap == "degrade"

    with pytest.warns(UserWarning):
        clf.classify(_five_node_diagram(), 2)
    assert calls[0] == 1


@pytest.mark.parametrize("raw", ["abc", "", "  ", "12.5", "1e3", "0x40"])
def test_malformed_max_calls_falls_back_to_default(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """La lectura malformada de C4NORM_LLM_MAX_CALLS NUNCA deja el cap sin definir:
    ``int()`` falla y ``_env_int`` cae al default finito 64 (fail-closed por defecto).
    """
    monkeypatch.setenv("C4NORM_LLM_MAX_CALLS", raw)
    clf = LLMClassifier(chat=lambda _p: "{}")
    assert clf.max_calls == 64


@pytest.mark.parametrize("raw", ["0", "-1", "-100"])
def test_nonpositive_max_calls_blocks_all_paid_calls(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """C4NORM_LLM_MAX_CALLS<=0 se parsea literalmente -> el guard (``>= max_calls``)
    dispara en el PRIMER lote -> bloqueo TOTAL: ni una sola llamada pagada.
    """
    calls, chat = _counting_chat()
    monkeypatch.setenv("C4NORM_LLM_MAX_CALLS", raw)
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=1)

    with pytest.raises(LLMSpendCapError):
        clf.classify(_five_node_diagram(), 2)

    # DIENTE: bloqueo TOTAL, jamás se paga una sola llamada. Sin el guard
    # ``_calls_made >= max_calls`` disparando ANTES del primer chat(), esto
    # pagaría >=1 llamada (hasta 5, una por lote).
    assert calls[0] == 0
