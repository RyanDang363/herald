"""Incident replay bridge — the own-surface boundary to Pika MCP (LLD §9).

The Fetch runtime never calls Pika. Instead the Orchestrator publishes one structured JSON line per
**milestone** to the `er:events` channel (`ReplayRecorder`), and this module derives a creative brief
from those lines after an event completes:

    er:events lines  --build_brief-->  incident dict  --write_incident-->  out/{incident_id}.json
                                                                            out/incident_replay_brief.json (latest)
                                                                            out/pika_prompt.md

`scripts/run_pika_replay.ps1` (Phase P) then drives the Claude Code CLI → Pika MCP from those files.

Everything here is pure logic + file IO over a `StorageInterface` snapshot — no uAgents, no Pika
client, no wall-clock (ordering comes from the monotonic `seq`), so it is fully unit-testable.

**Data-driven replay (LLD §9.1).** On top of the narrative brief, the recorder also captures a
full-state snapshot per milestone into an in-process, seq-keyed timeline; `export_incident_timeline`
writes it (with per-snapshot `ts` + library metadata) to `out/replay/{incident}.json` for the replay
page, the keyframe capturer, and the `/library`. `ts` is **injected** by the caller (the Orchestrator),
so this module stays wall-clock-free and the `er:events` line shape / `REPLAY-LOG-002` are untouched.

@spec REPLAY-LOG-001 @spec REPLAY-LOG-002 @spec REPLAY-BRIEF-001 @spec REPLAY-BRIEF-002
@spec REPLAY-BRIEF-003 @spec REPLAY-BRIEF-004
@spec REPLAY-SNAP-001 @spec REPLAY-SNAP-002 @spec REPLAY-SNAP-003
@spec REPLAY-KEY-001 @spec REPLAY-LIB-001 @spec REPLAY-LIB-002
"""

import copy
import json
import re
from pathlib import Path

from er_twin.storage import StorageInterface

EVENTS_CHANNEL = "er:events"
LATEST_BRIEF_FILENAME = "incident_replay_brief.json"
PROMPT_FILENAME = "pika_prompt.md"

# event key (as carried on each er:events line) -> incident_type (decision R2-H / REPLAY-BRIEF-004).
# Also driven by EVENT_REGISTRY; kept here as the replay module's canonical map.
INCIDENT_TYPES: dict[str, str] = {
    "intake": "patient_intake",
    "oxygen": "low_oxygen_alert",
    "summary": "er_status_summary",
    "discharge": "patient_discharge",
    "resolve": "event_resolved",
}

# Constant cinematic style per incident_type (decision R2-H).
VISUAL_STYLE: dict[str, str] = {
    "patient_intake": "clean cinematic ER intake and triage replay, realistic hospital operations",
    "low_oxygen_alert": "urgent but non-graphic hospital operations replay showing rapid oxygen response",
    "er_status_summary": "clean hospital command-center status visualization",
    "patient_discharge": "calm, resolved ER discharge sequence",
    "event_resolved": "clean hospital operations closure",
}

PIKA_OUTPUTS_REQUESTED: list[str] = [
    "15-25 second incident replay video",
    "captioned timeline",
    "voiceover summary",
]

# --- Data-driven replay (LLD §9.1) ---

# Subdirectories under the out/ dir (LLD §9.1): the snapshot timeline + the captured keyframe PNGs.
REPLAY_SUBDIR = "replay"
FRAMES_SUBDIR = "frames"

# Entity type -> snapshot plural key. Matches the dashboard `snapshot()` shape so the replay page can
# feed each snapshot's `entities` straight into the shared floor-positioning code (REPLAY-FRAME-001).
SNAPSHOT_ENTITIES: dict[str, str] = {
    "patient": "patients", "bed": "beds", "nurse": "nurses",
    "doctor": "doctors", "equipment": "equipment",
}

# Default time compression for the replay clip (decision: 10× — 10 real seconds ≈ 1 video second).
DEFAULT_SPEED_FACTOR = 10
# `generate_keyframes_video` accepts duration ∈ {5, 10} only (verified against the Pika MCP schema).
PIKA_CLIP_DURATIONS: tuple[int, int] = (5, 10)
# `generate_keyframes_video` interpolates between exactly two images (first_frame + last_frame), so the
# verified keyframe cap is 2 and selection degrades to start → end (REPLAY-KEY-001).
KEYFRAME_CAP = 2


