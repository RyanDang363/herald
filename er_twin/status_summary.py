"""Read-only ER status summary (SUMM-*)."""

from __future__ import annotations

from er_twin.agents import bed, nurse, patient
from er_twin.display import display
from er_twin.storage import StorageInterface

_ACTIVE_PATIENT_STATUSES = {"waiting", "in_triage", "admitted", "in_treatment"}


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _active_patients(store: StorageInterface) -> list[dict]:
    records = [store.get(patient.patient_key(pid)) for pid in store.list_ids("patient")]
    return [r for r in records if r.get("status") in _ACTIVE_PATIENT_STATUSES]


def build_status_summary(store: StorageInterface, active_o2_alert_beds: list[str]) -> str:
    active = _active_patients(store)
    occupied_beds = [
        bid for bid in store.list_ids("bed")
        if store.get(bed.bed_key(bid)).get("status") == "occupied"
    ]
    free_nurses = sum(
        1 for nid in store.list_ids("nurse")
        if store.get(nurse.nurse_key(nid)).get("available") is True
    )
    if not active and not occupied_beds:
        return (
            "Nothing currently happening in the ER — no active patients, "
            "no occupied beds, and no critical alerts."
        )
    n_pat, n_bed = len(active), len(occupied_beds)
    counts = (
        f"{n_pat} {_plural(n_pat, 'patient', 'patients')} active, "
        f"{n_bed} {_plural(n_bed, 'bed', 'beds')} occupied, "
        f"{free_nurses} {_plural(free_nurses, 'nurse', 'nurse(s)')} free."
    )
    tail: list[str] = []
    if active_o2_alert_beds:
        n_alerts = len(active_o2_alert_beds)
        beds_named = ", ".join(display(b) for b in active_o2_alert_beds)
        tail.append(f"{n_alerts} active O2 alert{_plural(n_alerts, '', 's')} on {beds_named}.")
    urgent = [p for p in active if isinstance(p.get("acuity"), int) and p["acuity"] <= 2]
    if urgent:
        top = min(urgent, key=lambda p: (p["acuity"], p.get("id", "")))
        tail.append(f"Most urgent: {top.get('name', top.get('id'))} (ESI-{top['acuity']}).")
    if not tail:
        tail.append("No critical alerts.")
    return f"{counts} {' '.join(tail)}"


def compose_summary(
    store: StorageInterface, active_o2_alert_beds: list[str], recalled: list[str]
) -> str:
    summary = build_status_summary(store, active_o2_alert_beds)
    if recalled:
        summary = f"{summary} Recent context: " + "; ".join(recalled) + "."
    return summary
