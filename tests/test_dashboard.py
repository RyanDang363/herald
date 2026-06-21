"""Tests for the read-only admin dashboard (fixture mode). Traces to docs/specs/dashboard-specs.md."""

import json

import pytest
from fastapi.testclient import TestClient

from dashboard import datasource
from dashboard.datasource import build_fixture_store, derive_summary, snapshot
from dashboard import pika_jobs
from dashboard import server
from dashboard.server import app

CREDS = {"username": "admin", "password": "password"}


@pytest.fixture
def replay_dir(tmp_path, monkeypatch):
    """Point the server's incident-replay dir at a temp folder. @spec REPLAY-FRAME-002, REPLAY-LIB-004"""
    d = tmp_path / "replay"
    d.mkdir()
    monkeypatch.setattr(server, "_REPLAY_DIR", d)
    return d


def _write_incident(replay_dir, incident_id="patient_intake-0001", **overrides) -> dict:
    record = {
        "incident_id": incident_id,
        "incident_type": "patient_intake",
        "title": "Chest pain intake — ESI-2",
        "summary": "Jordan Lee admitted to bed-1.",
        "speed_factor": 10,
        "start_ts": 1000.0,
        "end_ts": 1012.0,
        "involved": ["Jordan Lee", "bed-1", "Nurse Maya"],
        "video_url": None,
        "snapshots": [
            {"seq": 0, "ts": 1000.0, "action": "intake_received", "actor": "orchestrator",
             "target": None, "entities": {"patients": [], "beds": [], "nurses": [], "doctors": [], "equipment": []}},
            {"seq": 1, "ts": 1006.0, "action": "bed_assigned", "actor": "bed", "target": "bed1",
             "entities": {"patients": [{"id": "p1", "status": "admitted", "assigned_bed": "bed1"}],
                          "beds": [{"id": "bed1", "status": "occupied"}], "nurses": [], "doctors": [], "equipment": []}},
        ],
    }
    record.update(overrides)
    (replay_dir / f"{incident_id}.json").write_text(json.dumps(record), encoding="utf-8")
    return record


def new_client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client() -> TestClient:
    """A logged-in client (cookies persist on the instance). @spec DASH-AUTH-001"""
    c = TestClient(app)
    c.post("/login", data=CREDS)
    return c


# --- Auth ---------------------------------------------------------------------


# @spec DASH-AUTH-004 — protected API returns 401 when unauthenticated
def test_api_requires_auth():
    assert new_client().get("/api/state").status_code == 401
    assert new_client().get("/api/events").status_code == 401


# @spec DASH-AUTH-003 — protected page redirects to login when unauthenticated
def test_page_redirects_to_login():
    r = new_client().get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# @spec DASH-AUTH-001 — valid credentials open the dashboard
def test_login_success(auth_client):
    assert auth_client.get("/api/state").status_code == 200


