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


def pool_address(role: str, index: int) -> str:
    """Address for one member of an entity pool, e.g. pool_address('bed', 1)."""
    return address_for(f"{role}-{index}")