def _capture_entities(store: StorageInterface) -> dict[str, list[dict]]:
    """Deep-copy every `er:{entity}:{id}` record into the dashboard snapshot shape (REPLAY-SNAP-001).

    A snapshot is an immutable point-in-time capture, so we `deepcopy` each record: `store.get` only
    returns a *shallow* copy, so a nested field (e.g. `vitals`) would otherwise share its object with the
    live store and a later in-place mutation could bleed into an already-captured snapshot.
    """
    return {
        plural: [copy.deepcopy(store.get(f"er:{entity}:{eid}")) for eid in store.list_ids(entity)]
        for entity, plural in SNAPSHOT_ENTITIES.items()
    }

# Milestone action -> the agent that owns it, for the timeline `actor` field (cosmetic; LLD §9 examples).
_ACTOR_BY_ACTION: dict[str, str] = {
    "intake_received": "orchestrator", "record_created": "admissions", "patient_bound": "orchestrator",
    "triaged": "triage", "bed_assigned": "bed", "nurse_assigned": "nurse", "doctor_paged": "doctor",
    "intake_complete": "orchestrator", "patient_capacity_reached": "orchestrator",
    "no_bed_available": "bed", "no_nurse_available": "nurse", "no_doctor_available": "doctor",
    "oxygen_drop_simulated": "equipment", "alert_raised": "equipment", "unit_located": "equipment",
    "nurse_dispatched": "nurse", "oxygen_swap_complete": "orchestrator",
    "oxygen_event_complete": "orchestrator", "no_replacement_unit_available": "equipment",
    "no_dispatch_nurse_available": "nurse", "summary_generated": "orchestrator",
    "event_resolved": "admin", "doctor_assigned": "doctor", "discharge_complete": "orchestrator",
}


def actor_for(action: str) -> str:
    """Map a milestone action to its owning agent (default: orchestrator)."""
    return _ACTOR_BY_ACTION.get(action, "orchestrator")


def severity_from_acuity(acuity: int | None) -> str:
    """ESI acuity -> incident severity (decision R2-H): 1 critical, 2 high, 3 medium, 4-5 low."""
    return {1: "critical", 2: "high", 3: "medium"}.get(acuity, "low")


class ReplayRecorder:
    """Holds the per-run `seq` counter and per-type incident counters (LLD §9, decision Gap 9).

    Reset per process run; no wall-clock, no store dependency for its own state. `log` stamps a line
    with the next `seq` and publishes it to `er:events`; `next_incident_id` mints `{type}-{n:04d}`.
    """

    def __init__(self) -> None:
        self._seq = 0
        self._incident_counters: dict[str, int] = {t: 0 for t in INCIDENT_TYPES.values()}
        # Full-state snapshot timeline, keyed by `seq` so a re-capture overwrites (REPLAY-SNAP-002).
        self._timeline: dict[int, dict] = {}

    @property
    def seq(self) -> int:
        return self._seq

    def snapshot(
        self,
        store: StorageInterface,
        seq: int,
        ts: float,
        action: str = "",
        actor: str = "",
        target: str | None = None,
    ) -> dict:
        """Capture a full-state snapshot for `seq` and return it (LLD §9.1).

        @spec REPLAY-SNAP-001 — every entity record + a real wall-clock `ts` (injected by the caller,
        so this module stays wall-clock-free; the `er:events` line shape / REPLAY-LOG-002 are untouched).
        @spec REPLAY-SNAP-002 — keyed by `seq`, so re-capturing the same `seq` overwrites (idempotent).
        """
        record = {
            "seq": seq, "ts": ts, "action": action, "actor": actor,
            "target": target, "entities": _capture_entities(store),
        }
        self._timeline[seq] = record
        return record

    @property
    def timeline(self) -> list[dict]:
        """The captured snapshots, ordered by `seq`."""
        return [self._timeline[s] for s in sorted(self._timeline)]

    def snapshots_for(self, seqs) -> list[dict]:
        """The captured snapshots whose `seq` is in `seqs`, ordered by `seq` (per-incident slice)."""
        wanted = set(seqs)
        return [self._timeline[s] for s in sorted(self._timeline) if s in wanted]

    def log(
        self,
        store: StorageInterface,
        event: str,
        actor: str,
        action: str,
        target: str | None = None,
        **detail,
    ) -> dict:
        """Publish one structured milestone line to `er:events` and return it.

        @spec REPLAY-LOG-001 — line shape {seq, event, actor, action, target, detail}.
        @spec REPLAY-LOG-002 — `seq` is monotonic per run; no wall-clock field.
        """
        line = {
            "seq": self._seq, "event": event, "actor": actor,
            "action": action, "target": target, "detail": detail,
        }
        self._seq += 1
        store.publish(EVENTS_CHANNEL, json.dumps(line))
        return line

    def next_incident_id(self, event: str) -> str:
        """Increment the incident counter for `event`'s type and return `{incident_type}-{n:04d}`.

        @spec REPLAY-BRIEF-004 — incident_type ∈ {patient_intake, low_oxygen_alert, er_status_summary}.
        """
        incident_type = INCIDENT_TYPES[event]
        self._incident_counters[incident_type] += 1
        return f"{incident_type}-{self._incident_counters[incident_type]:04d}"


