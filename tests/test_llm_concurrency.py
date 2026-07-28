"""
Test de concurrencia REAL del cap de gasto LLM (HU-QA-D02, feedback líder-qa-transversal
sobre G-18 / HU-ARQ-D1, 2026-07-28).

``tests/test_llm_spend_cap.py`` prueba la garantía fail-closed con ``max_parallel=1``,
lo que fuerza la serialización de los lotes y por lo tanto JAMÁS ejercita el
``ThreadPoolExecutor`` real de ``LLMClassifier._ask_batched`` bajo el guard de
``_chat_fn``. El lock (``threading.Lock``) puede ser correcto en el papel y ese hecho
seguiría sin verificarse. Aquí se fuerza contención real: ``batch_size`` chico +
``max_parallel>1`` sobre suficientes nodos para que ``_ask_batched`` cree un pool con
varios workers ejecutando ``_ask`` (y por tanto el guard) EN PARALELO de verdad.

Diente que muerde (rojo-es-rojo, ver ``test_mutation_proof_lock_removal_causes_overpay``):
si alguien reemplaza el ``threading.Lock`` real por un candado que no serializa
check-and-increment, bajo esta misma contención el conteo de llamadas pagadas SUPERA
``max_calls`` — la garantía "jamás se paga de más" deja de sostenerse. Los tests 1-6
de este archivo corren contra el ``LLMClassifier`` real: si alguna vez empiezan a
fallar de forma esporádica (no determinista), es señal de que el guard real dejó de
ser atómico.
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

import pytest

from c4norm.classify import LLMClassifier, LLMSpendCapError
from c4norm.model import C4Type, Diagram, Node

if TYPE_CHECKING:
    from collections.abc import Callable


def _node_diagram(n: int) -> Diagram:
    """``n`` rectángulos de nivel 2 -> la heurística les da Container a todos."""
    return Diagram(
        name="t",
        nodes=[Node(id=f"n{i}", raw_label=f"Nodo {i}", shape="rectangle") for i in range(n)],
    )


def _counting_chat(delay: float = 0.0) -> tuple[list[int], Callable[[str], str]]:
    """chat que re-tipa a Person y cuenta invocaciones de forma thread-safe.

    El conteo usa SU PROPIO lock (independiente del ``_budget_lock`` del clasificador
    bajo prueba) para que una carrera en la instrumentación del test nunca se confunda
    con una carrera real del guard.
    """
    calls = [0]
    lock = threading.Lock()

    def chat(prompt: str) -> str:
        if delay:
            time.sleep(delay)
        with lock:
            calls[0] += 1
        data = json.loads(prompt.split("NODOS:\n")[1].split("\n\nARISTAS:")[0])
        ids = [n["id"] for n in data]
        return json.dumps({"nodes": {nid: {"c4Type": "Person"} for nid in ids}})

    return calls, chat


# -- Test 1: bajo contención real, el conteo es EXACTO (ni de más, ni de menos) -------


@pytest.mark.parametrize(
    ("n_nodes", "batch_size", "max_parallel", "max_calls"),
    [
        (200, 1, 16, 50),  # muchos lotes chicos, alta paralelización
        (100, 2, 8, 30),  # lotes de 2, paralelización media
        (64, 4, 4, 10),  # cap bajo, pocos workers
        (40, 1, 32, 40),  # cap == total de lotes exactamente (el borde: no debe disparar)
    ],
)
def test_concurrent_cap_exact_call_count(
    n_nodes: int, batch_size: int, max_parallel: int, max_calls: int
) -> None:
    """Bajo ThreadPoolExecutor real (max_parallel>1), el guard sigue siendo exacto.

    DIENTE: sin lock atómico, la carrera entre check e incremento haría que el
    conteo final rebase ``max_calls`` (o, con menos frecuencia, se quede corto por
    doble-conteo perdido). Con el lock real, ambos casos (bajo el cap y sobre el
    cap) dan un número EXACTO y determinista pese a la concurrencia real.
    """
    calls, chat = _counting_chat(delay=0.002)
    d = _node_diagram(n_nodes)
    clf = LLMClassifier(chat=chat, batch_size=batch_size, max_parallel=max_parallel, max_calls=max_calls)

    n_chunks = -(-n_nodes // batch_size)  # ceil
    if n_chunks <= max_calls:
        clf.classify(d, 2)
        assert calls[0] == n_chunks
    else:
        with pytest.raises(LLMSpendCapError):
            clf.classify(d, 2)
        assert calls[0] == max_calls


# -- Test 2: fail-closed, repetido muchas veces bajo contención real -> nunca sobrepaga -


def test_concurrent_fail_closed_never_overpays_repeated_trials() -> None:
    """Repite la corrida bajo contención real muchas veces: JAMÁS paga de más.

    Una sola corrida verde no descarta una carrera esporádica; repetir el escenario
    (distinta instancia, distinto chat cada vez) sube la confianza de que el guard
    real es atómico y no solo "tuvo suerte" con el scheduling del hilo.
    """
    for _ in range(15):
        calls, chat = _counting_chat()
        d = _node_diagram(80)
        clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=12, max_calls=25)
        with pytest.raises(LLMSpendCapError):
            clf.classify(d, 2)
        assert calls[0] == 25


# -- Test 3: on_cap='degrade' bajo contención real -> no sobrepaga y avisa audible ------


def test_concurrent_degrade_mode_no_overpay_and_warns() -> None:
    """degrade bajo contención real: cap respetado, warning audible, heurística intacta."""
    calls, chat = _counting_chat(delay=0.001)
    d = _node_diagram(60)
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=10, max_calls=20, on_cap="degrade")

    with pytest.warns(UserWarning, match="heurística"):
        clf.classify(d, 2)

    assert calls[0] == 20
    # Ningún nodo debería quedar re-tipado a Person: se conserva la heurística.
    for node in d.nodes:
        assert node.c4_type is C4Type.CONTAINER


# -- Test 4: el presupuesto se reinicia entre corridas, cada una con contención real ----


def test_concurrent_budget_resets_between_runs() -> None:
    """Dos classify() consecutivos, cada uno con contención real, no arrastran conteo."""
    calls, chat = _counting_chat(delay=0.001)
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=10, max_calls=15)

    with pytest.raises(LLMSpendCapError):
        clf.classify(_node_diagram(50), 2)
    assert calls[0] == 15

    with pytest.raises(LLMSpendCapError):
        clf.classify(_node_diagram(50), 2)
    assert calls[0] == 30  # otras 15 nuevas, no acumuladas con la corrida anterior


# -- Test 5: edge case — más workers que lotes disponibles -----------------------------


def test_concurrent_more_workers_than_chunks() -> None:
    """max_parallel muy superior al número de lotes: el guard sigue siendo exacto."""
    calls, chat = _counting_chat()
    d = _node_diagram(5)
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=50, max_calls=3)

    with pytest.raises(LLMSpendCapError):
        clf.classify(d, 2)
    assert calls[0] == 3


# -- Test 6: edge case — latencia desigual entre threads ("gap entre threads") ----------


def test_concurrent_uneven_latency_still_exact() -> None:
    """Threads con latencia desigual (algunos lentos, otros rápidos) no rompen el cap.

    Simula lotes con tiempos de respuesta distintos del proveedor LLM real: sin esto,
    una prueba con latencia uniforme podría no exponer una carrera que solo aparece
    cuando los hilos terminan en órdenes desincronizados.
    """
    counter = [0]
    counter_lock = threading.Lock()
    calls = [0]
    calls_lock = threading.Lock()

    def chat(prompt: str) -> str:
        with counter_lock:
            counter[0] += 1
            n = counter[0]
        time.sleep(0.005 if n % 3 == 0 else 0.0005)  # cada 3ra llamada es "lenta"
        with calls_lock:
            calls[0] += 1
        data = json.loads(prompt.split("NODOS:\n")[1].split("\n\nARISTAS:")[0])
        ids = [nd["id"] for nd in data]
        return json.dumps({"nodes": {nid: {"c4Type": "Person"} for nid in ids}})

    d = _node_diagram(90)
    clf = LLMClassifier(chat=chat, batch_size=1, max_parallel=15, max_calls=35)
    with pytest.raises(LLMSpendCapError):
        clf.classify(d, 2)
    assert calls[0] == 35


# -- Test 7 (mutation-proof): sin el lock, la contención real SÍ rompe el cap ----------


class _NoLockGuardMutant(LLMClassifier):
    """Mutante deliberado: reproduce el guard check-then-increment SIN el lock.

    Existe solo para demostrar rojo-es-rojo: si alguien quita o rompe el
    ``threading.Lock`` de ``LLMClassifier._chat_fn`` en ``c4norm/classify.py``, ESTA
    prueba (ejercitando el mismo patrón, a propósito desprotegido) debe fallar, y las
    de arriba (contra la clase real) deben seguir pasando. El ``time.sleep`` entre el
    check y el incremento ensancha la ventana de carrera a propósito: libera el GIL y
    garantiza que otro hilo pueda colarse entre "leer el contador" y "escribirlo",
    para que el bug se manifieste de forma confiable en cualquier máquina, no solo
    quizás bajo un scheduling desfavorable.

    Nota honesta de verificación manual: quitar el lock de la instancia REAL
    (``clf._budget_lock = <candado nulo>``, sin el ``time.sleep`` de este mutante)
    y correrlo bajo la misma contención NO reprodujo el sobrepago en 40 corridas
    seguidas (150 nodos, 32 workers, ``sys.setswitchinterval`` casi a cero incluido).
    Bajo CPython/GIL, el bloque "leer contador -> comparar -> incrementar" es tan
    pocas instrucciones que rara vez se interrumpe a media ejecución sin algo que
    ceda el GIL explícitamente (I/O, ``sleep``, adquisición de otro lock). Eso NO
    significa que el guard sin lock sea seguro — sigue siendo una carrera de libro
    de texto (check-then-act sin atomicidad) — solo que reproducirla de forma
    determinista en un test requiere ensanchar la ventana a propósito, que es
    justamente lo que hace este mutante con el ``sleep``.
    """

    def _chat_fn(self) -> Callable[[str], str]:
        base = self._base_chat_fn()

        def unguarded(prompt: str) -> str:
            if self._calls_made >= self.max_calls:
                raise LLMSpendCapError(self.max_calls)
            time.sleep(0.001)  # ventana de carrera forzada (sin lock)
            self._calls_made += 1
            return base(prompt)

        return unguarded


def test_mutation_proof_lock_removal_causes_overpay() -> None:
    """Rojo-es-rojo: neutralizado el lock, la contención real SÍ rebasa el cap.

    Esta es la prueba de que los tests 1-6 son capaces de morder: contra el guard
    real (con lock) siempre dan ``calls == max_calls`` exacto; contra este mutante
    (mismo patrón, sin lock) el conteo se va por encima del cap bajo la misma
    contención real. Si esta aserción alguna vez empezara a fallar (es decir, el
    mutante dejara de sobrepagar), sería señal de que el entorno serializó los
    hilos por completo y el ensanchamiento de la ventana de carrera dejó de ser
    suficiente — no de que el guard real se haya vuelto más seguro.
    """
    calls, chat = _counting_chat()
    d = _node_diagram(60)
    mutant = _NoLockGuardMutant(chat=chat, batch_size=1, max_parallel=16, max_calls=20)

    # El mutante puede o no lanzar LLMSpendCapError (depende de en qué orden terminan
    # los hilos), pero en cualquier caso debe haber pagado MÁS de max_calls llamadas:
    # esa es la garantía que se rompe sin el lock.
    with pytest.raises(LLMSpendCapError):
        mutant.classify(d, 2)

    assert calls[0] > 20, (
        f"el mutante sin lock debería sobrepagar bajo contención real, pero calls={calls[0]} "
        "(el fixture de contención dejó de ensanchar la ventana de carrera; sube n_nodes/max_parallel)"
    )
