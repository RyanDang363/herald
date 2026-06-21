"""FastAPI server for the read-only admin dashboard.

@spec DASH-API-001, DASH-API-002, DASH-API-003, DASH-API-004, DASH-ERR-001, DASH-IN-002
@spec DASH-AUTH-001, DASH-AUTH-002, DASH-AUTH-003, DASH-AUTH-004, DASH-AUTH-005, DASH-AUTH-006
@spec DASH-AUTH-007, DASH-AUTH-008

Run: uvicorn dashboard.server:app --port 8050

Auth note: session-cookie login via Google OAuth (any account — no allowlist) or a hardcoded
username/password fallback. A demo access gate, NOT real HIPAA compliance (the project uses
synthetic data; production compliance is out of scope).
"""

import json
import re
from datetime import datetime
from pathlib import Path

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from er_twin.config import settings

from . import pika_jobs
import dashboard.datasource as datasource
from .datasource import active_events_list, current_events, derive_summary, live_snapshot

_STATIC = Path(__file__).parent / "static"

# Incident replay artifacts written by the Orchestrator (er_twin.replay, LLD §9.1). Resolved relative
# to the repo root so the dashboard reads the same out/replay/ the agents write, regardless of CWD.
_REPLAY_DIR = Path(__file__).parent.parent / "out" / "replay"
# Incident ids are `{incident_type}-{n:04d}` — a strict allowlist also blocks path traversal.
_INCIDENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _replay_file(incident_id: str) -> Path | None:
    """The `out/replay/{incident_id}.json` path if it exists and the id is safe, else None."""
    if not _INCIDENT_ID_RE.fullmatch(incident_id):
        return None
    path = _REPLAY_DIR / f"{incident_id}.json"
    return path if path.is_file() else None

app = FastAPI(title="ER Twin — Admin Dashboard")
app.add_middleware(SessionMiddleware, secret_key=settings.dashboard_secret_key)
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Google OAuth is registered only when credentials are configured (graceful degradation).
oauth = OAuth()
GOOGLE_ENABLED = bool(settings.google_client_id and settings.google_client_secret)
if GOOGLE_ENABLED:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

_last_good: dict | None = None


# --- Auth ---------------------------------------------------------------------


def current_user(request: Request) -> str | None:
    return request.session.get("user")


def require_api(request: Request) -> str:
    """Dependency: protected API routes return 401 when unauthenticated. @spec DASH-AUTH-004"""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(_STATIC / "login.html")


@app.post("/login")
async def login(request: Request) -> RedirectResponse:
    """Validate hardcoded credentials and establish a session. @spec DASH-AUTH-001, DASH-AUTH-002"""
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))
    if username == settings.dashboard_username and password == settings.dashboard_password:
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/auth/config")
def auth_config() -> JSONResponse:
    """Lets the login page show the Google button only when configured. @spec DASH-AUTH-007"""
    return JSONResponse({"google_enabled": GOOGLE_ENABLED})


@app.get("/auth/google")
async def auth_google(request: Request):
    """Begin the Google OAuth flow. @spec DASH-AUTH-007"""
    if not GOOGLE_ENABLED:
        return RedirectResponse("/login?error=oauth_unconfigured", status_code=303)
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Complete OAuth: any authenticated Google account is allowed in. @spec DASH-AUTH-007, DASH-AUTH-008"""
    if not GOOGLE_ENABLED:
        return RedirectResponse("/login?error=oauth_unconfigured", status_code=303)
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse("/login?error=1", status_code=303)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    if not email:
        return RedirectResponse("/login?error=1", status_code=303)
    request.session["user"] = email  # no allowlist — any Google account is accepted
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Clear the session. @spec DASH-AUTH-005"""
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- Pages & API (protected) --------------------------------------------------


@app.get("/")
def index(request: Request):
    """Serve the dashboard, or redirect to login when unauthenticated. @spec DASH-AUTH-003"""
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(_STATIC / "index.html")


@app.get("/api/state")
def api_state(user: str = Depends(require_api)) -> JSONResponse:
    """Full read-only snapshot + derived KPIs. Falls back to last-good if the source is down."""
    global _last_good
    try:
        snap = live_snapshot()
    except Exception:  # noqa: BLE001 — source unavailable must never crash the server
        if _last_good is not None:
            return JSONResponse({**_last_good, "stale": True})
        raise HTTPException(status_code=503, detail="data source unavailable") from None

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": derive_summary(snap),
        **snap,
        "stale": False,
    }
    _last_good = payload
    return JSONResponse(payload)


