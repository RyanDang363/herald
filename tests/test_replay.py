"""Phase R — Incident Replay Bridge (REPLAY-*).

The replay layer is the own-surface boundary to Pika MCP (LLD §9): the Orchestrator publishes one
structured JSON line per milestone to the `er:events` channel (`ReplayRecorder`), and `replay.py`
derives an `out/incident_replay_brief.json` + `out/pika_prompt.md` from those lines after an event
completes. Everything here is pure / file-IO and unit-tested directly against an `InMemoryStore` and
a `tmp_path` out dir — no live Bureau. Each test traces to an EARS spec id.
"""

import json

from er_twin import replay
from er_twin.agents import bed, doctor, nurse, orchestrator, patient
from er_twin.storage import InMemoryStore


def _published(store: InMemoryStore) -> list[dict]:
    """Parse the JSON lines the recorder published to the `er:events` channel."""
    return [json.loads(m) for m in store._channels.get("er:events", [])]


# --- REPLAY-LOG-001/002: structured, seq-ordered, wall-clock-free event lines ---


def test_recorder_publishes_seq_ordered_structured_lines():
    # @spec REPLAY-LOG-001
    # @spec REPLAY-LOG-002
    store = InMemoryStore()
    rec = replay.ReplayRecorder()
    a = rec.log(store, "intake", "admissions", "record_created", "p1")
    b = rec.log(store, "intake", "triage", "triaged", "p1", acuity=2, specialty="cardiology")

    assert a["seq"] == 0 and b["seq"] == 1  # monotonic, starts at 0
    lines = _published(store)
    assert [ln["seq"] for ln in lines] == [0, 1]
    assert set(lines[0]) == {"seq", "event", "actor", "action", "target", "detail"}
    assert lines[1]["detail"] == {"acuity": 2, "specialty": "cardiology"}
    # No wall-clock field anywhere in the trace.
    assert all("timestamp" not in ln and "time" not in ln for ln in lines)


def test_incident_id_counts_per_type():
    # @spec REPLAY-BRIEF-004 — incident_type mapping + per-type 4-digit counter.
    rec = replay.ReplayRecorder()
    assert rec.next_incident_id("intake") == "patient_intake-0001"
    assert rec.next_incident_id("intake") == "patient_intake-0002"
    assert rec.next_incident_id("oxygen") == "low_oxygen_alert-0001"
    assert rec.next_incident_id("summary") == "er_status_summary-0001"


# --- REPLAY-BRIEF-001/004: brief derivation (timeline ordering, severity, synthetic patient) ---


def _intake_store() -> InMemoryStore:
    store = InMemoryStore()
    store.set("er:patient:p1", {
        "id": "p1", "name": "Jordan Lee", "chief_complaint": "chest pain", "acuity": 2,
        "specialty": "cardiology", "status": "admitted", "assigned_bed": "bed1",
        "care_team": ["nurse1", "doc1"], "vitals": {"spo2": 96},
    })
    return store


def _intake_lines() -> list[dict]:
    # Deliberately out of seq order to prove build_brief sorts by seq (REPLAY-LOG-002).
    return [
        {"seq": 2, "event": "intake", "actor": "triage", "action": "triaged", "target": "p1",
         "detail": {"acuity": 2, "specialty": "cardiology"}},
        {"seq": 0, "event": "intake", "actor": "orchestrator", "action": "intake_received",
         "target": None, "detail": {"detail": "chest pain"}},
        {"seq": 1, "event": "intake", "actor": "admissions", "action": "record_created",
         "target": "p1", "detail": {}},
        {"seq": 3, "event": "intake", "actor": "orchestrator", "action": "intake_complete",
         "target": "p1", "detail": {}},
    ]


