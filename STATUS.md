# STATUS — ER Twin

Live progress tracker. Update as phases complete. See
[implementation plan](docs/plans/2026-06-20-er-twin-core.plan.md) for detail.

**Current blocker:** _none — Phase 0 in progress_

## Phases

| Phase | Description | Owner | Status |
|---|---|---|---|
| 0 | Scaffold & contracts (`protocols`, `config`, `storage`, `addresses`) | done | **complete** |
| 1 | Bureau + Orchestrator skeleton (chat ping loop, `USE_MOCK`) | agents dev | not started |
| 2 | Entity agents + state + domain invariants | agents dev | not started |
| 3 | Event 1 — Patient intake | agents dev | not started |
| 4 | Event 2 — Low oxygen alert | agents dev | not started |
| 5 | Event 3 — Status summary | agents dev | not started |
| 6 | Redis swap (`RedisStore`), demo scripting | redis dev | not started |
| Stretch | Dashboard (FastAPI + HTML) | dashboard dev | not started |
| Stretch | Pika incident replay | agents dev | not started |

## Demo readiness checklist

- [ ] All 3 events fire end-to-end from a single chat command each
- [ ] `USE_MOCK=true` runs the full demo with no external API calls
- [ ] `.env.example` present; no secrets committed
- [ ] Demo trigger phrases rehearsed (see `docs/TEAM.md` USE_MOCK contract)
