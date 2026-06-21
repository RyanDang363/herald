"""Tests for the EHR loader module (er_twin/ehr.py).

All tests use a temp master file via a tmp_path fixture so the committed
fixtures/ehr_master.json is never mutated. Tests are fully offline (no Redis,
no network).

Spec coverage:
  EHR-FLOW-003, EHR-FLOW-004, EHR-FLOW-005
  EHR-IDEM-001, EHR-IDEM-002
  EHR-ERR-001
  INTAKE-IDEM-001 (find_active_patient_by_mrn path)
"""

from __future__ import annotations

import json
import pathlib

import er_twin.ehr as ehr_mod
from er_twin.ehr import (
    build_live_record,
    find_active_patient_by_mrn,
    get_ehr_record,
    load_master,
    next_mrn,
    register_new_patient,
)
from er_twin.storage import InMemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_master(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh)
    # Flush the module-level cache so each test starts clean.
    ehr_mod._flush_cache(path)


_SAMPLE_EHR = {
    "MRN-0001": {
        "mrn": "MRN-0001",
        "name": "Jordan Lee",
        "birthdate": "1968-03-12",
        "gender": "M",
        "medications": ["warfarin", "metoprolol"],
        "conditions": ["atrial fibrillation"],
        "allergies": ["penicillin"],
    },
    "MRN-0002": {
        "mrn": "MRN-0002",
        "name": "Taylor Chen",
        "birthdate": "1990-07-22",
        "gender": "F",
        "medications": [],
        "conditions": [],
        "allergies": [],
    },
}


# ---------------------------------------------------------------------------
# load_master / get_ehr_record
# ---------------------------------------------------------------------------

def test_load_master_returns_records(tmp_path: pathlib.Path) -> None:
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)
    master = load_master(master_file)
    assert "MRN-0001" in master
    assert master["MRN-0001"]["name"] == "Jordan Lee"


def test_load_master_missing_file_returns_empty(tmp_path: pathlib.Path) -> None:
    # @spec EHR-ERR-001
    missing = tmp_path / "nonexistent.json"
    assert load_master(missing) == {}


def test_get_ehr_record_found(tmp_path: pathlib.Path) -> None:
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)
    rec = get_ehr_record("MRN-0001", master_file)
    assert rec is not None
    assert rec["medications"] == ["warfarin", "metoprolol"]


def test_get_ehr_record_missing_returns_none(tmp_path: pathlib.Path) -> None:
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)
    assert get_ehr_record("MRN-9999", master_file) is None


# ---------------------------------------------------------------------------
# next_mrn
# ---------------------------------------------------------------------------

def test_next_mrn_empty_master_returns_0001(tmp_path: pathlib.Path) -> None:
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, {})
    assert next_mrn(master_file) == "MRN-0001"


def test_next_mrn_increments_beyond_existing(tmp_path: pathlib.Path) -> None:
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)
    assert next_mrn(master_file) == "MRN-0003"


def test_next_mrn_missing_file_returns_0001(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "nonexistent.json"
    assert next_mrn(missing) == "MRN-0001"


# ---------------------------------------------------------------------------
# register_new_patient
# ---------------------------------------------------------------------------

def test_register_new_patient_writes_and_caches(tmp_path: pathlib.Path) -> None:
    # @spec EHR-IDEM-002
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)

    register_new_patient("MRN-0003", "Alex Smith", path=master_file)

    # Verify on-disk
    with open(master_file) as fh:
        on_disk = json.load(fh)
    assert "MRN-0003" in on_disk

    # Verify cache coherence — in-process lookup must see the new entry.
    assert get_ehr_record("MRN-0003", master_file) is not None


def test_register_new_patient_idempotent(tmp_path: pathlib.Path) -> None:
    # @spec EHR-IDEM-001
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)

    register_new_patient("MRN-0003", "Alex Smith", path=master_file)
    register_new_patient("MRN-0003", "Alex Smith Again", path=master_file)

    with open(master_file) as fh:
        on_disk = json.load(fh)
    # Should appear exactly once, with original name preserved.
    mrn3_entries = [k for k in on_disk if k == "MRN-0003"]
    assert len(mrn3_entries) == 1
    assert on_disk["MRN-0003"]["name"] == "Alex Smith"


# ---------------------------------------------------------------------------
# build_live_record — returning patient
# ---------------------------------------------------------------------------

def test_build_live_record_returning_patient(tmp_path: pathlib.Path) -> None:
    # @spec EHR-FLOW-003
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)

    rec = build_live_record("MRN-0001", "Jordan Lee", "chest pain", {"hr": 102}, master_file)

    assert rec["mrn"] == "MRN-0001"
    assert rec["new_patient"] is False
    assert rec["history"]["medications"] == ["warfarin", "metoprolol"]
    assert rec["history"]["conditions"] == ["atrial fibrillation"]
    assert rec["history"]["allergies"] == ["penicillin"]


def test_build_live_record_does_not_set_patient_id_or_status(tmp_path: pathlib.Path) -> None:
    """Loader intentionally leaves patient_id and status for AdmissionsAgent."""
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)

    rec = build_live_record("MRN-0001", "Jordan Lee", "chest pain", {}, master_file)
    assert "patient_id" not in rec
    assert "status" not in rec


