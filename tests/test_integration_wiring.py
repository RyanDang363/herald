"""Cross-component wiring tests (integration of the four merged feature branches).

These verify the *seams* the merged components are wired across — EHR enrichment at intake,
agent-memory record/recall in the Orchestrator, and the dashboard's Redis event-feed mapping.
Every behavior is exercised through a pure function or an injected fake so no live Bureau / Redis /
Iris is required; the live end-to-end is the separate operator run.

@spec MEM-FLOW-001 @spec MEM-FLOW-002 @spec EHR-FLOW-001 @spec EHR-FLOW-002
@spec DASH-SYS-003
"""

from __future__ import annotations

import json
import pathlib

from er_twin.agents import admissions, orchestrator
from er_twin.memory import MemoryInterface
from er_twin.storage import InMemoryStore


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeMemory(MemoryInterface):
    """Records every event + serves canned recall results, so wiring is observable in-process."""

    def __init__(self, recall_result: list[str] | None = None) -> None:
        self.events: list[str] = []
        self._recall_result = recall_result or []

    def record_event(self, text: str) -> None:
        self.events.append(text)

    def recall(self, query: str) -> list[str]:
        return list(self._recall_result)


class RaisingMemory(MemoryInterface):
    """Every call raises — proves the Orchestrator's memory seam is non-fatal (MEM-ERR-001)."""

    def record_event(self, text: str) -> None:
        raise RuntimeError("iris down")

    def recall(self, query: str) -> list[str]:
        raise RuntimeError("iris down")


def _master(tmp_path: pathlib.Path, data: dict) -> pathlib.Path:
    import er_twin.ehr as ehr_mod

    path = tmp_path / "ehr_master.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    ehr_mod._master_cache.clear()
    return path


# ---------------------------------------------------------------------------
# EHR-FLOW-001 — MRN extraction from chat text
# ---------------------------------------------------------------------------

def test_extract_mrn_finds_token():
    # @spec EHR-FLOW-001
    assert orchestrator.extract_mrn("Returning patient MRN-0007 with chest pain") == "MRN-0007"


def test_extract_mrn_normalizes_case():
    # @spec EHR-FLOW-001
    assert orchestrator.extract_mrn("patient mrn-0042 arrived") == "MRN-0042"


def test_extract_mrn_absent_returns_empty():
    # @spec EHR-FLOW-001
    assert orchestrator.extract_mrn("A new patient arrived with chest pain") == ""


# ---------------------------------------------------------------------------
# EHR-FLOW-002 — AdmissionsAgent enriches the record from the EHR at intake
# ---------------------------------------------------------------------------

def test_intake_enriches_returning_patient_history(tmp_path):
    # @spec EHR-FLOW-002
    _master(tmp_path, {
        "MRN-0001": {
            "mrn": "MRN-0001", "name": "Jordan Lee", "medications": ["warfarin"],
            "conditions": ["atrial fibrillation"], "allergies": ["penicillin"],
        }
    })
    store = InMemoryStore()
    pid, record, created = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, mrn="MRN-0001"
    )
    assert created is True
    assert record["mrn"] == "MRN-0001"
    assert record["new_patient"] is False
    assert record["history"]["medications"] == ["warfarin"]
    assert record["status"] == "waiting"
    # Enrichment is persisted to the live hash, not just returned.
    assert store.get(f"er:patient:{pid}")["history"]["conditions"] == ["atrial fibrillation"]


def test_intake_mints_mrn_for_walkin(tmp_path):
    # @spec EHR-FLOW-002
    _master(tmp_path, {})
    store = InMemoryStore()
    _, record, _ = admissions.intake(store, "New Walker", "ankle injury", {})
    assert record["mrn"] == "MRN-0001"  # minted from empty master
    assert record["new_patient"] is True


def test_intake_dedupes_by_mrn(tmp_path):
    # @spec EHR-FLOW-002 — a returning MRN already active in the ER dedupes to the existing patient.
    _master(tmp_path, {"MRN-0001": {"mrn": "MRN-0001", "name": "Jordan Lee"}})
    store = InMemoryStore()
    pid1, _, c1 = admissions.intake(store, "Jordan Lee", "chest pain", {}, mrn="MRN-0001")
    # Same MRN, *different* complaint → still the same active patient, no second record.
    pid2, _, c2 = admissions.intake(store, "Jordan Lee", "follow-up", {}, mrn="MRN-0001")
    assert c1 is True and c2 is False
    assert pid1 == pid2
    assert store.list_ids("patient") == [pid1]


