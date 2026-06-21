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


def test_intake_on_milestone_captures_distinct_intermediate_states():
    # @spec REPLAY-SNAP-001 — the intake on_milestone hook snapshots the store AT each milestone, so the
    # timeline holds real intermediate states (waiting -> triaged -> admitted), not just the final one.
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor):
        module.init_state(store)
    rec = replay.ReplayRecorder()
    seqs: list[int] = []

    def capture(action, target, detail):
        actor = replay.actor_for(action)
        line = rec.log(store, "intake", actor, action, target, **detail)
        rec.snapshot(store, line["seq"], float(line["seq"]), action=action, actor=actor, target=target)
        seqs.append(line["seq"])

    orchestrator.run_intake(store, "Jordan Lee", "chest pain", {"spo2": 96}, on_milestone=capture)
    statuses = [
        (s["entities"]["patients"][0]["status"] if s["entities"]["patients"] else None)
        for s in rec.snapshots_for(seqs)
    ]
    assert "waiting" in statuses and "admitted" in statuses  # state genuinely advanced across snapshots
    # More than one distinct state-change frame (else the replay would be a single static image).
    assert len(replay.select_keyframes(rec.timeline, cap=99)) > 2


# --- REPLAY-SNAP-001/002/003: full-state snapshot timeline (data-driven replay, LLD §9.1) ---


def _snapshot_store() -> InMemoryStore:
    store = InMemoryStore()
    store.set("er:patient:p1", {"id": "p1", "name": "Jordan Lee", "status": "waiting"})
    store.set("er:bed:bed1", {"id": "bed1", "status": "available"})
    store.set("er:nurse:nurse1", {"id": "nurse1", "available": True})
    return store


def test_snapshot_captures_all_entities_with_ts():
    # @spec REPLAY-SNAP-001 — every entity record + a real ts; er:events line shape is NOT touched here.
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    snap = rec.snapshot(store, seq=0, ts=1718900000.5, action="record_created", actor="admissions", target="p1")

    assert set(snap) == {"seq", "ts", "action", "actor", "target", "entities"}
    assert snap["ts"] == 1718900000.5
    assert set(snap["entities"]) == {"patients", "beds", "nurses", "doctors", "equipment"}
    assert snap["entities"]["patients"][0]["id"] == "p1"
    assert snap["entities"]["doctors"] == []  # none in the store -> empty list, not missing


def test_snapshot_is_independent_of_later_mutation():
    # @spec REPLAY-SNAP-001 — the captured records are copies, not live references.
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    rec.snapshot(store, seq=0, ts=1.0, action="record_created", actor="admissions", target="p1")
    store.update("er:patient:p1", {"status": "admitted"})
    assert rec.timeline[0]["entities"]["patients"][0]["status"] == "waiting"


def test_snapshot_deep_copies_nested_fields():
    # @spec REPLAY-SNAP-001 — a snapshot is an immutable point-in-time capture: even an in-place mutation
    # of a nested field in the live store must NOT bleed into an already-captured snapshot.
    store = InMemoryStore()
    store.set("er:patient:p1", {"id": "p1", "vitals": {"spo2": 97}, "care_team": ["nurse1"]})
    rec = replay.ReplayRecorder()
    rec.snapshot(store, seq=0, ts=1.0, action="record_created", actor="admissions", target="p1")
    # Mutate the live record's nested objects IN PLACE (not via store.update replacement).
    store._data["er:patient:p1"]["vitals"]["spo2"] = 50
    store._data["er:patient:p1"]["care_team"].append("doc1")
    captured = rec.timeline[0]["entities"]["patients"][0]
    assert captured["vitals"]["spo2"] == 97
    assert captured["care_team"] == ["nurse1"]


def test_snapshot_idempotent_overwrite_by_seq():
    # @spec REPLAY-SNAP-002 — re-capturing the same seq overwrites, never duplicates.
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    rec.snapshot(store, seq=0, ts=1.0, action="record_created", actor="admissions", target="p1")
    store.update("er:patient:p1", {"status": "admitted"})
    rec.snapshot(store, seq=0, ts=2.0, action="bed_assigned", actor="bed", target="p1")

    assert len(rec.timeline) == 1
    assert rec.timeline[0]["ts"] == 2.0
    assert rec.timeline[0]["action"] == "bed_assigned"
    assert rec.timeline[0]["entities"]["patients"][0]["status"] == "admitted"


