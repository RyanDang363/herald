// Dashboard frontend — polls the read-only API and re-renders with live feedback.
// @spec DASH-UI-001, DASH-UI-002, DASH-UI-003, DASH-UI-004, DASH-UI-005
// @spec DASH-UI-006 (change-flash), DASH-UI-007 (event toasts), DASH-UI-008 (heartbeat)
"use strict";

const POLL_MS = 1000;

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

// --- Diff tracking (live feedback) -------------------------------------------
const prev = {}; // key "type:id" -> serialized record
let firstLoad = true;
const seenPatients = new Set();
const alerting = new Set();

// Returns "enter" for brand-new entities, "flash" for changed ones, "" otherwise.
// Records the new value so the next tick can diff against it.
function diffClass(type, id, record) {
  const key = `${type}:${id}`;
  const ser = JSON.stringify(record);
  const had = key in prev;
  const changed = had && prev[key] !== ser;
  prev[key] = ser;
  if (!had && !firstLoad) return "enter";
  if (changed) return "flash";
  return "";
}

const LOW_O2 = 50;
const isLowO2 = (e) => e.type === "oxygen" && e.supply_level != null && e.supply_level < LOW_O2;

function detectToasts(state) {
  const toasts = [];
  for (const p of state.patients || []) {
    if (!seenPatients.has(p.id)) {
      seenPatients.add(p.id);
      if (!firstLoad) toasts.push({ kind: "intake", msg: `New patient: ${p.name || p.id}` });
    }
  }
  for (const e of state.equipment || []) {
    if (isLowO2(e)) {
      if (!alerting.has(e.id) && !firstLoad) {
        toasts.push({ kind: "alert", msg: `Low O₂: ${e.id} at ${e.supply_level}% (${e.location || "—"})` });
      }
      alerting.add(e.id);
    } else {
      alerting.delete(e.id);
    }
  }
  return toasts;
}

function showToast({ kind, msg }) {
  const t = el("div", `toast toast-${kind}`, msg);
  $("toasts").append(t);
  setTimeout(() => t.classList.add("show"), 10);
  setTimeout(() => {
    t.classList.remove("show");
    setTimeout(() => t.remove(), 300);
  }, 4500);
}

function pulseHeartbeat() {
  const dot = $("live-dot");
  dot.classList.remove("beat");
  void dot.offsetWidth; // restart the animation
  dot.classList.add("beat");
}

// --- Renderers ---------------------------------------------------------------
function renderKpis(s) {
  const kpis = [
    ["Active patients", s.active_patients],
    ["Beds occupied", s.occupied_beds],
    ["Nurses free", s.free_nurses],
    ["Doctors free", s.free_doctors],
    ["Alerts", s.active_alerts],
  ];
  $("kpis").replaceChildren(
    ...kpis.map(([label, val]) => {
      const card = el("div", "kpi" + (label === "Alerts" && val > 0 ? " kpi-alert" : ""));
      card.append(el("div", "kpi-value", String(val ?? 0)), el("div", "kpi-label", label));
      return card;
    })
  );
}

function renderBeds(beds) {
  const root = $("beds");
  if (!beds.length) return root.replaceChildren(el("p", "empty", "No beds configured."));
  root.replaceChildren(
    ...beds.map((b) => {
      const tile = el("div", `bed bed-${b.status} ${diffClass("bed", b.id, b)}`);
      tile.append(
        el("div", "bed-id", b.id),
        el("div", "bed-status", b.status),
        el("div", "bed-sub", b.occupied_by ? `patient ${b.occupied_by}` : b.specialty || "—")
      );
      return tile;
    })
  );
}

