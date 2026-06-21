"""Shared parsing and synthesis helpers for event handlers."""

from __future__ import annotations

import re

from er_twin.ehr import get_ehr_record

_MRN_RE = re.compile(r"\bMRN-\d+\b", re.IGNORECASE)
_AGENT_MENTION_RE = re.compile(r"^\s*@agent1[0-9a-z]+\s+", re.IGNORECASE)
_MRN_ONLY_RE = re.compile(r"^\s*MRN-\d+\s*$", re.IGNORECASE)


def strip_agent_mention(text: str) -> str:
    return _AGENT_MENTION_RE.sub("", text).strip()


def extract_mrn(text: str) -> str:
    match = _MRN_RE.search(text)
    return match.group(0).upper() if match else ""
_CONFIRM_RE = re.compile(r"^\s*(confirm|yes|approved?|ok)\s*\.?\s*$", re.IGNORECASE)
_ASSIGN_RE = re.compile(
    r"\bassign\s+(?:(?:doc(?:tor)?|dr)\s*(\w+)|(\w+))\s+(?:nurse\s*(\w+)|(\w+))\s+(?:bed\s*(\w+)|(\w+))",
    re.IGNORECASE,
)
_BED_RE = re.compile(r"\bbed\s*(\d+)\b", re.IGNORECASE)
_NURSE_RE = re.compile(r"\bnurse\s*(\d+)\b", re.IGNORECASE)
_DOC_RE = re.compile(r"\b(?:doc(?:tor)?|dr)\s*(\d+)\b", re.IGNORECASE)
_COMPLAINT_KEYWORDS = (
    "chest pain", "shortness of breath", "abdominal pain", "headache",
    "ankle", "fracture", "laceration", "fever", "nausea", "injury",
    "pain", "bleeding", "dizziness", "weakness",
)


def normalize_text(text: str) -> str:
    return strip_agent_mention(text).strip()


def is_confirm(text: str) -> bool:
    return bool(_CONFIRM_RE.match(normalize_text(text)))


def is_mrn_only(text: str) -> bool:
    return bool(_MRN_ONLY_RE.match(normalize_text(text)))


def synthesize_vitals(mrn: str) -> dict:
    """Deterministic vitals per MRN for demo intake when none are supplied."""
    try:
        n = int(mrn.split("-")[1])
    except (IndexError, ValueError):
        n = 1
    return {
        "heart_rate": 72 + (n % 35),
        "blood_pressure": f"{118 + n % 28}/{76 + n % 12}",
        "resp_rate": 16 + (n % 8),
        "spo2": 95 + (n % 4),
        "temperature_f": round(98.0 + (n % 10) * 0.1, 1),
        "pain_score": 3 + (n % 7),
    }


def extract_complaint(text: str, mrn: str = "") -> str:
    """Pull a chief complaint from chat text, or return empty string."""
    cleaned = normalize_text(text)
    if mrn:
        cleaned = re.sub(re.escape(mrn), "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\b(intake|admit|patient|mrn)\b", "", cleaned, flags=re.IGNORECASE).strip(" ,:-")
    lowered = cleaned.lower()
    for kw in _COMPLAINT_KEYWORDS:
        if kw in lowered:
            return kw
    if len(cleaned) >= 4 and not is_mrn_only(cleaned):
        return cleaned
    return ""


def ehr_name_for_mrn(mrn: str) -> str:
    entry = get_ehr_record(mrn)
    return entry.get("name", "Unknown Patient") if entry else "Unknown Patient"