def _patient_id_in(lines: list[dict]) -> str | None:
    """The first patient id referenced as a milestone target (e.g. `p1`), or None."""
    for ln in lines:
        target = ln.get("target")
        if isinstance(target, str) and re.fullmatch(r"p\d+", target):
            return target
    return None


def _bed_display(bed_id: str | None) -> str | None:
    """`bed3` -> `bed-3`; passthrough for already-hyphenated / None."""
    if not bed_id:
        return None
    match = re.fullmatch(r"bed(\d+)", bed_id)
    return f"bed-{match.group(1)}" if match else bed_id


def _state_change(line: dict) -> str:
    """Render a milestone's detail as a compact `k=v` change string for the timeline (LLD §9)."""
    detail = line.get("detail") or {}
    parts = [f"{k}={v}" for k, v in detail.items() if v is not None and v != ""]
    return ", ".join(parts)


def _narrative(
    incident_type: str, lines: list[dict], patient: dict, store: StorageInterface
) -> tuple[str, str, str]:
    """Derive (title, summary, final_state) for the brief from the patient record + milestone lines."""
    if incident_type == "patient_intake":
        name = patient.get("name", patient.get("id", "patient"))
        complaint = patient.get("chief_complaint", "presentation")
        acuity = patient.get("acuity")
        bed = _bed_display(patient.get("assigned_bed"))
        team = ", ".join(patient.get("care_team", [])) or "no staff yet"
        title = f"{complaint.capitalize()} intake — ESI-{acuity}"
        summary = f"{name} ({complaint}) admitted to {bed or 'no bed'}; care team: {team}."
        final_state = f"{patient.get('id')} {patient.get('status', 'unknown')}" + (
            f" in {bed}" if bed else ""
        )
        return title, summary, final_state

    if incident_type == "low_oxygen_alert":
        bed = _bed_display(patient.get("assigned_bed")) or "the affected bed"
        swapped = any(ln["action"] == "oxygen_swap_complete" for ln in lines)
        title = f"Low-oxygen response — {bed}"
        if swapped:
            spo2 = (patient.get("vitals") or {}).get("spo2")
            summary = (
                f"Oxygen unit autonomously flagged low at {bed}; replacement located, nurse dispatched, "
                f"unit swapped" + (f"; SpO2 restored to {spo2}%." if spo2 else ".")
            )
            final_state = f"{bed} on replacement oxygen unit; alert resolved."
        else:
            summary = f"Low oxygen flagged at {bed}; response could not complete (see timeline)."
            final_state = f"{bed} alert unresolved."
        return title, summary, final_state

    # er_status_summary
    summary_line = next((ln for ln in lines if ln["action"] == "summary_generated"), None)
    text = (summary_line or {}).get("detail", {}).get("text", "ER status snapshot.")
    return "ER status snapshot", text, text


