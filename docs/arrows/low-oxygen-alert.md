# Arrow: low-oxygen-alert

Event 2 — the mandatory **real-async-messaging** showcase. A scripted chat command makes the bed-3
oxygen unit's EquipmentAgent drop its own supply below threshold and **autonomously emit**
`LowSupplyAlert`; the Orchestrator then handles alert → locate → dispatch → swap across separate
`@on_message` handlers, correlating the multi-hop flow manually (uAgents does not carry a session
across hops). This is the Fetch.ai "agents messaging agents" proof — distinct from intake, which is
in-process by decision.

## Status

**OK** — 2026-06-20. Phase 4 complete and green: 9 oxygen tests + 42 prior = 51/51 pass,
`ruff check .` clean, 18 agents boot. The agent-to-agent chain is verified end-to-end through a live
Bureau by [spikes/oxygen_async_flow_spike.py](../../spikes/oxygen_async_flow_spike.py) (exit 0; logs
`alert_raised → unit_located → nurse2 accepts → oxygen_swap_complete` and the resolved chat line). All
9 active OXY-* specs `[x]`.

_Mapped + audited in one pass (Phase 4 landed this session). HLD (README) SHA `8e87478` unchanged
since the OK arrows were audited — same upstream._

## References

| Type | Location |
|------|----------|
| HLD — Event 2, push-based equipment alert | [README.md](../../README.md) |
| LLD — §3 Event-2 contracts + Gap-4 trigger note, §6 in-flight O2 dispatch, §2 Equipment/Nurse | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| Decisions — Gap 4 (R1 simulate-trigger), R2-C swap, R2-D in-flight, R2-E locate; async mandate | [Round 1](../decisions/2026-06-20-event-flow-decisions.md) · [Round 2](../decisions/2026-06-20-round-2-event-mechanics.md) · [intake-orchestration-mode](../decisions/2026-06-20-intake-orchestration-mode.md) |
| EARS — 9 active OXY-* specs | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_event_oxygen.py](../../tests/test_event_oxygen.py) (9) |
| Code | [equipment.py](../../er_twin/agents/equipment.py) (`simulate_oxygen_drop`/`locate_replacement`/`swap_oxygen_unit` + handlers), [nurse.py](../../er_twin/agents/nurse.py) (`dispatch_nurse` + handler), [orchestrator.py](../../er_twin/agents/orchestrator.py) (`on_low_supply`/`on_locate`/`on_dispatch`, `apply_oxygen_swap`, `should_start_o2_dispatch`, chat oxygen branch) |
| Proof | [spikes/oxygen_async_flow_spike.py](../../spikes/oxygen_async_flow_spike.py) |

## Architecture