def parse_assignment_override(text: str) -> dict[str, str | None]:
    """Parse 'assign doc1 nurse2 bed3' style overrides."""
    t = normalize_text(text).lower()
    out: dict[str, str | None] = {"doctor_id": None, "nurse_id": None, "bed_id": None}
    m = _ASSIGN_RE.search(t)
    if m:
        doc = m.group(1) or m.group(2)
        nurse = m.group(3) or m.group(4)
        bed = m.group(5) or m.group(6)
        if doc and doc.startswith("doc"):
            out["doctor_id"] = doc
        elif doc and doc.startswith("nurse"):
            out["nurse_id"] = doc
        elif doc:
            out["doctor_id"] = doc if doc.startswith("doc") else f"doc{doc.removeprefix('dr')}"
        if nurse:
            out["nurse_id"] = nurse if nurse.startswith("nurse") else f"nurse{nurse}"
        if bed:
            out["bed_id"] = bed if bed.startswith("bed") else f"bed{bed}"
        return out
    dm = _DOC_RE.search(t)
    nm = _NURSE_RE.search(t)
    bm = _BED_RE.search(t)
    if dm:
        out["doctor_id"] = f"doc{dm.group(1)}"
    if nm:
        out["nurse_id"] = f"nurse{nm.group(1)}"
    if bm:
        out["bed_id"] = f"bed{bm.group(1)}"
    return out


def format_proposal(
    name: str, mrn: str, acuity: int, specialty: str,
    bed_id: str | None, nurse_id: str | None, doctor_id: str | None,
    display,
    available: dict | None = None,
) -> str:
    available = available or {}
    lines = [
        f"Triage complete for {name} ({mrn}): ESI-{acuity} ({specialty}).",
        "",
    ]

    # Available beds
    beds = available.get("beds", [])
    if beds:
        bed_opts = ", ".join(
            f"{b['id']} ({b['specialty']}){' ★' if b['id'] == bed_id else ''}"
            for b in beds
        )
        lines.append(f"Beds available: {bed_opts}")
    else:
        lines.append("Beds available: none")

    # Available nurses
    nurses = available.get("nurses", [])
    if nurses:
        nurse_opts = ", ".join(
            f"{display(n['id'])}{' ★' if n['id'] == nurse_id else ''}"
            for n in nurses
        )
        lines.append(f"Nurses available: {nurse_opts}")
    else:
        lines.append("Nurses available: none")

    # Available doctors (only for acuity ≤ 2)
    if acuity <= 2:
        docs = available.get("doctors", [])
        if docs:
            doc_opts = ", ".join(
                f"{display(d['id'])} ({d['specialty']}, load {d['load']}){' ★' if d['id'] == doctor_id else ''}"
                for d in docs
            )
            lines.append(f"Doctors available: {doc_opts}")
        else:
            lines.append("Doctors available: none (urgent — ESI-2)")

    lines.append("")
    lines.append("★ = recommended.")
    lines.append("→ Pick interactively: http://localhost:8050  (Current Events tab)")
    lines.append("→ Or reply here:  \"confirm\"  or  \"assign doc2 nurse2 bed3\"")
    return "\n".join(lines)


def format_discharge_proposal(
    name: str,
    mrn: str,
    bed_id: str | None,
    nurse_id: str | None,
    doctor_id: str | None,
    display,
    available: dict | None = None,
) -> str:
    """Chat proposal for discharge sign-off staff selection."""
    available = available or {}
    bed_text = display(bed_id) if bed_id else "waiting area"
    lines = [
        f"Discharge proposal for {name} ({mrn}) from {bed_text}.",
        "Select staff to sign off discharge:",
        "",
    ]

    nurses = available.get("nurses", [])
    if nurses:
        nurse_opts = ", ".join(
            f"{display(n['id'])} ({n.get('tag', 'available')}){' ★' if n['id'] == nurse_id else ''}"
            for n in nurses
        )
        lines.append(f"Nurses: {nurse_opts}")
    else:
        lines.append("Nurses: none")

    docs = available.get("doctors", [])
    if docs:
        doc_opts = ", ".join(
            f"{display(d['id'])} ({d.get('tag', 'available')}){' ★' if d['id'] == doctor_id else ''}"
            for d in docs
        )
        lines.append(f"Doctors: {doc_opts}")
    else:
        lines.append("Doctors: none")

    lines.append("")
    lines.append("★ = recommended (current care team).")
    lines.append("→ Pick interactively: http://localhost:8050  (Current Events tab)")
    lines.append("→ Or reply here:  \"confirm\"  or  \"assign nurse2 doc1\"")
    return "\n".join(lines)
