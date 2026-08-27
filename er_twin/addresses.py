"""Deterministic agent addresses derived from the base seed (LLD section 5).

Computed once at import time and used as constants — no runtime Almanac discovery. Each agent's
seed is `{AGENT_SEED}-{role}`; entity pools append an index, e.g. `bed-1`.
"""

from uagents.crypto import Identity

from er_twin.config import settings


def seed_for(role: str) -> str:
    return f"{settings.agent_seed}-{role}"


def address_for(role: str) -> str:
    return Identity.from_seed(seed_for(role), 0).address


# Singleton agents referenced across the system.
ORCHESTRATOR_ADDRESS = address_for("orchestrator")
STUB_ADDRESS = address_for("stub")
ADMISSIONS_ADDRESS = address_for("admissions")
TRIAGE_ADDRESS = address_for("triage")


def bed_address(bed_id: str) -> str:
    """Address for a specific bed agent, e.g. bed_address('bed1')."""
    return address_for(bed_id)


def nurse_address(nurse_id: str) -> str:
    """Address for a specific nurse agent, e.g. nurse_address('nurse1')."""
    return address_for(nurse_id)


def doctor_address(doctor_id: str) -> str:
    """Address for a specific doctor agent, e.g. doctor_address('doc1')."""
    return address_for(doctor_id)


def patient_agent_address(slot: int) -> str:
    """Address for a specific patient pool agent, e.g. patient_agent_address(1)."""
    return address_for(f"patient-{slot}")