**Purpose:** Detect a depleting oxygen unit (pushed by the unit's own agent), locate a same-type
replacement, dispatch a nurse, and atomically swap the unit — restoring the patient's SpO2 — then
confirm to chat. Idempotent against duplicate alerts.

**Key Components / flow:**
1. **Chat trigger (OXY-FLOW-007):** `orchestrator.handle_chat` oxygen branch resolves the bed →
   `equipment.oxygen_unit_at_bed` → sends `SimulateOxygenDropRequest` to `address_for(o2_1)`.
2. **Autonomous push (OXY-FLOW-007→001):** the o2_1 EquipmentAgent's `_make_simulate_handler` calls
   pure `simulate_oxygen_drop` (supply→45, patient spo2→88) then `ctx.send(ORCHESTRATOR_ADDRESS,
   LowSupplyAlert(...))` — the unit emits its own alert.
3. **Locate (OXY-FLOW-002/003):** `on_low_supply` registers the in-flight dispatch, selects a
   replacement via pure `locate_replacement` (R2-E: same-type, `supply ≥ 50`, highest-supply then id
   → o2_2), and sends `EquipmentLocateRequest` to that unit, which confirms via `_make_locate_handler`
   (`is_available`).
4. **Dispatch (OXY-FLOW-004):** `on_locate` finds an available nurse (`find_available_nurse` → nurse2,
   nurse1 pre-busy) and sends `StaffDispatchRequest`; the nurse accepts via `_make_dispatch_handler`.
5. **Swap (OXY-FLOW-005, R2-C):** `on_dispatch` → `apply_oxygen_swap` = `equipment.swap_oxygen_unit`
   (o2_2 in-use at bed-3; o2_1 freed + `needs_restock`; bed equipment list; patient spo2→96) +
   `nurse.dispatch_nurse` (nurse2 unavailable, relocated to bed-3).
6. **Confirm (OXY-FLOW-006):** `format_oxygen_confirmation` via `_reply_oxygen` back to the chat user.

**Correlation:** a `flow_id` is threaded through every oxygen message; per-flow context lives in
`oxygen_flows: dict[flow_id, OxygenFlow]` (bed, depleted/replacement unit, nurse, originating chat
session). Each response handler looks up its flow by `flow_id` — a response for an unknown or already-
`done` flow is a no-op — so overlapping or autonomous alerts coexist without clobbering one another.
`_session_senders` routes the final reply to the originating chat user; chat-triggered flows occupy the
full-lifecycle `CommandGate` (ORCH-SYS-003), autonomous alerts run ungated.

**Idempotency (OXY-IDEM-001, R2-D):** `in_flight_o2_dispatches: {equipment_id → flow_id}` (the bed is
`oxygen_flows[flow_id].bed_id`); `should_start_o2_dispatch` blocks a second dispatch for a unit already
in flight; cleared only after swap + chat reply (clear-on-completion).

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Flow | OXY-FLOW-001..007 | 7 | 0 | 0 |
| Errors | OXY-ERR-001 | 1 | 0 | 0 |
| Idempotency | OXY-IDEM-001 | 1 | 0 | 0 |

**Summary:** 9 of 9 active OXY specs implemented + tested. Transport is genuine async uAgent messaging
(not in-process) — the project's agent-to-agent proof.

## Key Findings

1. **Autonomy is real, not synthesized** — the depleting unit's own agent emits `LowSupplyAlert`; the
   Orchestrator never fabricates it. The scripted `SimulateOxygenDropRequest` only nudges supply down
   (Gap 4), preserving the autonomous-agent model.
2. **Select-then-confirm locate** — the Orchestrator pre-selects the replacement via the pure
   `locate_replacement` (deterministic R2-E sort), then asks that unit's agent to confirm
   availability (OXY-FLOW-003). Honest async without nondeterministic broadcast/collection over all
   units; `near_location` stays advisory.
3. **Cross-entity swap stays in the Orchestrator** — `apply_oxygen_swap` composes entity pure
   functions (equipment + nurse), mirroring `run_intake`'s ownership of multi-entity transitions.
4. **Pure-function + thin-handler split** — all logic (`simulate_oxygen_drop`, `locate_replacement`,
   `swap_oxygen_unit`, `dispatch_nurse`, `should_start_o2_dispatch`) is unit-tested against an
   `InMemoryStore`; the live async wiring is proven separately by the spike (Bureau-in-pytest is flaky
   on Windows).

## Work Required

### Must Fix
_None — all OXY specs implemented + tested; async chain proven end-to-end._

### Should Fix
_None — the concurrency hardening (formerly GAP 2) was completed this session:_ `_oxygen_ctx` was
replaced with a `flow_id`-keyed `oxygen_flows: dict[flow_id, OxygenFlow]` registry; every oxygen
message carries a `flow_id` (LLD §3); `on_locate`/`on_dispatch` treat a response for an unknown or
already-`done` flow as a no-op; `equipment.swap_oxygen_unit` is idempotent (no-op if the bed already
holds the replacement). Overlapping or autonomous alerts now run independent contexts and cannot clobber
each other. Shares the `flow_id` with the `orchestrator-skeleton` lifecycle-gate fix. Covered by
`test_oxygen_swap_is_idempotent` + the threaded-`flow_id` spike run (`flow=spike-1` through to
`oxygen_swap_complete`). (Select-then-confirm locate stays as-is; broadcast/collect is not needed.)

### Nice to Have
1. Replay milestone lines (`oxygen_drop_simulated`, `alert_raised`, `unit_located`,
   `nurse_dispatched`, `oxygen_swap_complete`, `oxygen_event_complete` + failure milestones, R2-G)
   are logged via `ctx.logger` but not yet published to `er:events` — wired in Phase R.
2. Manual chat run of *"Bed 3's patient oxygen is dropping"* needs the one-time Agentverse inspector
   mailbox connect; the spike already proves the in-Bureau message chain.
