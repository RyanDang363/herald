"""Tests for the read-only admin dashboard (fixture mode). Traces to docs/specs/dashboard-specs.md."""

import pytest
from fastapi.testclient import TestClient

from dashboard import datasource
from dashboard.datasource import build_fixture_store, derive_summary, snapshot
from dashboard.server import app

CREDS = {"username": "admin", "password": "password"}


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