@app.get("/api/events")
def api_events(user: str = Depends(require_api)) -> JSONResponse:
    return JSONResponse({"events": current_events()})


@app.get("/api/active_events")
def api_active_events(user: str = Depends(require_api)) -> JSONResponse:
    """Unresolved current events awaiting admin resolve. @spec RESOLVE-FLOW-001"""
    return JSONResponse({"active_events": active_events_list()})


@app.post("/api/active_events/{event_id}/confirm")
async def api_confirm_proposal(event_id: str, body: dict, user: str = Depends(require_api)) -> JSONResponse:
    """Confirm a pending proposal from the dashboard UI (intake or discharge).

    Body: { bed_id?, nurse_id, doctor_id }
    """
    from er_twin.active_events import _event_key, confirm_pending_proposal, create_active_event, get_active_event
    from er_twin.events.discharge_flow import commit_discharge
    from er_twin.events.intake_flow import commit_full_intake
    from er_twin.storage import make_store

    store = make_store() if settings.dashboard_source == "redis" else datasource.get_store()
    rec = get_active_event(store, event_id)
    if not rec or rec.get("status") != "pending_approval":
        raise HTTPException(status_code=404, detail="pending proposal not found")

    patient_id = rec.get("patient_id", "")
    event_type = rec.get("type", "")
    proposed = rec.get("proposed", {})

    if event_type == "discharge_proposal":
        nurse_id = body.get("nurse_id") or proposed.get("nurse_id")
        doctor_id = body.get("doctor_id") or proposed.get("doctor_id")
        outcome = commit_discharge(store, patient_id, nurse_id, doctor_id)
        promoted = confirm_pending_proposal(
            store, event_id, outcome["confirmation"], new_type="discharge",
        )
        if not promoted:
            create_active_event(store, "discharge", outcome["confirmation"], patient_id=patient_id)
        return JSONResponse({"confirmed": True, "summary": outcome["confirmation"], "event_id": event_id})

    if event_type == "intake_proposal":
        bed_id = body.get("bed_id") or proposed.get("bed_id")
        nurse_id = body.get("nurse_id") or proposed.get("nurse_id")
        doctor_id = body.get("doctor_id") or proposed.get("doctor_id")
        # Patient record is created here for the first time (nothing was written during planning).
        name = rec.get("name", "")
        mrn = rec.get("mrn", "")
        chief_complaint = rec.get("chief_complaint", "")
        vitals = rec.get("vitals") or {}
        outcome = commit_full_intake(store, name, chief_complaint, vitals, mrn, bed_id, nurse_id, doctor_id)
        if outcome.get("error"):
            raise HTTPException(status_code=409, detail=outcome["error"])
        real_patient_id = outcome["patient_id"]
        promoted = confirm_pending_proposal(
            store, event_id, outcome["confirmation"], new_type="intake",
        )
        if promoted:
            store.update(_event_key(event_id), {"patient_id": real_patient_id})
        else:
            create_active_event(store, "intake", outcome["confirmation"], patient_id=real_patient_id)
        return JSONResponse({"confirmed": True, "summary": outcome["confirmation"], "event_id": event_id})

    raise HTTPException(status_code=404, detail="unsupported proposal type")


@app.post("/api/active_events/{event_id}/resolve")
def api_resolve_active_event(event_id: str, user: str = Depends(require_api)) -> JSONResponse:
    """Resolve a current event from the dashboard (archives to event log). @spec RESOLVE-FLOW-002"""
    from er_twin.events.resolve import resolve_event_from_dashboard
    from er_twin.replay import ReplayRecorder
    from er_twin.storage import make_store

    store = make_store() if settings.dashboard_source == "redis" else datasource.get_store()
    rec = resolve_event_from_dashboard(store, event_id, ReplayRecorder())
    if rec is None:
        raise HTTPException(status_code=404, detail="active event not found")
    return JSONResponse({"resolved": True, "event": rec})


# --- Incident replay (data-driven, LLD §9.1) ----------------------------------
#
# The replay page + its JSON are public (synthetic data; needed by the headless frame capturer and by
# judges opening a shared link). The /library index is gated (see below). @spec REPLAY-FRAME-001/002


@app.get("/replay/{incident_id}")
def replay_page(incident_id: str) -> FileResponse:
    """Serve the replay playback page; the page fetches /api/replay/{id} and degrades if absent."""
    return FileResponse(_STATIC / "replay.html")