def build_brief(
    lines: list[dict], incident_id: str, incident_type: str, store: StorageInterface
) -> dict:
    """Derive the `out/incident_replay_brief.json` shape from an incident's event-log lines (LLD §9).

    Pure + read-only: reads the patient record from `store` to derive severity/location/narrative;
    `timeline[].t` is a synthetic display stamp derived from the (relative) `seq` — not wall-clock.

    @spec REPLAY-BRIEF-001 @spec REPLAY-BRIEF-004
    """
    ordered = sorted(lines, key=lambda ln: ln["seq"])
    patient_id = _patient_id_in(ordered)
    record = store.get(f"er:patient:{patient_id}") if patient_id else {}
    acuity = record.get("acuity")

    if acuity is not None:
        severity = severity_from_acuity(acuity)
    elif incident_type == "low_oxygen_alert":
        severity = "medium"  # alert with no locatable patient (decision R2-H)
    else:
        severity = "low"

    patient = None
    if patient_id:
        patient = {
            "id": patient_id,
            "condition": f"synthetic {record.get('chief_complaint', 'condition')}",
            "acuity": acuity,
        }

    base_seq = ordered[0]["seq"] if ordered else 0
    timeline = [
        {
            "t": f"00:{(ln['seq'] - base_seq) * 5:02d}",
            "actor": ln.get("actor") or actor_for(ln["action"]),
            "action": ln["action"],
            "target": ln.get("target"),
            "state_change": _state_change(ln),
        }
        for ln in ordered
    ]

    title, summary, final_state = _narrative(incident_type, ordered, record, store)
    return {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "title": title,
        "summary": summary,
        "severity": severity,
        "location": f"ER {_bed_display(record.get('assigned_bed'))}" if record.get("assigned_bed") else "ER",
        "patient": patient,
        "timeline": timeline,
        "final_state": final_state,
        "visual_style": VISUAL_STYLE[incident_type],
        "pika_outputs_requested": list(PIKA_OUTPUTS_REQUESTED),
    }


def render_pika_prompt(brief: dict) -> str:
    """Render the human-/MCP-readable creative brief Pika MCP turns into replay media (LLD §9).

    @spec REPLAY-BRIEF-002 — instructs synthetic-data-only / no-PHI safety, autonomous-coordination
    emphasis, hackathon-demo suitability, and the return contract (asset URL/ID, task_id, tool, summary).
    """
    timeline_md = "\n".join(
        f"- `{e['t']}` **{e['actor']}** {e['action']}"
        + (f" → {e['target']}" if e.get("target") else "")
        + (f" ({e['state_change']})" if e.get("state_change") else "")
        for e in brief["timeline"]
    )
    patient = brief.get("patient")
    patient_md = (
        f"- Patient: `{patient['id']}` — {patient['condition']} (ESI-{patient['acuity']})"
        if patient else "- Patient: none (operations-level incident)"
    )
    return f"""# Pika Replay Brief — {brief['title']}

**Incident:** `{brief['incident_id']}` ({brief['incident_type']}) · **Severity:** {brief['severity']} · **Location:** {brief['location']}

## Scene
{brief['summary']}

{patient_md}
- Final state: {brief['final_state']}

## Timeline (synthetic display times)
{timeline_md}

## Visual style
{brief['visual_style']}

## Instructions (must follow)
- Use **synthetic hospital data only** — no gore, **no real people**, no identifiable faces, no real PHI.
- Produce a safe, cinematic, realistic **hospital-operations replay** suitable for a hackathon demo.
- Emphasize the **autonomous agent coordination** across the timeline and keep the timeline legible.
- Requested outputs: {", ".join(brief['pika_outputs_requested'])}.

## Return contract
Return the asset **URL/ID**, the **task_id** (if the render is async), the **tool used**, and a short
**summary** of what was produced.
"""


