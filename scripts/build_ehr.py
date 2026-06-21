"""Build the master EHR fixture (fixtures/ehr_master.json) from Synthea CSV output.

Two modes:
  1. Synthea CSV mode: reads output/csv/ produced by running:
       java -jar synthea-with-dependencies.jar -p 20
     (Java + Synthea JAR must be present; one-time step to regenerate from real data)

  2. Synthetic fallback mode (default when Synthea output is absent):
     generates 20 realistic-but-fictional patient records entirely in Python.
     This is the mode that runs in CI / on machines without Java.

Usage:
  uv run python scripts/build_ehr.py           # auto-detects which mode
  uv run python scripts/build_ehr.py --synthea  # force Synthea CSV mode (fails if absent)
  uv run python scripts/build_ehr.py --synthetic # force synthetic mode
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random

REPO_ROOT = pathlib.Path(__file__).parent.parent
SYNTHEA_CSV_DIR = REPO_ROOT / "output" / "csv"
FIXTURE_PATH = REPO_ROOT / "fixtures" / "ehr_master.json"

PATIENT_COUNT = 20


# ---------------------------------------------------------------------------
# Synthetic data pools (realistic but fictional)
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Drew",
    "Peyton", "Skyler", "Reese", "Emery", "Dakota", "Sage", "River", "Finley",
    "Rowan", "Cameron", "Logan", "Alex",
]
_LAST_NAMES = [
    "Lee", "Chen", "Patel", "Garcia", "Smith", "Johnson", "Williams", "Brown",
    "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas",
    "Jackson", "Harris", "Martin", "Thompson", "White",
]
_GENDERS = ["M", "F", "M", "F", "M"]  # weighted roughly 50/50

_MEDICATIONS: list[list[str]] = [
    [],
    ["metformin"],
    ["lisinopril", "atorvastatin"],
    ["warfarin", "metoprolol"],
    ["amlodipine"],
    ["levothyroxine"],
    ["omeprazole", "sertraline"],
    ["albuterol"],
    ["metoprolol", "furosemide", "aspirin"],
    ["gabapentin", "duloxetine"],
    ["prednisone"],
    ["insulin glargine", "metformin"],
    ["clopidogrel", "atorvastatin", "aspirin"],
    ["hydrochlorothiazide"],
    ["montelukast", "fluticasone"],
    ["rivaroxaban"],
    ["ramipril", "bisoprolol"],
    ["quetiapine"],
    ["tamsulosin"],
    ["esomeprazole", "pantoprazole"],
]

_CONDITIONS: list[list[str]] = [
    [],
    ["type 2 diabetes"],
    ["hypertension"],
    ["atrial fibrillation"],
    ["asthma"],
    ["hypothyroidism"],
    ["gastroesophageal reflux disease"],
    ["chronic obstructive pulmonary disease"],
    ["heart failure", "hypertension"],
    ["chronic pain", "depression"],
    ["rheumatoid arthritis"],
    ["type 1 diabetes"],
    ["coronary artery disease"],
    ["hypertension", "obesity"],
    ["asthma", "allergic rhinitis"],
    ["deep vein thrombosis"],
    ["hypertension", "heart failure"],
    ["bipolar disorder"],
    ["benign prostatic hyperplasia"],
    ["peptic ulcer disease"],
]

_ALLERGIES: list[list[str]] = [
    [],
    ["penicillin"],
    ["sulfa drugs"],
    ["aspirin"],
    ["codeine"],
    ["latex"],
    ["penicillin", "cephalosporins"],
    ["ibuprofen"],
    [],
    ["shellfish"],
    ["peanuts"],
    ["amoxicillin"],
    [],
    ["morphine"],
    ["erythromycin"],
    [],
    ["vancomycin"],
    ["contrast dye"],
    [],
    ["ciprofloxacin"],
]


def _random_birthdate(rng: random.Random) -> str:
    year = rng.randint(1940, 2005)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


def build_synthetic(count: int = PATIENT_COUNT) -> dict:
    """Generate `count` synthetic patient records without Synthea."""
    rng = random.Random(42)  # fixed seed → deterministic fixture
    master: dict = {}
    used_names: set[str] = set()

    for i in range(1, count + 1):
        mrn = f"MRN-{i:04d}"
        # pick a unique name
        while True:
            first = rng.choice(_FIRST_NAMES)
            last = rng.choice(_LAST_NAMES)
            full = f"{first} {last}"
            if full not in used_names:
                used_names.add(full)
                break

        idx = (i - 1) % len(_MEDICATIONS)
        master[mrn] = {
            "mrn": mrn,
            "name": full,
            "birthdate": _random_birthdate(rng),
            "gender": rng.choice(_GENDERS),
            "medications": list(_MEDICATIONS[idx]),
            "conditions": list(_CONDITIONS[idx]),
            "allergies": list(_ALLERGIES[idx]),
        }
    return master


# ---------------------------------------------------------------------------
# Synthea CSV parser
# ---------------------------------------------------------------------------

def build_from_synthea(csv_dir: pathlib.Path) -> dict:
    """Parse Synthea CSV output → master EHR dict keyed by MRN."""
    patients_csv = csv_dir / "patients.csv"
    medications_csv = csv_dir / "medications.csv"
    conditions_csv = csv_dir / "conditions.csv"
    allergies_csv = csv_dir / "allergies.csv"

    for f in [patients_csv, medications_csv, conditions_csv, allergies_csv]:
        if not f.exists():
            raise FileNotFoundError(f"Expected Synthea CSV not found: {f}")

    # Read patients
    patients: list[dict] = []
    with open(patients_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            patients.append(row)

    # Limit to PATIENT_COUNT and assign sequential MRNs
    patients = patients[:PATIENT_COUNT]
    uuid_to_mrn = {p["Id"]: f"MRN-{i:04d}" for i, p in enumerate(patients, 1)}

    def _read_by_patient(path: pathlib.Path, id_col: str, value_col: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                pid = row.get(id_col, "")
                if pid in uuid_to_mrn:
                    val = row.get(value_col, "").strip()
                    if val:
                        result.setdefault(pid, [])
                        if val not in result[pid]:
                            result[pid].append(val)
        return result

    meds = _read_by_patient(medications_csv, "PATIENT", "DESCRIPTION")
    conds = _read_by_patient(conditions_csv, "PATIENT", "DESCRIPTION")
    allergies = _read_by_patient(allergies_csv, "PATIENT", "DESCRIPTION")

    master: dict = {}
    for p in patients:
        uid = p["Id"]
        mrn = uuid_to_mrn[uid]
        first = p.get("FIRST", "Unknown")
        last = p.get("LAST", "")
        master[mrn] = {
            "mrn": mrn,
            "name": f"{first} {last}".strip(),
            "birthdate": p.get("BIRTHDATE", ""),
            "gender": p.get("GENDER", "U"),
            "medications": meds.get(uid, []),
            "conditions": conds.get(uid, []),
            "allergies": allergies.get(uid, []),
        }
    return master


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build fixtures/ehr_master.json")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--synthea", action="store_true", help="Force Synthea CSV mode")
    group.add_argument("--synthetic", action="store_true", help="Force synthetic fallback mode")
    args = parser.parse_args()

    if args.synthea:
        print(f"Building from Synthea CSV at {SYNTHEA_CSV_DIR} …")
        master = build_from_synthea(SYNTHEA_CSV_DIR)
    elif args.synthetic or not SYNTHEA_CSV_DIR.exists():
        if not args.synthetic and not SYNTHEA_CSV_DIR.exists():
            print(f"Synthea output not found at {SYNTHEA_CSV_DIR}; using synthetic mode.")
        else:
            print("Using synthetic mode (--synthetic flag).")
        master = build_synthetic(PATIENT_COUNT)
    else:
        print(f"Synthea output found at {SYNTHEA_CSV_DIR}; building from CSV …")
        master = build_from_synthea(SYNTHEA_CSV_DIR)

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_PATH, "w", encoding="utf-8") as fh:
        json.dump(master, fh, indent=2)

    print(f"Wrote {len(master)} records to {FIXTURE_PATH}")
    first_mrn = next(iter(master))
    print(f"  Sample: {first_mrn} → {master[first_mrn]['name']}")


if __name__ == "__main__":
    main()