def test_snapshot_timeline_orders_by_seq():
    # @spec REPLAY-SNAP-001 — timeline + snapshots_for return seq-ordered records regardless of insert order.
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    for seq in (2, 0, 1):
        rec.snapshot(store, seq=seq, ts=float(seq), action=f"a{seq}", actor="orchestrator")
    assert [s["seq"] for s in rec.timeline] == [0, 1, 2]
    assert [s["seq"] for s in rec.snapshots_for([0, 2])] == [0, 2]


def test_log_line_shape_unchanged_by_snapshot_wiring():
    # @spec REPLAY-LOG-002 (guard) — capturing snapshots must NOT alter the er:events line shape and
    # must add no wall-clock field to the published line.
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    line = rec.log(store, "intake", "admissions", "record_created", "p1")
    rec.snapshot(store, seq=line["seq"], ts=1718900000.0, action="record_created", actor="admissions", target="p1")
    published = _published(store)[-1]
    assert set(published) == {"seq", "event", "actor", "action", "target", "detail"}
    assert "ts" not in published and "timestamp" not in published and "time" not in published


class _PublishBoom(InMemoryStore):
    def publish(self, channel: str, msg: str) -> None:
        raise RuntimeError("redis publish down")


class _ReadBoom(InMemoryStore):
    def list_ids(self, entity: str) -> list[str]:
        raise RuntimeError("redis read down")


def test_log_milestone_is_best_effort_on_backend_fault():
    # @spec REPLAY-SNAP-001 (best-effort) — replay capture is additive observation, so a transient
    # backend fault (RedisStore publish/read timeout) must NEVER raise out of the milestone path and
    # abort the live ER command. A publish fault -> no line, nothing appended; a snapshot-read fault ->
    # the line still returns (event feed succeeded), the snapshot is just skipped.
    from er_twin.agents import orchestrator

    orchestrator._replay = replay.ReplayRecorder()
    buf: list[dict] = []
    line = orchestrator._record_milestone(buf, _PublishBoom(), "intake", "admissions", "record_created", "p1")
    assert line is None and buf == []  # publish failed -> skipped, no exception

    orchestrator._replay = replay.ReplayRecorder()
    line2 = orchestrator._log_milestone(_ReadBoom(), "intake", "admissions", "record_created", "p1")
    assert line2 is not None and line2["action"] == "record_created"  # feed line still produced
    assert orchestrator._replay.timeline == []  # snapshot capture skipped on the read fault


def _intake_snapshots() -> list[dict]:
    store = _snapshot_store()
    rec = replay.ReplayRecorder()
    rec.snapshot(store, seq=0, ts=1000.0, action="intake_received", actor="orchestrator", target=None)
    store.update("er:patient:p1", {"status": "admitted", "assigned_bed": "bed1"})
    rec.snapshot(store, seq=1, ts=1006.0, action="bed_assigned", actor="bed", target="bed1")
    rec.snapshot(store, seq=2, ts=1012.0, action="nurse_assigned", actor="nurse", target="nurse1")
    return rec.timeline


def test_export_timeline_writes_file_with_metadata(tmp_path):
    # @spec REPLAY-SNAP-003 @spec REPLAY-LIB-001 — ordered snapshots + derived library metadata.
    out = tmp_path / "out"
    names = {"bed1": "bed-1", "nurse1": "Nurse Maya"}
    record = replay.export_incident_timeline(
        _intake_snapshots(), "patient_intake-0001", "patient_intake",
        "Chest pain intake", "Jordan Lee admitted to bed-1.",
        display=lambda x: names.get(x, x), out_dir=str(out),
    )
    path = out / "replay" / "patient_intake-0001.json"
    assert path.exists()
    on_disk = json.loads(path.read_text())
    assert on_disk == record
    assert record["incident_type"] == "patient_intake"
    assert [s["seq"] for s in record["snapshots"]] == [0, 1, 2]
    assert record["start_ts"] == 1000.0 and record["end_ts"] == 1012.0
    assert record["video_url"] is None
    assert record["speed_factor"] == replay.DEFAULT_SPEED_FACTOR
    # involved = distinct actors+targets (in encounter order) via display(); None target dropped.
    assert record["involved"] == ["orchestrator", "bed", "bed-1", "nurse", "Nurse Maya"]