def write_incident(brief: dict, out_dir: str = "out") -> dict[str, str]:
    """Write the per-incident history file, the latest-brief copy, and the Pika prompt (LLD §9 R2-H).

    Returns the written paths. The per-incident `{incident_id}.json` is history; `incident_replay_brief.json`
    is the fixed path the Phase P Pika script reads (always the most recent incident).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    brief_json = json.dumps(brief, indent=2)

    history = out / f"{brief['incident_id']}.json"
    latest = out / LATEST_BRIEF_FILENAME
    prompt = out / PROMPT_FILENAME
    history.write_text(brief_json, encoding="utf-8")
    latest.write_text(brief_json, encoding="utf-8")
    prompt.write_text(render_pika_prompt(brief), encoding="utf-8")
    return {"history": str(history), "latest": str(latest), "prompt": str(prompt)}


def export_incident(
    lines: list[dict], incident_id: str, incident_type: str, store: StorageInterface, out_dir: str = "out"
) -> dict | None:
    """Build the brief from `lines` and write the replay artifacts; return the brief (or None).

    @spec REPLAY-BRIEF-003 — if no milestone lines were recorded (no event ran), write nothing and
    return None: no empty artifacts.
    """
    if not lines:
        return None
    brief = build_brief(lines, incident_id, incident_type, store)
    write_incident(brief, out_dir=out_dir)
    return brief


# --- Data-driven replay: snapshot timeline export + keyframe selection (LLD §9.1) ---


def requested_clip_duration(
    start_ts: float | None, end_ts: float | None, speed_factor: int = DEFAULT_SPEED_FACTOR
) -> int:
    """Real elapsed time compressed by `speed_factor`, snapped to Pika's allowed {5, 10} seconds.

    @spec REPLAY-LIB-002 — requested clip duration ≈ `real_elapsed / speed_factor`, clamped to the
    `generate_keyframes_video` duration enum so frame-space isn't wasted on a too-long clip.
    """
    lo, hi = PIKA_CLIP_DURATIONS
    if start_ts is None or end_ts is None or speed_factor <= 0:
        return lo
    raw = max(0.0, end_ts - start_ts) / speed_factor
    if raw <= lo:
        return lo
    if raw >= hi:
        return hi
    return lo if (raw - lo) <= (hi - raw) else hi


def select_keyframes(snapshots: list[dict], cap: int = KEYFRAME_CAP) -> list[dict]:
    """Pick the state-change snapshots, capped, degrading to evenly-spaced frames incl. first + last.

    @spec REPLAY-KEY-001 — keep snapshots where entity state actually changed (always the first), then
    cap at Pika's verified keyframe limit (`KEYFRAME_CAP = 2` → start → end). Pure: unit-testable
    without a browser.
    """
    ordered = sorted(snapshots, key=lambda s: s["seq"])
    if not ordered:
        return []
    changed = [ordered[0]]
    for snap in ordered[1:]:
        if snap.get("entities") != changed[-1].get("entities"):
            changed.append(snap)
    if cap <= 0 or len(changed) <= cap:
        return changed
    if cap == 1:
        return [changed[-1]]
    last = len(changed) - 1
    idxs = sorted({round(i * last / (cap - 1)) for i in range(cap)})
    return [changed[i] for i in idxs]


def _distinct_involved(snapshots: list[dict], display=lambda x: x) -> list[str]:
    """Distinct timeline actors + targets (order-preserving), mapped through `display` (REPLAY-LIB-001)."""
    seen: list[str] = []
    for snap in snapshots:
        for key in (snap.get("actor"), snap.get("target")):
            if not key:
                continue
            name = display(key)
            if name and name not in seen:
                seen.append(name)
    return seen


def build_incident_timeline(
    snapshots: list[dict],
    incident_id: str,
    incident_type: str,
    title: str,
    summary: str,
    speed_factor: int = DEFAULT_SPEED_FACTOR,
    display=lambda x: x,
) -> dict:
    """Build the `out/replay/{incident}.json` record from captured snapshots + library metadata.

    @spec REPLAY-LIB-001 — title/summary/incident_type, start/end `ts` (first/last snapshot), and
    `involved[]` (distinct actors+targets via `display`/DISPLAY_NAMES). `video_url` starts null and is
    filled in by the Phase-4 Pika step (REPLAY-LIB-003).
    """
    ordered = sorted(snapshots, key=lambda s: s["seq"])
    return {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "title": title,
        "summary": summary,
        "speed_factor": speed_factor,
        "start_ts": ordered[0]["ts"] if ordered else None,
        "end_ts": ordered[-1]["ts"] if ordered else None,
        "involved": _distinct_involved(ordered, display),
        "video_url": None,
        "snapshots": ordered,
    }


def export_incident_timeline(
    snapshots: list[dict],
    incident_id: str,
    incident_type: str,
    title: str,
    summary: str,
    speed_factor: int = DEFAULT_SPEED_FACTOR,
    display=lambda x: x,
    out_dir: str = "out",
) -> dict | None:
    """Write the snapshot timeline to `out/replay/{incident}.json`; return the record (or None).

    @spec REPLAY-SNAP-003 — if no milestones were captured (no snapshots), write nothing and return
    None (mirrors REPLAY-BRIEF-003 — no empty artifacts).
    """
    if not snapshots:
        return None
    record = build_incident_timeline(
        snapshots, incident_id, incident_type, title, summary,
        speed_factor=speed_factor, display=display,
    )
    replay_dir = Path(out_dir) / REPLAY_SUBDIR
    replay_dir.mkdir(parents=True, exist_ok=True)
    (replay_dir / f"{incident_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