# ---------------------------------------------------------------------------
# build_live_record — new patient (unknown MRN)
# ---------------------------------------------------------------------------

def test_build_live_record_new_patient_unknown_mrn(tmp_path: pathlib.Path) -> None:
    # @spec EHR-FLOW-004
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)

    rec = build_live_record("MRN-9999", "Alex Smith", "shortness of breath", {}, master_file)

    assert rec["mrn"] == "MRN-9999"
    assert rec["new_patient"] is True
    assert rec["history"] == {"medications": [], "conditions": [], "allergies": []}
    # Writeback: fixture should now contain MRN-9999
    assert get_ehr_record("MRN-9999", master_file) is not None


# ---------------------------------------------------------------------------
# build_live_record — walk-in with blank MRN (mint)
# ---------------------------------------------------------------------------

def test_build_live_record_mints_mrn_when_blank(tmp_path: pathlib.Path) -> None:
    # @spec EHR-FLOW-005
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, _SAMPLE_EHR)  # has MRN-0001 and MRN-0002

    rec = build_live_record("", "New Walker", "ankle injury", {}, master_file)

    assert rec["mrn"] == "MRN-0003"  # next after 0001, 0002
    assert rec["new_patient"] is True
    assert get_ehr_record("MRN-0003", master_file) is not None


def test_build_live_record_mints_mrn_when_none(tmp_path: pathlib.Path) -> None:
    # @spec EHR-FLOW-005 — None is treated same as blank
    master_file = tmp_path / "ehr_master.json"
    _write_master(master_file, {})

    rec = build_live_record(None, "First Ever", "cut finger", {}, master_file)  # type: ignore[arg-type]

    assert rec["mrn"] == "MRN-0001"
    assert rec["new_patient"] is True


# ---------------------------------------------------------------------------
# build_live_record — missing fixture (graceful fallback)
# ---------------------------------------------------------------------------

def test_build_live_record_missing_fixture_treats_as_new(tmp_path: pathlib.Path) -> None:
    # @spec EHR-ERR-001
    missing = tmp_path / "does_not_exist.json"

    rec = build_live_record("MRN-0001", "Anyone", "anything", {}, missing)

    assert rec["new_patient"] is True
    assert rec["history"] == {"medications": [], "conditions": [], "allergies": []}


# ---------------------------------------------------------------------------
# find_active_patient_by_mrn
# ---------------------------------------------------------------------------

def test_find_active_patient_by_mrn_found(tmp_path: pathlib.Path) -> None:
    # @spec INTAKE-IDEM-001
    store = InMemoryStore()
    store.set("er:patient:p1", {"mrn": "MRN-0001", "status": "admitted", "name": "Jordan Lee"})
    store.set("er:patient:p2", {"mrn": "MRN-0002", "status": "waiting", "name": "Taylor Chen"})

    result = find_active_patient_by_mrn(store, "MRN-0002")
    assert result == "p2"


def test_find_active_patient_by_mrn_not_found(tmp_path: pathlib.Path) -> None:
    store = InMemoryStore()
    store.set("er:patient:p1", {"mrn": "MRN-0001", "status": "admitted"})

    assert find_active_patient_by_mrn(store, "MRN-9999") is None


def test_find_active_patient_by_mrn_skips_discharged(tmp_path: pathlib.Path) -> None:
    """Discharged patients must not be returned for MRN dedupe — DK3 / DOMAIN-STATE-003."""
    store = InMemoryStore()
    store.set("er:patient:p1", {"mrn": "MRN-0001", "status": "discharged"})
    store.set("er:patient:p2", {"mrn": "MRN-0001", "status": "admitted"})

    # p1 is discharged — should find p2 (the active re-admission).
    result = find_active_patient_by_mrn(store, "MRN-0001")
    assert result == "p2"


def test_find_active_patient_by_mrn_all_discharged_returns_none() -> None:
    """If the only match is discharged, return None so a new admission is created."""
    store = InMemoryStore()
    store.set("er:patient:p1", {"mrn": "MRN-0001", "status": "discharged"})

    assert find_active_patient_by_mrn(store, "MRN-0001") is None


def test_find_active_patient_by_mrn_empty_store() -> None:
    assert find_active_patient_by_mrn(InMemoryStore(), "MRN-0001") is None


# ---------------------------------------------------------------------------
# build_ehr.py CSV parsing (small inline unit test)
# ---------------------------------------------------------------------------

def test_build_ehr_synthetic_produces_correct_structure() -> None:
    """build_synthetic generates PATIENT_COUNT records with the expected keys."""
    from scripts.build_ehr import build_synthetic

    master = build_synthetic(5)
    assert len(master) == 5
    for mrn, entry in master.items():
        assert mrn.startswith("MRN-")
        assert "name" in entry
        assert "medications" in entry
        assert isinstance(entry["medications"], list)
        assert "conditions" in entry
        assert "allergies" in entry
        assert entry["mrn"] == mrn
