# Arrow: dashboard

Read-only admin dashboard UI, API, auth gate, and demo simulation around ER state.

## Status

**OK** - 2026-06-21 (HLD SHA `8e87478`, reconciled from pre-integration `79e8a57`). Fixture/sim dashboard, auth gate, and UI were already done; the live Redis snapshot (`DASH-SYS-002`) and `er:events` stream read (`DASH-SYS-003`) landed 2026-06-21 and are verified live. `DASH-IN-001` remains intentionally deferred.

> **Shared with `incident-replay` (R+, 2026-06-21).** The data-driven replay layer (LLD §9.1) added `/replay`, `/api/replay`, `/library`, `/api/library` routes to `dashboard/server.py` and `floor.js`/`replay.{html,js}`/`library.{html,js}` under `static/` — those carry `REPLAY-*` specs (owned by `incident-replay`), **not** `DASH-*`. `app.js` was refactored to source floor geometry from the new shared `floor.js` (`window.Floor`) with **no behavior change** (verified by screenshot + the existing `test_dashboard.py` suite still green), so all `DASH-*` specs are unaffected. The README delta that bumped `incident-replay`'s `hld_sha` to `772888f` is the additive §9.1 subsection only; this arrow's next audit will reconcile the SHA but find no `DASH-*` impact.

## References

| Type | Location |
|------|----------|
| HLD — stretch dashboard sections | [README.md](../../README.md) |
| LLD | [docs/llds/dashboard.lld.md](../llds/dashboard.lld.md) |
| EARS — 32 active specs | [docs/specs/dashboard-specs.md](../specs/dashboard-specs.md) |
| Tests | [tests/test_dashboard.py](../../tests/test_dashboard.py) |
| Code | [dashboard/server.py](../../dashboard/server.py), [dashboard/datasource.py](../../dashboard/datasource.py), [dashboard/sim.py](../../dashboard/sim.py), [dashboard/static/index.html](../../dashboard/static/index.html), [dashboard/static/app.js](../../dashboard/static/app.js), [dashboard/static/style.css](../../dashboard/static/style.css) |

## Architecture

**Purpose:** Provide a live operational surface over ER state with a demo-safe access gate and standalone fixture/simulation modes.

**Key Components:**
1. `server.py` — FastAPI routes, session auth, and optional Google OAuth.
2. `datasource.py` — snapshot assembly, derived summary, fixture/bootstrap event data, and source switching.
3. `sim.py` — scripted timeline for standalone demo playback.
4. `static/` — polling UI, live feedback, and inline detail rail interactions.

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| API | DASH-API-001 to DASH-API-004 | 4 | 0 | 0 |
| System / data source | DASH-SYS-001 to DASH-SYS-004 | 4 | 0 | 0 |
| UI | DASH-UI-001 to DASH-UI-008 | 8 | 0 | 0 |
| Simulation | DASH-SIM-001 to DASH-SIM-002 | 2 | 0 | 0 |
| Error handling | DASH-ERR-001 to DASH-ERR-003 | 3 | 0 | 0 |
| Authentication | DASH-AUTH-001 to DASH-AUTH-010 | 10 | 0 | 0 |
| Input | DASH-IN-001 to DASH-IN-002 | 1 | 1 | 0 |

**Summary:** 31 of 32 active specs implemented; 1 deferred (`DASH-IN-001`); 0 active gaps.

## Key Findings

1. **Dashboard behavior is coherent and test-backed** — [tests/test_dashboard.py](../../tests/test_dashboard.py) covers auth, API, simulation, and read-only behavior against the current server/datasource implementation.
2. **Live Redis path landed 2026-06-21** — `DASH-SYS-002` (snapshot via `get_store()` → `RedisStore`) and `DASH-SYS-003` (`current_events()` → `_redis_events()` reads the `er:events` Stream with XREVRANGE, mapped to `{ts, event, detail}` rows) are now implemented in [dashboard/datasource.py](../../dashboard/datasource.py). Verified live: 4 intake milestone lines read back from the same Redis the agents write. Set `DASHBOARD_SOURCE=redis` to share the agents' store. `_redis_events` degrades to an empty feed on any connection/parse error (never 500s the endpoint).
3. **Input remains intentionally deferred** — the seam exists in [dashboard/orchestrator_client.py](../../dashboard/orchestrator_client.py) and [dashboard/server.py](../../dashboard/server.py), but `DASH-IN-001` is correctly still deferred rather than drifted.

## Work Required

### Should Fix
1. Add frontend-level tests or lightweight browser checks for the inline detail rail and card-selection behavior in the dashboard UI.

### Nice to Have
1. Extend the inline detail interaction to beds/equipment.
2. `_redis_events` polls via XREVRANGE per `/api/events` request; if the feed ever needs push semantics, add a server-side poller into the existing `EventBuffer` ring.

