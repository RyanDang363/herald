"""Unit tests for the Phase 1 single-process Bureau skeleton (ORCH-* specs).

These exercise the *pure*, unit-testable seams of the Orchestrator — intent resolution, the mock
lookup, LLM-error fallback, session→sender correlation, and command serialization — without booting
a live Bureau / mailbox (that path is proven by spikes/mailbox_inside_bureau_spike.py and verified
manually). Each test traces to an EARS spec id.
"""

import pytest

from er_twin.agents import orchestrator as orch


# --- Intent resolution: USE_MOCK hardcoded lookup (ORCH-LLM-003) ---


def test_resolve_intent_ping():
    # @spec ORCH-LLM-003
    assert orch.resolve_intent("ping") == "ping"


def test_resolve_intent_intake():
    # @spec ORCH-LLM-003
    assert orch.resolve_intent("A new patient arrived with chest pain") == "intake"


def test_resolve_intent_oxygen():
    # @spec ORCH-LLM-003
    assert orch.resolve_intent("Bed 3's patient oxygen is dropping") == "oxygen"


def test_resolve_intent_summary():
    # @spec ORCH-LLM-003
    assert orch.resolve_intent("Show me what's happening in the ER") == "summary"


def test_mock_replies_match_team_contract():
    # @spec ORCH-LLM-003 — registry-driven mock replies for no-store fallback.
    assert "MRN" in orch.MOCK_REPLIES["intake"]
    assert (
        orch.MOCK_REPLIES["oxygen"]
        == "Low O2 on bed-3 (88%). Dispatched nurse-2 with replacement unit o2-2. ETA ~15s."
    )
    assert (
        orch.MOCK_REPLIES["summary"]
        == "3 patients active, 2 beds occupied, 1 nurse free. No critical alerts."
    )


# --- Unknown intent → clarify, no dispatch (ORCH-LLM-004) ---


def test_resolve_intent_unknown():
    # @spec ORCH-LLM-004
    assert orch.resolve_intent("what's the weather like in Paris") == "unknown"


def test_unknown_intent_clarifies_no_dispatch():
    # @spec ORCH-LLM-004
    intent = orch.resolve_intent("gibberish that maps to nothing")
    assert intent == "unknown"
    # Unknown is neither the ping dispatch path nor a known mock reply -> nothing to dispatch.
    assert intent != "ping"
    assert intent not in orch.MOCK_REPLIES
    # A non-empty clarifying message is available to return to chat.
    assert orch.CLARIFICATION.strip()


# --- LLM enablement & fallback (ORCH-LLM-002 / ORCH-LLM-003) ---


def test_use_mock_skips_llm(monkeypatch):
    # @spec ORCH-LLM-003
    def _boom(_text):
        raise AssertionError("ASI:One must not be called when USE_MOCK is enabled")

    monkeypatch.setattr(orch.settings, "use_mock", True)
    monkeypatch.setattr(orch, "_resolve_via_llm", _boom)
    assert orch.resolve_command("ping") == "ping"


def test_llm_error_falls_back_to_mock(monkeypatch):
    # @spec ORCH-LLM-002
    def _boom(_text):
        raise RuntimeError("simulated ASI:One timeout / rate-limit")

    monkeypatch.setattr(orch.settings, "use_mock", False)
    monkeypatch.setattr(orch, "_resolve_via_llm", _boom)
    # The LLM call errors; the Orchestrator must not crash and falls back to the mock lookup.
    assert orch.resolve_command("A new patient arrived with chest pain") == "intake"


# --- Session→sender correlation (ORCH-SKEL-001 async pattern) ---


def test_session_sender_correlation():
    # @spec ORCH-SKEL-001
    senders = orch.SessionSenders()
    assert senders.recall("session-x") is None  # nothing remembered yet
    senders.remember("session-x", "agent1qUSER")
    assert senders.recall("session-x") == "agent1qUSER"
    senders.forget("session-x")
    assert senders.recall("session-x") is None  # forgotten after relay


# --- Command serialization (ORCH-SYS-003) ---


def test_command_gate_defers_until_terminal_reply():
    # @spec ORCH-SYS-003 — the gate holds one command active across its FULL lifecycle (until its
    # terminal reply frees it), not just around dispatch. A command arriving while busy is deferred
    # (queued) and only runs once the active one finishes.
    gate = orch.CommandGate()
    assert gate.is_busy() is False

    gate.start("chat-1")
    assert gate.is_busy() is True and gate.active() == "chat-1"

    queued = orch.PendingChatCommand(sender="agent1q...", session_id="s2", text="ping")
    gate.enqueue(queued)
    assert gate.pop_next() is None  # still busy -> the deferred command does not run yet

    gate.finish("chat-1")  # terminal reply produced -> gate frees
    assert gate.is_busy() is False
    assert gate.pop_next() is queued  # now the deferred command can run
    assert gate.pop_next() is None  # queue drained


def test_command_gate_finish_ignores_stale_flow():
    # @spec ORCH-SYS-003 — a late watchdog/finalizer for a replaced flow must not free a newer command.
    gate = orch.CommandGate()
    gate.start("chat-1")
    gate.finish("chat-OLD")
    assert gate.is_busy() is True and gate.active() == "chat-1"
    gate.finish("chat-1")
    assert gate.is_busy() is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