def test_build_brief_shape_and_derivation():
    # @spec REPLAY-BRIEF-001
    # @spec REPLAY-BRIEF-004
    brief = replay.build_brief(_intake_lines(), "patient_intake-0001", "patient_intake", _intake_store())

    assert brief["incident_id"] == "patient_intake-0001"
    assert brief["incident_type"] == "patient_intake"  # one of the three event types
    assert brief["severity"] == "high"  # acuity 2 -> high (R2-H)
    assert brief["patient"] == {"id": "p1", "condition": "synthetic chest pain", "acuity": 2}
    assert brief["location"] == "ER bed-1"
    assert brief["visual_style"] == replay.VISUAL_STYLE["patient_intake"]
    assert brief["pika_outputs_requested"]  # non-empty
    # timeline sorted by seq, t derived from (relative) seq, every required field present
    seqs_in_order = [ln["seq"] for ln in sorted(_intake_lines(), key=lambda x: x["seq"])]
    assert seqs_in_order == [0, 1, 2, 3]
    assert [e["t"] for e in brief["timeline"]] == ["00:00", "00:05", "00:10", "00:15"]
    assert brief["timeline"][0]["action"] == "intake_received"
    assert all({"t", "actor", "action", "target", "state_change"} <= set(e) for e in brief["timeline"])


def test_severity_from_acuity_mapping():
    # @spec REPLAY-BRIEF-001 — R2-H severity scale.
    assert replay.severity_from_acuity(1) == "critical"
    assert replay.severity_from_acuity(2) == "high"
    assert replay.severity_from_acuity(3) == "medium"
    assert replay.severity_from_acuity(4) == "low"
    assert replay.severity_from_acuity(5) == "low"


def test_summary_brief_has_no_patient():
    # @spec REPLAY-BRIEF-004 — er_status_summary maps with no specific patient.
    lines = [{"seq": 0, "event": "summary", "actor": "orchestrator", "action": "summary_generated",
              "target": None, "detail": {"text": "2 patients active, 1 bed occupied, 1 nurse free."}}]
    brief = replay.build_brief(lines, "er_status_summary-0001", "er_status_summary", InMemoryStore())
    assert brief["incident_type"] == "er_status_summary"
    assert brief["patient"] is None
    assert "2 patients active" in brief["summary"]


# --- REPLAY-BRIEF-001/002/003: export to files ---


def test_export_writes_brief_prompt_and_history(tmp_path):
    # @spec REPLAY-BRIEF-001
    # @spec REPLAY-BRIEF-002
    out = tmp_path / "out"
    brief = replay.export_incident(
        _intake_lines(), "patient_intake-0001", "patient_intake", _intake_store(), out_dir=str(out)
    )
    assert brief is not None
    history = out / "patient_intake-0001.json"
    latest = out / "incident_replay_brief.json"
    prompt = out / "pika_prompt.md"
    assert history.exists() and latest.exists() and prompt.exists()
    # latest is a copy of the per-incident history file
    assert json.loads(history.read_text()) == json.loads(latest.read_text())
    # prompt carries the synthetic-data/safety + return contract (REPLAY-BRIEF-002)
    text = prompt.read_text().lower()
    assert "synthetic" in text and "no real" in text
    assert "task_id" in text and "autonomous" in text


def test_export_no_lines_writes_nothing(tmp_path):
    # @spec REPLAY-BRIEF-003 — no event ran -> no empty artifacts.
    out = tmp_path / "out"
    result = replay.export_incident([], "patient_intake-0001", "patient_intake", InMemoryStore(), out_dir=str(out))
    assert result is None
    assert not out.exists() or not any(out.iterdir())


# --- Integration: the real intake milestone set publishes + exports cleanly (no live Bureau) ---


def test_intake_milestones_map_to_a_coherent_brief(tmp_path):
    # @spec REPLAY-LOG-001 — exercises the exact milestone -> er:events line mapping the Orchestrator's
    # intake branch performs (incl. the nested `detail` kwarg), then the brief export.
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor):
        module.init_state(store)
    outcome = orchestrator.run_intake(store, "Jordan Lee", "chest pain", {"spo2": 96, "heart_rate": 112})

    rec = replay.ReplayRecorder()
    lines = [
        rec.log(store, "intake", replay.actor_for(m["action"]), m["action"], m["target"], **m["detail"])
        for m in outcome["milestones"]
    ]
    out = tmp_path / "out"
    brief = replay.export_incident(lines, rec.next_incident_id("intake"), "patient_intake", store, out_dir=str(out))

    assert brief["incident_id"] == "patient_intake-0001"
    assert brief["severity"] == "high"  # ESI-2
    assert brief["patient"]["id"] == "p1"
    assert brief["timeline"][0]["action"] == "intake_received"
    assert any(e["action"] == "intake_complete" for e in brief["timeline"])
    assert (out / "incident_replay_brief.json").exists() and (out / "pika_prompt.md").exists()