@app.get("/api/replay/{incident_id}")
def api_replay(incident_id: str) -> JSONResponse:
    """Return the incident's snapshot timeline from `out/replay/{incident}.json` (404 if missing).

    A half-written / corrupt file must not 500 — degrade to 404 like the sibling `/api/library` skip.
    """
    path = _replay_file(incident_id)
    if path is None:
        raise HTTPException(status_code=404, detail="incident replay not found")
    try:
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=404, detail="incident replay unavailable") from exc


def _library_entry(record: dict, fallback_id: str) -> dict:
    """Project an incident record down to the library card metadata (no heavy snapshot payload)."""
    incident_id = record.get("incident_id", fallback_id)
    return {
        "incident_id": incident_id,
        "incident_type": record.get("incident_type"),
        "title": record.get("title"),
        "summary": record.get("summary"),
        "start_ts": record.get("start_ts"),
        "end_ts": record.get("end_ts"),
        "speed_factor": record.get("speed_factor"),
        "involved": record.get("involved", []),
        "video_url": record.get("video_url"),
        "snapshot_count": len(record.get("snapshots", [])),
        "replay_url": f"/replay/{incident_id}",  # in-browser fallback (REPLAY-LIB-005)
    }


@app.get("/library")
def library_page(request: Request):
    """The session-gated incident library; redirects to login when unauthenticated. @spec REPLAY-LIB-004"""
    if not current_user(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(_STATIC / "library.html")


@app.get("/api/library")
def api_library(user: str = Depends(require_api)) -> JSONResponse:
    """List this session's incidents from `out/replay/*.json` with their metadata. @spec REPLAY-LIB-004"""
    entries: list[dict] = []
    if _REPLAY_DIR.is_dir():
        for path in sorted(_REPLAY_DIR.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue  # a half-written / corrupt file must not break the whole library
            if not isinstance(record, dict):
                continue  # valid JSON but not an incident object (e.g. a bare list) — skip, don't 500
            entries.append(_library_entry(record, path.stem))
    # pika_enabled lets the library page show the "Generate clip" action only when it would work.
    return JSONResponse({"incidents": entries, "pika_enabled": settings.dashboard_allow_pika})


# --- On-demand Pika generation (gated, dashboard-orchestrated) -----------------
#
# The dashboard (an ops surface, not er_twin/) lets an operator render a logged incident into a Pika
# clip on demand. It spawns the verified offline path (capture_replay_frames -> run_pika_keyframes.ps1
# -> Claude CLI -> Pika MCP), which back-writes video_url into out/replay/{incident}.json. Gated by
# DASHBOARD_ALLOW_PIKA because it spends Pika credits and shells out. @spec REPLAY-PIKA-003


@app.post("/api/replay/{incident_id}/generate")
def api_replay_generate(incident_id: str, user: str = Depends(require_api)) -> JSONResponse:
    """Start (or rejoin) an on-demand Pika render for an incident. 403 unless DASHBOARD_ALLOW_PIKA."""
    if not settings.dashboard_allow_pika:
        raise HTTPException(status_code=403, detail="Pika generation is disabled (set DASHBOARD_ALLOW_PIKA=true)")
    if _replay_file(incident_id) is None:
        raise HTTPException(status_code=404, detail="incident replay not found")
    job = pika_jobs.start_job(incident_id, _REPLAY_DIR)
    return JSONResponse(job.as_dict(), status_code=202)


@app.get("/api/replay/{incident_id}/status")
def api_replay_status(incident_id: str, user: str = Depends(require_api)) -> JSONResponse:
    """Poll an incident's render job. Reports the existing clip (idle) when no job has run this session."""
    if not settings.dashboard_allow_pika:
        raise HTTPException(status_code=403, detail="Pika generation is disabled (set DASHBOARD_ALLOW_PIKA=true)")
    job = pika_jobs.get_job(incident_id)
    if job is None:
        url = pika_jobs.read_video_url(_REPLAY_DIR, incident_id)
        return JSONResponse({"incident_id": incident_id, "status": pika_jobs.IDLE, "video_url": url, "error": None})
    return JSONResponse(job.as_dict())


@app.post("/api/command")
def api_command(body: dict, user: str = Depends(require_api)) -> JSONResponse:
    """Deferred input route — rejected while read-only. @spec DASH-IN-002"""
    if not settings.dashboard_allow_input:
        raise HTTPException(
            status_code=403, detail="command input is disabled (read-only dashboard)"
        )
    from .orchestrator_client import send_command

    accepted = send_command(body.get("phrase", ""))
    return JSONResponse({"accepted": accepted})