# @spec DASH-AUTH-002 — invalid credentials do not establish a session
def test_login_failure():
    c = new_client()
    r = c.post("/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?error=1"
    assert c.get("/api/state").status_code == 401


# @spec DASH-AUTH-005 — logout clears the session
def test_logout_clears_session(auth_client):
    assert auth_client.get("/api/state").status_code == 200
    auth_client.get("/logout")
    assert auth_client.get("/api/state").status_code == 401


# @spec DASH-AUTH-006 — login page is reachable without auth
def test_login_page_public():
    assert new_client().get("/login").status_code == 200


# @spec DASH-AUTH-007 — auth config reports whether Google sign-in is available
def test_auth_config_reports_google_disabled_by_default(monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_ENABLED", False)
    assert new_client().get("/auth/config").json() == {"google_enabled": False}


# @spec DASH-AUTH-007 — Google flow route degrades cleanly when not configured
def test_google_sign_in_redirects_to_error_when_unconfigured(monkeypatch):
    monkeypatch.setattr(server, "GOOGLE_ENABLED", False)
    r = new_client().get("/auth/google", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?error=oauth_unconfigured"


# @spec DASH-AUTH-008 — a successful Google callback accepts any authenticated email account
def test_google_callback_accepts_any_email(monkeypatch):
    class GoogleClient:
        async def authorize_access_token(self, request):
            return {"userinfo": {"email": "anyone@example.com"}}

    monkeypatch.setattr(server, "GOOGLE_ENABLED", True)
    monkeypatch.setattr(
        server.oauth,
        "google",
        GoogleClient(),
        raising=False,
    )

    c = new_client()
    r = c.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert c.get("/api/state").status_code == 200


# @spec DASH-AUTH-008 — a Google callback without an email does not establish a session
def test_google_callback_requires_email(monkeypatch):
    class GoogleClient:
        async def authorize_access_token(self, request):
            return {"userinfo": {}}

    monkeypatch.setattr(server, "GOOGLE_ENABLED", True)
    monkeypatch.setattr(
        server.oauth,
        "google",
        GoogleClient(),
        raising=False,
    )

    c = new_client()
    r = c.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?error=1"
    assert c.get("/api/state").status_code == 401


# --- State / API (authenticated) ----------------------------------------------


# @spec DASH-API-001
def test_state_returns_all_entity_types(auth_client):
    body = auth_client.get("/api/state").json()
    for key in ("patients", "beds", "nurses", "doctors", "equipment"):
        assert key in body, f"missing {key}"
    assert body["patients"], "fixture should have patients"


# @spec DASH-API-003
def test_state_includes_derived_summary(auth_client):
    summary = auth_client.get("/api/state").json()["summary"]
    for key in ("active_patients", "occupied_beds", "free_nurses", "free_doctors", "active_alerts"):
        assert key in summary
    # Fixture: bed1 occupied; nurse2 + doc2 free; o2_1 at 45% (< 50) is one alert.
    assert summary["occupied_beds"] == 1
    assert summary["free_nurses"] == 1
    assert summary["free_doctors"] == 1
    assert summary["active_alerts"] == 1


# @spec DASH-API-002 — read endpoints never mutate state
def test_state_is_read_only(auth_client):
    before = snapshot(build_fixture_store())
    auth_client.get("/api/state")
    auth_client.get("/api/state")
    after = snapshot(build_fixture_store())
    assert before == after


# @spec DASH-API-004
def test_events_endpoint_returns_lines(auth_client):
    events = auth_client.get("/api/events").json()["events"]
    assert isinstance(events, list) and events
    assert {"ts", "event", "detail"} <= set(events[0])


# @spec DASH-IN-002 — command input rejected while read-only (but auth still required first)
def test_command_rejected_when_input_disabled(auth_client):
    r = auth_client.post("/api/command", json={"phrase": "A new patient arrived with chest pain"})
    assert r.status_code == 403


# --- Pure functions (no client) -----------------------------------------------


# @spec DASH-SYS-004 — snapshot uses only the StorageInterface
def test_snapshot_assembles_from_store():
    snap = snapshot(build_fixture_store())
    assert {p["id"] for p in snap["patients"]} == {"p1", "p2", "p3"}
    assert len(snap["beds"]) == 4


# @spec DASH-API-003 — empty ER summarizes to zeros, not an error
def test_derive_summary_empty():
    empty = {"patients": [], "beds": [], "nurses": [], "doctors": [], "equipment": []}
    assert derive_summary(empty) == {
        "active_patients": 0,
        "occupied_beds": 0,
        "free_nurses": 0,
        "free_doctors": 0,
        "active_alerts": 0,
    }


# @spec DASH-ERR-003 — missing optional fields must not raise
def test_derive_summary_tolerates_partial_records():
    snap = {
        "patients": [{"id": "p9"}],
        "beds": [{"id": "b9"}],
        "nurses": [{}],
        "doctors": [{}],
        "equipment": [{}],
    }
    summary = derive_summary(snap)
    assert summary["active_patients"] == 1  # no status -> counted as active
    assert summary["active_alerts"] == 0


def test_fixture_is_default_source():
    # Guards the read-only baseline assumption used by the tests above. @spec DASH-SYS-001
    assert datasource.settings.dashboard_source == "fixture"


# --- Incident replay endpoints (data-driven replay, LLD §9.1) -----------------


# @spec REPLAY-FRAME-002 — the timeline endpoint returns the ordered snapshots (with ts) from the file
def test_api_replay_returns_ordered_timeline(replay_dir):
    _write_incident(replay_dir)
    body = new_client().get("/api/replay/patient_intake-0001").json()
    assert body["incident_id"] == "patient_intake-0001"
    assert [s["seq"] for s in body["snapshots"]] == [0, 1]
    assert all("ts" in s for s in body["snapshots"])
    assert body["start_ts"] == 1000.0 and body["end_ts"] == 1012.0


# @spec REPLAY-FRAME-001 — the replay page is served (it fetches the timeline + reuses floor.js)
def test_replay_page_served(replay_dir):
    r = new_client().get("/replay/patient_intake-0001")
    assert r.status_code == 200
    assert "replay.js" in r.text and "floor.js" in r.text


# @spec REPLAY-FRAME-002 — a missing incident returns 404, not a 500
def test_api_replay_missing_incident_404(replay_dir):
    assert new_client().get("/api/replay/does-not-exist").status_code == 404


# @spec REPLAY-FRAME-002 — a corrupt/half-written incident file degrades to 404, never a 500
def test_api_replay_corrupt_file_404(replay_dir):
    (replay_dir / "patient_intake-0001.json").write_text("{not valid json", encoding="utf-8")
    assert new_client().get("/api/replay/patient_intake-0001").status_code == 404


# @spec REPLAY-FRAME-002 — replay endpoints need no auth (public synthetic replay; capturer/judges open it)
def test_api_replay_public(replay_dir):
    _write_incident(replay_dir)
    assert new_client().get("/api/replay/patient_intake-0001").status_code == 200


# A traversal-style id is rejected (the strict id allowlist also blocks path traversal).
def test_api_replay_rejects_unsafe_id(replay_dir):
    assert new_client().get("/api/replay/..%2f..%2fsecret").status_code == 404


# --- Incident library (session-only, gated, LLD §9.1) -------------------------


# @spec REPLAY-LIB-004 — the library lists every incident in out/replay/ with its metadata + video
def test_api_library_lists_incidents(auth_client, replay_dir):
    _write_incident(replay_dir, "patient_intake-0001",
                    video_url="https://cdn.pika.test/clip1.mp4")
    _write_incident(replay_dir, "low_oxygen_alert-0001", incident_type="low_oxygen_alert",
                    title="Low-oxygen response — bed-3", summary="O2 swapped on bed-3.",
                    involved=["bed-3", "Nurse Chen"])
    body = auth_client.get("/api/library").json()
    ids = {e["incident_id"] for e in body["incidents"]}
    assert ids == {"patient_intake-0001", "low_oxygen_alert-0001"}
    by_id = {e["incident_id"]: e for e in body["incidents"]}
    entry = by_id["patient_intake-0001"]
    assert entry["video_url"] == "https://cdn.pika.test/clip1.mp4"
    assert entry["incident_type"] == "patient_intake"
    assert entry["start_ts"] == 1000.0 and entry["end_ts"] == 1012.0
    assert entry["involved"] == ["Jordan Lee", "bed-1", "Nurse Maya"]
    assert entry["replay_url"] == "/replay/patient_intake-0001"
    # heavy snapshot payload is NOT shipped in the library list — only the count
    assert "snapshots" not in entry and entry["snapshot_count"] == 2


# @spec REPLAY-LIB-005 — an incident with no video_url still lists, with the /replay fallback link
def test_api_library_entry_without_video_still_lists(auth_client, replay_dir):
    _write_incident(replay_dir, "patient_intake-0001", video_url=None)
    entry = auth_client.get("/api/library").json()["incidents"][0]
    assert entry["video_url"] is None
    assert entry["replay_url"] == "/replay/patient_intake-0001"  # fallback the page links to


# @spec REPLAY-LIB-004 — the library API + page require auth (reuses the dashboard gate)
def test_library_requires_auth(replay_dir):
    assert new_client().get("/api/library").status_code == 401
    r = new_client().get("/library", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# Empty session library is an empty list, not an error (+ the pika feature flag, default off).
def test_api_library_empty(auth_client, replay_dir):
    assert auth_client.get("/api/library").json() == {"incidents": [], "pika_enabled": False}


# A corrupt incident file is skipped, not fatal to the whole library.
def test_api_library_skips_corrupt_file(auth_client, replay_dir):
    _write_incident(replay_dir, "patient_intake-0001")
    (replay_dir / "broken.json").write_text("{not json", encoding="utf-8")
    ids = {e["incident_id"] for e in auth_client.get("/api/library").json()["incidents"]}
    assert ids == {"patient_intake-0001"}


# Valid JSON that is NOT an object (e.g. a bare list) is skipped, not a 500 (record.get would AttributeError).
def test_api_library_skips_non_dict_json(auth_client, replay_dir):
    _write_incident(replay_dir, "patient_intake-0001")
    (replay_dir / "arraylike.json").write_text("[1, 2, 3]", encoding="utf-8")
    (replay_dir / "stringlike.json").write_text('"just a string"', encoding="utf-8")
    r = auth_client.get("/api/library")
    assert r.status_code == 200
    assert {e["incident_id"] for e in r.json()["incidents"]} == {"patient_intake-0001"}


# @spec REPLAY-LIB-004 — the library page is served to an authenticated user
def test_library_page_served(auth_client, replay_dir):
    r = auth_client.get("/library")
    assert r.status_code == 200 and "library.js" in r.text


# @spec DASH-SIM-001, DASH-SIM-002 — scripted timeline evolves and emits agent-attributed events
def test_sim_timeline_evolves_and_attributes_agents():
    from dashboard.sim import SimController

    c = SimController()
    s0, e0 = c.state_and_events(1000.0)  # elapsed 0 — baseline
    beds0 = {b["id"]: b for b in s0["beds"]}
    assert beds0["bed2"]["status"] == "available"

    s1, e1 = c.state_and_events(1000.0 + 14)  # past the bed-assign step at t+13s
    beds1 = {b["id"]: b for b in s1["beds"]}
    assert beds1["bed2"]["status"] == "occupied"
    assert beds1["bed2"]["occupied_by"] == "p3"

    assert len(e1) > len(e0)
    assert {"from", "to", "event", "detail"} <= set(e1[0])


# --- On-demand Pika generation (gated, dashboard-orchestrated) -----------------
# @spec REPLAY-PIKA-003


@pytest.fixture
def pika_on(monkeypatch):
    """Enable the Pika action and run jobs inline (no thread, no subprocess). Resets the registry."""
    monkeypatch.setattr(server.settings, "dashboard_allow_pika", True)
    monkeypatch.setattr(pika_jobs, "_spawn", lambda target: target())  # run the job body synchronously
    pika_jobs.reset()
    yield
    pika_jobs.reset()


# The library payload advertises whether the Pika action is available (default: off).
def test_library_reports_pika_disabled_by_default(auth_client, replay_dir):
    assert auth_client.get("/api/library").json()["pika_enabled"] is False


def test_library_reports_pika_enabled(auth_client, replay_dir, pika_on):
    assert auth_client.get("/api/library").json()["pika_enabled"] is True


# @spec REPLAY-PIKA-003 — generation/status require auth (reuse the dashboard gate), even when disabled
def test_pika_endpoints_require_auth(replay_dir):
    assert new_client().post("/api/replay/patient_intake-0001/generate").status_code == 401
    assert new_client().get("/api/replay/patient_intake-0001/status").status_code == 401


# @spec REPLAY-PIKA-003 — disabled by default: an authed operator still gets 403, not a render
def test_pika_generate_forbidden_when_disabled(auth_client, replay_dir):
    _write_incident(replay_dir)
    assert auth_client.post("/api/replay/patient_intake-0001/generate").status_code == 403
    assert auth_client.get("/api/replay/patient_intake-0001/status").status_code == 403


# @spec REPLAY-PIKA-003 — generating for an unknown incident is a 404, not a started job
def test_pika_generate_missing_incident_404(auth_client, replay_dir, pika_on):
    assert auth_client.post("/api/replay/does-not-exist/generate").status_code == 404


# @spec REPLAY-PIKA-003 — happy path: the job runs, the runner back-writes video_url, job completes,
# and the library subsequently serves that clip.
def test_pika_generate_completes_and_clip_appears(auth_client, replay_dir, pika_on, monkeypatch):
    _write_incident(replay_dir, "patient_intake-0001", video_url=None)

    def fake_runner(incident_id):  # stand-in for capture_replay_frames + run_pika_keyframes.ps1
        path = replay_dir / f"{incident_id}.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["video_url"] = "https://cdn.pika.test/generated.mp4"
        path.write_text(json.dumps(rec), encoding="utf-8")

    monkeypatch.setattr(pika_jobs, "default_runner", fake_runner)

    assert auth_client.post("/api/replay/patient_intake-0001/generate").status_code == 202
    status = auth_client.get("/api/replay/patient_intake-0001/status").json()
    assert status["status"] == "completed"
    assert status["video_url"] == "https://cdn.pika.test/generated.mp4"
    # the clip is now in the file, so the library serves it
    entry = auth_client.get("/api/library").json()["incidents"][0]
    assert entry["video_url"] == "https://cdn.pika.test/generated.mp4"


# @spec REPLAY-PIKA-003 — a runner that raises marks the job failed (never crashes the worker)
def test_pika_generate_failure_marks_job_failed(auth_client, replay_dir, pika_on, monkeypatch):
    _write_incident(replay_dir, "patient_intake-0001", video_url=None)

    def boom(incident_id):
        raise RuntimeError("pika render exploded")

    monkeypatch.setattr(pika_jobs, "default_runner", boom)

    auth_client.post("/api/replay/patient_intake-0001/generate")
    status = auth_client.get("/api/replay/patient_intake-0001/status").json()
    assert status["status"] == "failed"
    assert "exploded" in status["error"]


# @spec REPLAY-PIKA-003 — a runner that finishes without writing a clip is a failure (file is truth)
def test_pika_generate_no_url_is_failure(auth_client, replay_dir, pika_on, monkeypatch):
    _write_incident(replay_dir, "patient_intake-0001", video_url=None)
    monkeypatch.setattr(pika_jobs, "default_runner", lambda incident_id: None)  # writes nothing

    auth_client.post("/api/replay/patient_intake-0001/generate")
    status = auth_client.get("/api/replay/patient_intake-0001/status").json()
    assert status["status"] == "failed"
    assert "video_url" in status["error"]


# @spec REPLAY-PIKA-003 — with no job this session, status is "idle" and reports any existing clip
def test_pika_status_idle_reports_existing_clip(auth_client, replay_dir, pika_on):
    _write_incident(replay_dir, "patient_intake-0001", video_url="https://cdn.pika.test/old.mp4")
    status = auth_client.get("/api/replay/patient_intake-0001/status").json()
    assert status["status"] == "idle"
    assert status["video_url"] == "https://cdn.pika.test/old.mp4"