def test_intake_name_dedupe_still_works_without_mrn(tmp_path):
    # @spec INTAKE-IDEM-001 — the existing name+complaint fallback must survive EHR wiring.
    _master(tmp_path, {})
    store = InMemoryStore()
    pid1, _, c1 = admissions.intake(store, "Sam Rivera", "ankle sprain", {})
    pid2, _, c2 = admissions.intake(store, "Sam Rivera", "ankle sprain", {})
    assert c1 is True and c2 is False
    assert pid1 == pid2
    assert store.list_ids("patient") == [pid1]


# ---------------------------------------------------------------------------
# MEM-FLOW-001 / MEM-ERR-001 — record_event seam is wired + non-fatal
# ---------------------------------------------------------------------------

def test_record_memory_appends_event():
    # @spec MEM-FLOW-001
    fake = FakeMemory()
    orchestrator.set_memory(fake)
    try:
        orchestrator._record_memory(_DummyCtx(), "Admitted Jordan Lee (chest pain). ESI-2.")
        assert fake.events == ["Admitted Jordan Lee (chest pain). ESI-2."]
    finally:
        orchestrator.set_memory(_NOOP)


def test_record_memory_swallows_backend_error():
    # @spec MEM-ERR-001 — a memory backend failure must never crash a command.
    orchestrator.set_memory(RaisingMemory())
    try:
        orchestrator._record_memory(_DummyCtx(), "anything")  # must not raise
    finally:
        orchestrator.set_memory(_NOOP)


# ---------------------------------------------------------------------------
# MEM-FLOW-002 — summary folds recalled facts (and stays unchanged under empty recall)
# ---------------------------------------------------------------------------

def _summary_store() -> InMemoryStore:
    store = InMemoryStore()
    store.set("er:patient:p1", {"id": "p1", "name": "Avery Chen", "status": "in_treatment", "acuity": 3})
    store.set("er:bed:bed3", {"id": "bed3", "status": "occupied"})
    store.set("er:nurse:nurse2", {"id": "nurse2", "available": True})
    return store


def test_compose_summary_folds_recalled_context():
    # @spec MEM-FLOW-002
    store = _summary_store()
    out = orchestrator.compose_summary(store, [], ["earlier: Jordan Lee admitted ESI-2"])
    assert "Recent context: earlier: Jordan Lee admitted ESI-2." in out


def test_compose_summary_unchanged_when_no_recall():
    # @spec MEM-FLOW-002 — NoopMemory returns [] → template path is byte-identical (no regression).
    store = _summary_store()
    base = orchestrator.build_status_summary(store, [])
    assert orchestrator.compose_summary(store, [], []) == base


# ---------------------------------------------------------------------------
# ORCH-LLM-001 / ORCH-LLM-002 — ASI:One intent resolution + graceful fallback
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


@pytest.mark.parametrize("raw,expected", [
    ("intake", "intake"),
    ("oxygen", "oxygen"),
    ("summary", "summary"),
    ("ping", "ping"),
    ("unknown", "unknown"),
    ("The user wants a status summary.", "summary"),  # tolerant of a wrapped token
    ("intent: oxygen", "oxygen"),
])
def test_parse_llm_intent_maps_known_tokens(raw, expected):
    # @spec ORCH-LLM-001
    assert orchestrator._parse_llm_intent(raw) == expected


def test_parse_llm_intent_raises_on_garbage():
    # @spec ORCH-LLM-001 — unrecognizable reply raises so resolve_command can fall back.
    with pytest.raises(ValueError):
        orchestrator._parse_llm_intent("I have no idea what you mean")


def test_resolve_via_llm_raises_without_key(monkeypatch):
    # @spec ORCH-LLM-002 — no key → raise (never silently call ASI:One); resolve_command falls back.
    import er_twin.config as cfg

    monkeypatch.setattr(cfg.settings, "asione_api_key", "")
    with pytest.raises(RuntimeError):
        orchestrator._resolve_via_llm("A new patient arrived with chest pain")


def test_resolve_command_falls_back_to_mock_on_llm_error(monkeypatch):
    # @spec ORCH-LLM-002 — live mode, but the LLM errors → deterministic keyword lookup still resolves.
    import er_twin.config as cfg

    monkeypatch.setattr(cfg.settings, "use_mock", False)
    monkeypatch.setattr(orchestrator, "_resolve_via_llm", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))
    assert orchestrator.resolve_command("A new patient arrived with chest pain") == "intake"


