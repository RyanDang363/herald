"""Phase 5 — Event 3: Status Summary (SUMM-*).

The status summary is **read-only and synchronous** (LLD §7 / decision R2-F): the Orchestrator reads
the shared store directly and renders a deterministic, state-derived template — no async messaging, no
state mutation. So the whole event is a single pure function (`orchestrator.build_status_summary`)
plus a thin synchronous chat branch; these tests drive the pure function against an `InMemoryStore`.

`build_status_summary(store, active_o2_alert_beds)` takes the in-flight O2-alert beds as a parameter
(the chat branch computes them from `oxygen_flows`/`in_flight_o2_dispatches`), so the O2-alert line is
unit-testable by injecting a list — no live oxygen flow needed. Each test traces to an EARS spec id.
"""

import copy

from er_twin import main
from er_twin.agents import bed, doctor, equipment, nurse, orchestrator, patient
from er_twin.storage import InMemoryStore


def _baseline_store() -> InMemoryStore:
    """Clean seed + the mid-shift demo baseline (reproduces the R2-F reconciliation numbers)."""
    store = InMemoryStore()
    main.seed_state(store)
    main.seed_baseline(store)
    return store


def _clean_store() -> InMemoryStore:
    """Clean inventory only — no patients admitted, all beds available (empty-ER fixture)."""
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor, equipment):
        module.init_state(store)
    return store


# --- SUMM-FLOW-001/002: state-derived counts + alert/urgent lines (R2-F reconciliation) ---


def test_summary_baseline_string():
    # @spec SUMM-FLOW-001
    # @spec SUMM-FLOW-002
    store = _baseline_store()
    assert orchestrator.build_status_summary(store, []) == (
        "2 patients active, 1 bed occupied, 1 nurse free. No critical alerts."
    )


def test_summary_after_intake_string():
    # @spec SUMM-FLOW-002 — counts update + "Most urgent" line after admitting Jordan Lee.
    store = _baseline_store()
    orchestrator.run_intake(store, "Jordan Lee", "chest pain", {"spo2": 96, "heart_rate": 112})
    assert orchestrator.build_status_summary(store, []) == (
        "3 patients active, 2 beds occupied, 0 nurse(s) free. Most urgent: Jordan Lee (ESI-2)."
    )


# --- SUMM-ERR-001: empty ER ---


def test_summary_empty_er():
    # @spec SUMM-ERR-001
    store = _clean_store()
    assert orchestrator.build_status_summary(store, []) == (
        "Nothing currently happening in the ER — no active patients, "
        "no occupied beds, and no critical alerts."
    )


# --- SUMM-FLOW-002: active-O2-alert line (injected list — no live flow needed) ---


def test_summary_active_o2_alert_line():
    # @spec SUMM-FLOW-002 — names the bed via the display map; replaces the "no alerts" all-clear.
    store = _baseline_store()
    summary = orchestrator.build_status_summary(store, ["bed3"])
    assert "1 active O2 alert on bed-3." in summary
    assert "No critical alerts." not in summary


def test_summary_multiple_o2_alerts_pluralized():
    # @spec SUMM-FLOW-002 — pluralize + name every alerting bed.
    store = _baseline_store()
    summary = orchestrator.build_status_summary(store, ["bed3", "bed4"])
    assert "2 active O2 alerts on bed-3, bed-4." in summary


# --- SUMM-FLOW-002: "Most urgent" selection (lowest acuity, tie-break by id ascending) ---


def test_summary_most_urgent_lowest_acuity_then_id():
    # @spec SUMM-FLOW-002
    store = _clean_store()
    store.set("er:patient:p1", {"id": "p1", "name": "Alice", "acuity": 2, "status": "admitted"})
    store.set("er:patient:p2", {"id": "p2", "name": "Bob", "acuity": 1, "status": "admitted"})
    store.set("er:patient:p3", {"id": "p3", "name": "Cara", "acuity": 1, "status": "waiting"})
    store.update("er:bed:bed1", {"status": "occupied", "occupied_by": "p1"})
    # lowest acuity is 1 (p2 and p3 tie); id ascending -> p2 "Bob".
    assert "Most urgent: Bob (ESI-1)." in orchestrator.build_status_summary(store, [])


def test_summary_no_urgent_line_when_all_low_acuity():
    # @spec SUMM-FLOW-002 — no active patient with acuity <= 2 -> no "Most urgent" line.
    store = _baseline_store()  # p1 ESI-4, p2 ESI-3
    summary = orchestrator.build_status_summary(store, [])
    assert "Most urgent" not in summary


# --- SUMM-STATE-001: producing a summary mutates nothing ---


def test_summary_does_not_mutate_state():
    # @spec SUMM-STATE-001
    store = _baseline_store()
    before = copy.deepcopy(store._data)
    orchestrator.build_status_summary(store, ["bed3"])
    assert store._data == before