def test_export_timeline_no_snapshots_writes_nothing(tmp_path):
    # @spec REPLAY-SNAP-003 — no milestones ran -> no empty artifact.
    out = tmp_path / "out"
    result = replay.export_incident_timeline(
        [], "patient_intake-0001", "patient_intake", "t", "s", out_dir=str(out)
    )
    assert result is None
    assert not (out / "replay").exists()


# --- REPLAY-LIB-002: time compression to Pika's allowed durations ---


def test_requested_clip_duration_compresses_and_clamps():
    # @spec REPLAY-LIB-002 — real_elapsed / speed_factor, snapped to {5, 10}.
    assert replay.requested_clip_duration(0.0, 30.0, speed_factor=10) == 5    # 3s -> floor 5
    assert replay.requested_clip_duration(0.0, 90.0, speed_factor=10) == 10   # 9s -> nearest 10
    assert replay.requested_clip_duration(0.0, 600.0, speed_factor=10) == 10  # 60s -> clamp 10
    assert replay.requested_clip_duration(0.0, 70.0, speed_factor=10) == 5    # 7s -> nearest 5
    assert replay.requested_clip_duration(None, None) == 5                    # missing -> min
    assert replay.requested_clip_duration(5.0, 5.0) == 5                      # zero elapsed -> min


# --- REPLAY-KEY-001: keyframe selection (pure, no browser) ---


def _keyframe_snapshots() -> list[dict]:
    # Four snapshots; seq 1 and 2 share identical entities (no state change between them).
    a = {"patients": [{"id": "p1", "status": "waiting"}]}
    b = {"patients": [{"id": "p1", "status": "admitted"}]}
    c = {"patients": [{"id": "p1", "status": "in_treatment"}]}
    return [
        {"seq": 0, "ts": 0.0, "entities": a},
        {"seq": 1, "ts": 1.0, "entities": b},
        {"seq": 2, "ts": 2.0, "entities": b},  # unchanged from seq 1 -> dropped as a state-change frame
        {"seq": 3, "ts": 3.0, "entities": c},
    ]


def test_replay_meta_cli_duration_and_safe_video_url(tmp_path, capsys):
    # @spec REPLAY-LIB-002/003 — the argv helper computes the clamped clip duration and writes video_url
    # WITHOUT interpolating it into Python source, so a URL containing a single quote round-trips exactly
    # (the injection/break the inline `python -c` heredoc was vulnerable to).
    from scripts import replay_meta

    inc = tmp_path / "inc.json"
    inc.write_text(json.dumps({
        "start_ts": 0.0, "end_ts": 90.0, "speed_factor": 10, "video_url": None,
        "snapshots": [{"seq": 0}],
    }), encoding="utf-8")

    assert replay_meta.main(["replay_meta", "duration", str(inc)]) == 0
    assert capsys.readouterr().out.strip() == "10"  # 90/10 = 9 -> nearest allowed (10)

    hostile_url = "https://cdn.test/clip-a'b.mp4"  # embedded single quote
    assert replay_meta.main(["replay_meta", "set-video-url", str(inc), hostile_url]) == 0
    written = json.loads(inc.read_text(encoding="utf-8"))
    assert written["video_url"] == hostile_url  # exact, no injection
    assert written["snapshots"] == [{"seq": 0}]  # rest of the record untouched

    assert replay_meta.main(["replay_meta", "bogus"]) == 2  # unknown command -> nonzero, no crash


def test_select_keyframes_drops_unchanged_then_caps_to_start_end():
    # @spec REPLAY-KEY-001 — state-change snapshots, capped at KEYFRAME_CAP (2) -> start + end.
    snaps = _keyframe_snapshots()
    # No cap: the unchanged seq 2 is dropped, leaving the three state-change frames.
    assert [s["seq"] for s in replay.select_keyframes(snaps, cap=99)] == [0, 1, 3]
    # Verified Pika cap (2): degrade to first + last state-change frame.
    assert [s["seq"] for s in replay.select_keyframes(snaps, cap=replay.KEYFRAME_CAP)] == [0, 3]
    assert replay.KEYFRAME_CAP == 2
    assert replay.select_keyframes([], cap=2) == []
