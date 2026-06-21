"""EHR loader — intake-time patient history merge (LLD §4 EHR Contract).

Responsibilities:
  - Load and cache the committed master EHR fixture (fixtures/ehr_master.json).
  - Distinguish returning patients (known MRN → load history) from new patients
    (unknown/blank MRN → empty history + writeback + mint MRN when needed).
  - Provide find_active_patient_by_mrn so agents can resolve MRN → live patient_id
    without raw Redis scans (works on InMemoryStore and RedisStore alike).

Division of labour with AdmissionsAgent (Dev 1):
  - build_live_record returns the EHR-enriched record WITHOUT patient_id / status.
  - AdmissionsAgent adds patient_id, sets status="waiting", and calls store.set().
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from er_twin.storage import StorageInterface

# Module-level cache keyed by resolved fixture path so tests can override safely.
_master_cache: dict[str, dict] = {}


def _fixture_path() -> pathlib.Path:
    from er_twin.config import settings  # local import avoids circular deps at module level

    return pathlib.Path(settings.ehr_master_path)


def load_master(path: pathlib.Path | None = None) -> dict:
    """Return the master EHR dict (keyed by MRN), reading and caching from disk.

    If the fixture is missing or unreadable, returns {} (graceful fallback — EHR-ERR-001).
    """
    resolved = str((path or _fixture_path()).resolve())
    if resolved not in _master_cache:
        _master_cache[resolved] = _read_fixture(resolved)
    return _master_cache[resolved]


def _read_fixture(resolved_path: str) -> dict:
    try:
        with open(resolved_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _flush_cache(path: pathlib.Path) -> None:
    """Invalidate the in-process cache for the given path (called after writeback)."""
    key = str(path.resolve())
    _master_cache.pop(key, None)


def get_ehr_record(mrn: str, path: pathlib.Path | None = None) -> dict | None:
    """Return the master EHR entry for `mrn`, or None if absent."""
    return load_master(path).get(mrn)


def next_mrn(path: pathlib.Path | None = None) -> str:
    """Mint the next sequential MRN (MRN-NNNN) based on the current master.

    Returns MRN-0001 when the master is empty. Thread-safety is not required
    for the demo; this is call-then-persist, not an atomic increment.
    """
    # @spec EHR-FLOW-005
    master = load_master(path)
    if not master:
        return "MRN-0001"
    max_n = 0
    for mrn in master:
        try:
            n = int(mrn.split("-")[1])
            if n > max_n:
                max_n = n
        except (IndexError, ValueError):
            pass
    return f"MRN-{max_n + 1:04d}"


def register_new_patient(
    mrn: str,
    name: str,
    birthdate: str = "",
    gender: str = "U",
    path: pathlib.Path | None = None,
) -> dict:
    """Append a new stub entry to the master EHR and refresh the in-process cache.

    No-op (returns existing entry) if MRN already exists — EHR-IDEM-001.
    Cache is refreshed after writeback so get_ehr_record sees the new entry — EHR-IDEM-002.
    """
    # @spec EHR-IDEM-001, EHR-IDEM-002
    fixture = path or _fixture_path()
    master = load_master(fixture)

    if mrn in master:
        return master[mrn]

    entry: dict = {
        "mrn": mrn,
        "name": name,
        "birthdate": birthdate,
        "gender": gender,
        "medications": [],
        "conditions": [],
        "allergies": [],
    }
    master[mrn] = entry

    fixture.parent.mkdir(parents=True, exist_ok=True)
    with open(fixture, "w", encoding="utf-8") as fh:
        json.dump(master, fh, indent=2)

    # Refresh cache so subsequent in-process lookups see the new entry.
    _flush_cache(fixture)
    _master_cache[str(fixture.resolve())] = master

    return entry


def build_live_record(
    mrn: str,
    name: str,
    chief_complaint: str,
    vitals: dict,
    path: pathlib.Path | None = None,
) -> dict:
    """Build the EHR-enriched patient record for admission.

    MRN resolution (EHR-FLOW-001..005):
      - blank/None mrn  → mint next sequential MRN via next_mrn(); treat as new.
      - mrn in master   → returning patient; load history; new_patient=False.
      - mrn not in master → new patient; empty history; writeback; new_patient=True.

    The returned record contains mrn, name, chief_complaint, vitals, history, new_patient.
    It intentionally does NOT set patient_id or status — those are AdmissionsAgent's job.
    """
    fixture = path or _fixture_path()

    # Mint MRN for unregistered walk-ins.
    if not mrn:
        mrn = next_mrn(fixture)

    ehr_entry = get_ehr_record(mrn, fixture)

    record: dict = {
        "mrn": mrn,
        "name": name,
        "chief_complaint": chief_complaint,
        "vitals": vitals,
    }

    if ehr_entry is not None:
        # @spec EHR-FLOW-003
        record["history"] = {
            "medications": list(ehr_entry.get("medications", [])),
            "conditions": list(ehr_entry.get("conditions", [])),
            "allergies": list(ehr_entry.get("allergies", [])),
        }
        record["new_patient"] = False
    else:
        # @spec EHR-FLOW-004
        record["history"] = {"medications": [], "conditions": [], "allergies": []}
        record["new_patient"] = True
        register_new_patient(mrn, name, path=fixture)

    return record


def find_active_patient_by_mrn(
    store: "StorageInterface",
    mrn: str,
) -> str | None:
    """Return the patient_id of a non-discharged patient with the given MRN, or None.

    Uses store.list_ids + store.get through the StorageInterface so it works on
    both InMemoryStore (USE_MOCK / tests) and RedisStore without raw index scans.
    Also used by AdmissionsAgent for the INTAKE-IDEM-001 MRN-based dedupe check.
    """
    for pid in store.list_ids("patient"):
        record = store.get(f"er:patient:{pid}")
        if record.get("mrn") == mrn and record.get("status") != "discharged":
            return pid
    return None