function renderPatients(patients) {
  const root = $("patients");
  const active = patients.filter((p) => p.status !== "discharged");
  if (!active.length) return root.replaceChildren(el("p", "empty", "No patients in the ER."));
  root.replaceChildren(
    ...active.map((p) => {
      const v = p.vitals || {};
      const card = el("div", `card ${diffClass("patient", p.id, p)}`);
      card.append(
        el("div", "card-top", `<strong>${p.name || p.id}</strong><span class="pill acuity-${p.acuity}">ESI ${p.acuity ?? "—"}</span>`),
        el("div", "card-line", `${p.chief_complaint || "—"} · ${p.status}`),
        el("div", "card-line muted", `HR ${v.hr ?? "—"} · SpO₂ ${v.spo2 ?? "—"} · BP ${v.bp ?? "—"}`),
        el("div", "card-line muted", `Bed ${p.assigned_bed || "—"} · Team ${(p.care_team || []).join(", ") || "—"}`)
      );
      return card;
    })
  );
}

function renderStaff(nurses, doctors) {
  const mk = (s, role, type) => {
    const free = s.available;
    const card = el("div", `card ${diffClass(type, s.id, s)}`);
    card.append(
      el("div", "card-top", `<strong>${s.id}</strong><span class="pill ${free ? "ok" : "busy"}">${free ? "free" : "busy"}</span>`),
      el("div", "card-line muted", `${role}${s.specialty ? " · " + s.specialty : ""}${s.location ? " · " + s.location : ""}`),
      el("div", "card-line muted", `Assigned: ${(s.assignments || []).join(", ") || "—"}`)
    );
    return card;
  };
  const cards = [...nurses.map((n) => mk(n, "nurse", "nurse")), ...doctors.map((d) => mk(d, "doctor", "doctor"))];
  $("staff").replaceChildren(...(cards.length ? cards : [el("p", "empty", "No staff on shift.")]));
}

function renderEquipment(equipment) {
  const root = $("equipment");
  if (!equipment.length) return root.replaceChildren(el("p", "empty", "No equipment tracked."));
  root.replaceChildren(
    ...equipment.map((e) => {
      const low = isLowO2(e);
      const card = el("div", `card ${low ? "card-alert" : ""} ${diffClass("equipment", e.id, e)}`);
      const level = e.supply_level != null ? `${e.supply_level}%` : e.in_use_by ? "in use" : "available";
      card.append(
        el("div", "card-top", `<strong>${e.id}</strong><span class="pill ${low ? "busy" : "ok"}">${level}</span>`),
        el("div", "card-line muted", `${e.type} · ${e.location || "—"}${e.in_use_by ? " · " + e.in_use_by : ""}`)
      );
      return card;
    })
  );
}

function renderEvents(events) {
  const root = $("events");
  if (!events.length) return root.replaceChildren(el("li", "empty", "No events yet."));
  root.replaceChildren(
    ...[...events].reverse().map((ev) => {
      const li = el("li", `event event-${ev.event}`);
      const chain = ev.from && ev.to ? `${ev.from} → ${ev.to}` : ev.event;
      li.append(
        el("span", "event-ts", ev.ts || ""),
        el("span", "event-chain", chain),
        el("span", "event-detail", ev.detail || "")
      );
      return li;
    })
  );
}

// --- Poll loop ---------------------------------------------------------------
async function tick() {
  try {
    const state = await getJSON("/api/state");
    $("banner").classList.toggle("hidden", !state.stale);
    $("updated").textContent = "updated " + (state.generated_at || "");
    pulseHeartbeat();

    const toasts = detectToasts(state);
    renderKpis(state.summary || {});
    renderBeds(state.beds || []);
    renderPatients(state.patients || []);
    renderStaff(state.nurses || [], state.doctors || []);
    renderEquipment(state.equipment || []);
    toasts.forEach(showToast);
    firstLoad = false;
  } catch (e) {
    $("banner").classList.remove("hidden");
  }
  try {
    const { events } = await getJSON("/api/events");
    renderEvents(events || []);
  } catch (e) {
    /* keep last log on error */
  }
}

tick();
setInterval(tick, POLL_MS);