# ---------------------------------------------------------------------------
# ORCH-CHAT-002 — ASI:One prepends a routing mention; strip it so downstream
# exact-match lookups (MOCK_INTAKE) and anchored parsers (is_confirm) see the
# operator's actual words. The mention is the agent's *handle* — either the raw
# "@agent1..." address or a human handle like "@er-herald" set on Agentverse.
# ---------------------------------------------------------------------------

_ADDR = "agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w"


@pytest.mark.parametrize("raw, expected", [
    (f"@{_ADDR} A new patient arrived with chest pain", "A new patient arrived with chest pain"),
    (f"  @{_ADDR}   Show me what's happening in the ER", "Show me what's happening in the ER"),
    ("A new patient arrived with chest pain", "A new patient arrived with chest pain"),  # no mention → no-op
    (f"@{_ADDR} ", ""),  # mention only
    ("@er-herald confirm", "confirm"),  # human handle (Agentverse) — not just the raw address
    ("@er-herald patient MRN-0006 admitted with chest pain", "patient MRN-0006 admitted with chest pain"),
])
def test_strip_agent_mention(raw, expected):
    # @spec ORCH-CHAT-002 — leading uAgents routing mention removed; otherwise text untouched.
    assert orchestrator.strip_agent_mention(raw) == expected


def test_strip_agent_mention_is_idempotent():
    # @spec ORCH-CHAT-002 — applying twice equals applying once (no accidental double-strip).
    once = orchestrator.strip_agent_mention(f"@{_ADDR} A new patient arrived with chest pain")
    assert orchestrator.strip_agent_mention(once) == once


def test_strip_agent_mention_keeps_non_agent_at_sign():
    # @spec ORCH-CHAT-002 — only a *leading* "@handle " mention is routing noise; a stray mid-text '@' stays.
    assert orchestrator.strip_agent_mention("email me @ noon about chest pain") == "email me @ noon about chest pain"


def test_is_confirm_handles_human_handle_mention():
    # @spec ORCH-CHAT-002 — "confirm" must parse even when ASI:One prepends the "@er-herald" handle,
    # otherwise the proposal re-prompts forever. (Regression: anchored is_confirm vs leading mention.)
    from er_twin.events.helpers import is_confirm

    assert is_confirm("@er-herald confirm")
    assert is_confirm("confirm")
    assert not is_confirm("@er-herald assign doc1 nurse2 bed3")


# ---------------------------------------------------------------------------
# ORCH-SYS-003 — a confirm-stage proposal must not wedge the session: a brand-new
# command (MRN + admit/discharge verb) supersedes it instead of being read as a
# bad "confirm" and re-prompting forever.
# ---------------------------------------------------------------------------

def _confirm_pending(kind="intake_confirm", event_type="intake"):
    from er_twin.events.base import PendingProposal

    return PendingProposal(kind=kind, event_type=event_type, sender="s", session_id="sid", mrn="MRN-0006")


@pytest.mark.parametrize("text", [
    "patient MRN-0006 admitted with complaint of chest pain",  # the 12:45 wedge: re-issued admit
    "admit patient MRN-0007 to bed1",
    "discharge MRN-0006",                                       # changed mind mid-proposal
])
def test_new_command_supersedes_confirm_proposal(text):
    # @spec ORCH-SYS-003 — a fresh MRN command abandons the stale proposal and dispatches anew.
    assert orchestrator._supersedes_pending(text, _confirm_pending()) is True


@pytest.mark.parametrize("text", [
    "confirm",                       # a real confirm
    "assign doc1 nurse2 bed3",       # a valid override
    "summary",                       # no MRN — not a new patient command
    "MRN-0006",                      # bare MRN, no admit/discharge verb
])
def test_confirm_and_override_do_not_supersede(text):
    # @spec ORCH-SYS-003 — the happy path (confirm / override / unrelated) still flows to the handler.
    assert orchestrator._supersedes_pending(text, _confirm_pending()) is False


@pytest.mark.parametrize("kind", ["awaiting_mrn", "awaiting_complaint"])
def test_data_gathering_stages_are_never_superseded(kind):
    # @spec ORCH-SYS-003 — replies that fill in MRN/complaint may keyword-collide; never supersede them.
    assert orchestrator._supersedes_pending("admit MRN-0006 chest pain", _confirm_pending(kind=kind)) is False


