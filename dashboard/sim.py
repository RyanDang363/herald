"""Scripted demo timeline — a deterministic ER story on a loop.

@spec DASH-SIM-001, DASH-SIM-002

Drives the live-feedback / agent-visualizer / floor-map UI without a running Bureau. The frontend
still polls the normal API; this just supplies an evolving snapshot + event stream over time.

The timeline is a list of steps, each at an elapsed-second offset. State is the fixture BASE with
each step's `patch` merged cumulatively (records keyed `entity:id`); events accumulate. The whole
thing loops every LOOP_SECONDS so a demo can be left running.
"""

import json
from copy import deepcopy
from pathlib import Path

from .datasource import ENTITIES

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "er_state.json"
LOOP_SECONDS = 36


def _base_records() -> dict[tuple[str, str], dict]:
    data = json.loads(_FIXTURE_PATH.read_text())
    records: dict[tuple[str, str], dict] = {}
    for entity, plural in ENTITIES.items():
        for rec in data.get(plural, []):
            records[(entity, rec["id"])] = deepcopy(rec)
    return records


def _ev(event: str, detail: str, frm: str, to: str) -> dict:
    return {"event": event, "detail": detail, "from": frm, "to": to}


# (at_seconds, [events emitted at this step], {(entity, id): field patch})
TIMELINE: list[tuple[int, list[dict], dict[tuple[str, str], dict]]] = [
    (
        4,
        [_ev("intake", "New patient Alex Kim arrived (fever)", "ASI:One", "OrchestratorAgent")],
        {("patient", "p3"): {"status": "waiting"}},
    ),
    (
        7,
        [_ev("intake", "Routing intake to admissions", "OrchestratorAgent", "AdmissionsAgent")],
        {("patient", "p3"): {"status": "in_triage"}},
    ),
    (
        10,
        [_ev("triage", "Alex Kim triaged ESI-4", "OrchestratorAgent", "TriageAgent")],
        {("patient", "p3"): {"acuity": 4}},
    ),
    (
        13,
        [_ev("bed", "Assigning bed2 to Alex Kim", "OrchestratorAgent", "BedAgent")],
        {
            ("patient", "p3"): {"status": "admitted", "assigned_bed": "bed2"},
            ("bed", "bed2"): {"status": "occupied", "occupied_by": "p3"},
        },
    ),
    (
        16,
        [_ev("staff", "nurse2 assigned to p3 at bed2", "OrchestratorAgent", "NurseAgent")],
        {
            ("patient", "p3"): {"care_team": ["nurse2"]},
            ("nurse", "nurse2"): {"available": False, "location": "bed2", "assignments": ["p3"]},
        },
    ),
    (
        22,
        [_ev("alert", "o2_2 oxygen dropping (28%) at bed1", "EquipmentAgent", "OrchestratorAgent")],
        {("equipment", "o2_2"): {"supply_level": 28}},
    ),
    (
        25,
        [
            _ev(
                "dispatch",
                "Locating replacement O2 near bed1",
                "OrchestratorAgent",
                "EquipmentAgent",
            )
        ],
        {},
    ),
    (
        28,
        [_ev("dispatch", "nurse1 bringing o2_1 to bed1", "OrchestratorAgent", "NurseAgent")],
        {
            ("equipment", "o2_1"): {"location": "bed1", "in_use_by": "p1"},
            ("equipment", "o2_2"): {"supply_level": 28, "in_use_by": None},
        },
    ),
    (
        32,
        [
            _ev(
                "summary",
                "3 patients active, 2 beds occupied, 1 alert resolved",
                "OrchestratorAgent",
                "ASI:One",
            )
        ],
        {},
    ),
]


class SimController:
    """Computes (snapshot, events) for an elapsed time, looping every LOOP_SECONDS."""

    def __init__(self) -> None:
        self._t0: float | None = None

    def _elapsed(self, now: float) -> float:
        if self._t0 is None:
            self._t0 = now
        return (now - self._t0) % LOOP_SECONDS

    def state_and_events(self, now: float) -> tuple[dict, list[dict]]:
        elapsed = self._elapsed(now)
        records = _base_records()
        events: list[dict] = []
        for at, evs, patch in TIMELINE:
            if at > elapsed:
                break
            for key, fields in patch.items():
                records.setdefault(key, {}).update(fields)
            for i, ev in enumerate(evs):
                events.append({"ts": f"t+{at:02d}s", "seq": at * 10 + i, **ev})
        return _records_to_snapshot(records), events


def _records_to_snapshot(records: dict[tuple[str, str], dict]) -> dict:
    out: dict[str, list] = {plural: [] for plural in ENTITIES.values()}
    for (entity, _id), rec in records.items():
        out[ENTITIES[entity]].append(rec)
    return out


# Module-level singleton used by the datasource in sim mode.
controller = SimController()