@pytest.mark.parametrize("text", [
    "A new patient arrived with chest pain",
    "a new patient arrived with chest pain please",  # casing + trailing words
    f"@{_ADDR} A new patient arrived with chest pain",  # backstop: mention survived
])
def test_lookup_mock_intake_finds_jordan_lee(text):
    # @spec INTAKE-FLOW-001 — the chest-pain trigger selects the Jordan Lee payload, never "Unknown Patient".
    data = orchestrator.lookup_mock_intake(text)
    assert data is not None and data["name"] == "Jordan Lee"


def test_lookup_mock_intake_returns_none_for_unrelated_text():
    # @spec INTAKE-FLOW-001 — unrelated text has no canned payload (caller falls back to Unknown Patient).
    assert orchestrator.lookup_mock_intake("what's the weather") is None


# ---------------------------------------------------------------------------
# DASH-SYS-003 — er:events stream line → dashboard display row
# ---------------------------------------------------------------------------

def test_dashboard_event_row_maps_replay_line():
    # @spec DASH-SYS-003
    from dashboard.datasource import _event_row

    line = {
        "seq": 3, "event": "intake", "actor": "bed", "action": "bed_assigned",
        "target": "bed1", "detail": {"patient": "p3"},
    }
    row = _event_row("1718900000000-0", line)
    assert set(row) >= {"ts", "event", "detail"}
    assert row["event"] == "intake"
    assert "bed_assigned" in row["detail"]
    assert "bed1" in row["detail"]
    assert "patient=p3" in row["detail"]


# ---------------------------------------------------------------------------
# Test fixtures / shims
# ---------------------------------------------------------------------------

class _DummyCtx:
    """Minimal Context stand-in exposing only `logger` (with the methods the seam touches)."""

    class _Log:
        def exception(self, *a, **k):
            pass

        def info(self, *a, **k):
            pass

    logger = _Log()


from er_twin.memory import NoopMemory as _NoopCls  # noqa: E402

_NOOP = _NoopCls()


# ---------------------------------------------------------------------------
# Seeding hardening — ensure_seeded verifies the inventory actually landed, and
# find_available_bed must not treat a missing/empty bed record as available.
# (Closes the gap where a partially-seeded RedisStore silently degrades every
#  intake to no_bed_available while the boot log still looks healthy.)
# ---------------------------------------------------------------------------

from er_twin import main as _main  # noqa: E402
from er_twin.agents import bed as _bed  # noqa: E402


def test_ensure_seeded_reports_full_inventory():
    # @spec INTAKE-FLOW-006 — a freshly seeded store reports beds + nurses (and the rest) present.
    store = InMemoryStore()
    counts = _main.ensure_seeded(store)
    assert counts["bed"] == len(_bed.BEDS) and counts["bed"] > 0
    assert counts["nurse"] > 0 and counts["doctor"] > 0 and counts["equipment"] > 0


def test_ensure_seeded_is_idempotent():
    # @spec INTAKE-FLOW-006 — re-seeding doesn't multiply or drop inventory (safe on every boot).
    store = InMemoryStore()
    first = _main.ensure_seeded(store)
    second = _main.ensure_seeded(store)
    assert first == second


def test_ensure_seeded_self_heals_missing_beds():
    # @spec INTAKE-ERR-002 — if beds are wiped out from under the store, ensure_seeded restores them.
    store = InMemoryStore()
    _main.ensure_seeded(store)
    for bid in list(_bed.BEDS):
        store.set(_bed.bed_key(bid), {})  # simulate a cleared/partial backend
    # find_available_bed must NOT see those empty records as usable...
    assert _bed.find_available_bed(store, "cardiology") is None
    # ...and a re-seed restores a usable bed.
    counts = _main.ensure_seeded(store)
    assert counts["bed"] == len(_bed.BEDS)
    assert _bed.find_available_bed(store, "cardiology") is not None


def test_find_available_bed_ignores_missing_records():
    # @spec INTAKE-ERR-002 — empty/missing bed hash is never selectable (regression guard).
    store = InMemoryStore()
    store.set(_bed.bed_key("bed1"), {})  # exists in index but no fields → not a real bed
    assert _bed.find_available_bed(store, "cardiology") is None
    assert _bed.find_available_bed(store, "general") is None
