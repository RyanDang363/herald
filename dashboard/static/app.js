// Dashboard frontend — polls the read-only API and re-renders with live feedback.
// @spec DASH-UI-001, DASH-UI-002, DASH-UI-003, DASH-UI-004, DASH-UI-005
// @spec DASH-UI-006 (change-flash), DASH-UI-007 (event toasts), DASH-UI-008 (heartbeat)
// Floor geometry + entity placement live in the shared floor.js (window.Floor), reused by the replay
// page so both maps match exactly. @spec REPLAY-FRAME-001
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
let selected = null; // { kind: "patient" | "nurse" | "doctor" | "equipment", id: string }
let currentState = null;
let selectedKey = "";
let floorPositions = new Map(); // key -> { x, y } in floor viewBox units

// Shared floor geometry + helpers (floor.js must load before this script).
const { LOW_O2, isLowO2 } = window.Floor;

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

function toggleSelection(kind, id) {
  if (selected && selected.kind === kind && selected.id === id) {
    selected = null;
  } else {
    selected = { kind, id };
  }
  renderDetail();
  syncSelectedCards();
}

function showAlertsDetail() {
  selected = { kind: "alerts", id: "active" };
  renderDetail();
  syncSelectedCards();
}

function closeDetail() {
  selected = null;
  renderDetail();
  syncSelectedCards();
}

function syncSelectedCards() {
  const nextKey = selected ? `${selected.kind}:${selected.id}` : "";
  if (
    nextKey === selectedKey &&
    document.querySelector(".interactive-card.active, .floor-token.active, .kpi-action.active")
  ) return;
  selectedKey = nextKey;
  document.querySelectorAll(".interactive-card, .floor-token, .kpi-action").forEach((node) => {
    const isActive = nextKey && node.dataset.key === nextKey;
    node.classList.toggle("active", !!isActive);
    node.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function detailRows(rows) {
  return rows
    .map(
      ([label, value, tone]) =>
        `<div class="detail-row ${tone ? `tone-${tone}` : ""}"><span class="detail-label">${label}</span><span class="detail-value ${tone ? "detail-badge" : ""}">${value ?? "—"}</span></div>`
    )
    .join("");
}

function detailSection(title, rows) {
  return `<section class="detail-section"><h3>${title}</h3>${detailRows(rows)}</section>`;
}

function activeAlerts(state) {
  return (state.equipment || [])
    .filter(isLowO2)
    .map((item) => ({
      id: item.id,
      issue: "Low oxygen supply",
      location: item.location || "Unknown",
      level: item.supply_level,
      tone: supplyTone(item.supply_level) || "bad",
    }));
}

function supplyTone(level) {
  if (level == null) return "";
  if (level < 30) return "bad";
  if (level < 70) return "warn";
  return "good";
}

function acuityTone(acuity) {
  if (acuity == null) return "";
  if (acuity <= 2) return "bad";
  if (acuity === 3) return "warn";
  return "good";
}

function spo2Tone(spo2) {
  if (spo2 == null) return "";
  if (spo2 < 92) return "bad";
  if (spo2 < 95) return "warn";
  return "good";
}

function hrTone(hr) {
  if (hr == null) return "";
  if (hr < 50 || hr > 120) return "bad";
  if (hr < 60 || hr > 100) return "warn";
  return "good";
}

function renderDetail() {
  const shell = $("detail-shell");
  const panel = $("detail-panel");
  const body = $("detail-body");
  const title = $("detail-title");
  const sub = $("detail-sub");
  const kicker = $("detail-kicker");
  const hasSelection = !!selected && !!currentState;
  shell.classList.toggle("hidden", !hasSelection);
  shell.setAttribute("aria-hidden", hasSelection ? "false" : "true");
  document.body.classList.toggle("detail-open", hasSelection);

  if (!hasSelection) {
    body.replaceChildren();
    return;
  }

  let record = null;
  if (selected.kind === "alerts") {
    record = { id: "active" };
  } else if (selected.kind === "patient") {
    record = (currentState.patients || []).find((p) => p.id === selected.id);
  } else if (selected.kind === "nurse") {
    record = (currentState.nurses || []).find((n) => n.id === selected.id);
  } else if (selected.kind === "doctor") {
    record = (currentState.doctors || []).find((d) => d.id === selected.id);
  } else if (selected.kind === "equipment") {
    record = (currentState.equipment || []).find((e) => e.id === selected.id);
  }

  if (!record) {
    closeDetail();
    return;
  }

  if (selected.kind === "alerts") {
    const alerts = activeAlerts(currentState);
    kicker.textContent = "Alerts";
    title.textContent = `${alerts.length} active ${alerts.length === 1 ? "issue" : "issues"}`;
    sub.textContent = alerts.length ? "Current problems requiring attention" : "No active issues detected";
    body.innerHTML = alerts.length
      ? alerts
          .map((alert) =>
            detailSection(`${alert.issue}: ${alert.id}`, [
              ["Device", alert.id],
              ["Location", alert.location, "bad"],
              ["Current level", `${alert.level}%`, alert.tone],
              ["Action", "Replace or refill oxygen", "bad"],
            ])
          )
          .join("")
      : detailSection("Status", [["System state", "Normal", "good"]]);
  } else if (selected.kind === "patient") {
    const v = record.vitals || {};
    kicker.textContent = "Patient";
    title.textContent = record.name || record.id;
    sub.textContent = `${record.chief_complaint || "No chief complaint"} · ${record.status || "status unknown"}`;
    body.innerHTML =
      detailSection("Status", [
        ["Patient ID", record.id],
        ["Acuity", record.acuity != null ? `ESI ${record.acuity}` : "—", acuityTone(record.acuity)],
        ["Bed", record.assigned_bed || "Unassigned"],
        ["Care team", (record.care_team || []).join(", ") || "—"],
      ]) +
      detailSection("Vitals", [
        ["Heart rate", v.hr ? `${v.hr} bpm` : "—", hrTone(v.hr)],
        ["SpO₂", v.spo2 ? `${v.spo2}%` : "—", spo2Tone(v.spo2)],
        ["Blood pressure", v.bp || "—"],
      ]);
  } else if (selected.kind === "equipment") {
    const level = record.supply_level != null ? `${record.supply_level}%` : "—";
    const inUse = record.in_use_by ? `In use by ${record.in_use_by}` : "Available";
    const useTone = record.in_use_by ? "warn" : "good";
    kicker.textContent = "Device";
    title.textContent = record.id;
    sub.textContent = `${record.type || "equipment"} · ${record.location || "location unknown"}`;
    body.innerHTML =
      detailSection("Status", [
        ["Device ID", record.id],
        ["Type", record.type || "—"],
        ["Location", record.location || "—"],
        ["Use state", inUse, useTone],
      ]) +
      detailSection("Supply", [
        ["Current level", level, supplyTone(record.supply_level)],
        ["Alert threshold", record.type === "oxygen" ? `< ${LOW_O2}%` : "—", record.type === "oxygen" ? "bad" : ""],
      ]);
  } else {
    const role = selected.kind === "nurse" ? "Nurse" : "Doctor";
    kicker.textContent = role;
    title.textContent = record.id;
    sub.textContent = `${record.available ? "Available" : "Busy"}${record.location ? ` · ${record.location}` : ""}`;
    body.innerHTML =
      detailSection("Assignment", [
        ["Role", role.toLowerCase()],
        ["Specialty", record.specialty || "General"],
        ["Location", record.location || "—"],
        ["Availability", record.available ? "Available" : "Busy", record.available ? "good" : "warn"],
      ]) +
      detailSection("Workload", [
        ["Assigned cases", (record.assignments || []).join(", ") || "—"],
        ["Open slots", record.available ? "1+" : "0", record.available ? "good" : "warn"],
      ]);
  }
  panel.scrollTop = 0;
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
      const isAlerts = label === "Alerts";
      const card = el(isAlerts ? "button" : "div", "kpi" + (isAlerts ? " kpi-action" : "") + (isAlerts && val > 0 ? " kpi-alert" : ""));
      if (isAlerts) {
        card.type = "button";
        card.dataset.key = "alerts:active";
        card.onclick = showAlertsDetail;
      }
      card.append(el("div", "kpi-value", String(val ?? 0)), el("div", "kpi-label", label));
      return card;
    })
  );
}

// Floor-token renderer for the LIVE dashboard: adds change-flash motion + selection state on top of
// the shared placement from Floor.placeEntities.
function floorMarker(kind, id, label, x, y, extraClass = "", title = "", nextPositions = null) {
  const key = `${kind}:${id}`;
  const activeClass = selected && selected.kind === kind && selected.id === id ? " active" : "";
  const previous = floorPositions.get(key);
  const next = { x, y };
  const moved = !firstLoad && previous && !Floor.sameFloorPoint(previous, next);
  if (nextPositions) nextPositions.set(key, next);
  const markerTitle = title || `${kind} ${id}`;
  const style = [
    `left:${Floor.floorPercent(x, "x")}`,
    `top:${Floor.floorPercent(y, "y")}`,
    previous ? `--from-left:${Floor.floorPercent(previous.x, "x")}` : "",
    previous ? `--from-top:${Floor.floorPercent(previous.y, "y")}` : "",
    `--to-left:${Floor.floorPercent(x, "x")}`,
    `--to-top:${Floor.floorPercent(y, "y")}`,
  ].filter(Boolean).join(";");
  return `<button type="button" class="floor-token ${kind}${activeClass} ${moved ? "moving" : ""} ${extraClass}" data-key="${Floor.escapeAttr(key)}" style="${style}" title="${Floor.escapeAttr(markerTitle)}" aria-label="${Floor.escapeAttr(markerTitle)}">
    <span class="token-core">${Floor.escapeAttr(label)}</span>
    <span class="token-label">${Floor.escapeAttr(id)}</span>
  </button>`;
}

function renderFloorMap(state) {
  const map = $("floor-map");
  const patients = state.patients || [];
  const nurses = state.nurses || [];
  const doctors = state.doctors || [];

  const specs = Floor.placeEntities(state);
  const nextFloorPositions = new Map();
  const markers = specs.map((spec) =>
    floorMarker(spec.kind, spec.id, spec.label, spec.x, spec.y, spec.cls, spec.title, nextFloorPositions)
  );

  map.innerHTML = `
    <div class="floor-shell">
      ${Floor.renderBlueprint()}
      <div class="floor-hud" aria-hidden="true">
        <span>ER-01</span>
        <span>${patients.filter((p) => p.status !== "discharged").length} patients</span>
        <span>${nurses.length + doctors.length} staff</span>
      </div>
      ${markers.join("")}
      <div class="floor-legend">
        <span><i class="legend-dot patient"></i>Patients</span>
        <span><i class="legend-dot nurse"></i>Nurses</span>
        <span><i class="legend-dot doctor"></i>Doctors</span>
        <span><i class="legend-dot equipment"></i>Devices</span>
      </div>
    </div>
  `;
  floorPositions = nextFloorPositions;

  map.querySelectorAll(".floor-token").forEach((node) => {
    const [kind, id] = node.dataset.key.split(":");
    if (["patient", "nurse", "doctor"].includes(kind)) {
      node.onclick = () => toggleSelection(kind, id);
    } else if (kind === "bed") {
      node.onclick = () => {
        const patient = patients.find((p) => p.assigned_bed === id);
        if (patient) toggleSelection("patient", patient.id);
      };
    } else if (kind === "equipment") {
      node.onclick = () => toggleSelection("equipment", id);
    }
  });
  syncSelectedCards();
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
      const card = el("button", `card interactive-card ${diffClass("patient", p.id, p)}`);
      card.type = "button";
      card.dataset.key = `patient:${p.id}`;
      card.onclick = () => toggleSelection("patient", p.id);
      card.append(
        el("div", "card-top", `<strong>${p.name || p.id}</strong><span class="pill acuity-${p.acuity}">ESI ${p.acuity ?? "—"}</span>`),
        el("div", "card-line", `${p.chief_complaint || "—"} · ${p.status}`),
        el("div", "card-line muted", `HR ${v.hr ?? "—"} · SpO₂ ${v.spo2 ?? "—"} · BP ${v.bp ?? "—"}`),
        el("div", "card-line muted", `Bed ${p.assigned_bed || "—"} · Team ${(p.care_team || []).join(", ") || "—"}`),
        el("div", "card-hint", "Click for live details")
      );
      return card;
    })
  );
}

function renderStaff(nurses, doctors) {
  const mk = (s, role, type) => {
    const free = s.available;
    const card = el("button", `card interactive-card ${diffClass(type, s.id, s)}`);
    card.type = "button";
    card.dataset.key = `${type}:${s.id}`;
    card.onclick = () => toggleSelection(type, s.id);
    card.append(
      el("div", "card-top", `<strong>${s.id}</strong><span class="pill ${free ? "ok" : "busy"}">${free ? "free" : "busy"}</span>`),
      el("div", "card-line muted", `${role}${s.specialty ? " · " + s.specialty : ""}${s.location ? " · " + s.location : ""}`),
      el("div", "card-line muted", `Assigned: ${(s.assignments || []).join(", ") || "—"}`),
      el("div", "card-hint", "Click for live details")
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
      const card = el("button", `card interactive-card ${low ? "card-alert" : ""} ${diffClass("equipment", e.id, e)}`);
      card.type = "button";
      card.dataset.key = `equipment:${e.id}`;
      const level = e.supply_level != null ? `${e.supply_level}%` : e.in_use_by ? "in use" : "available";
      card.append(
        el("div", "card-top", `<strong>${e.id}</strong><span class="pill ${low ? "busy" : "ok"}">${level}</span>`),
        el("div", "card-line muted", `${e.type} · ${e.location || "—"}${e.in_use_by ? " · " + e.in_use_by : ""}`),
        el("div", "card-hint", "Click for live details")
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
    currentState = state;
    $("banner").classList.toggle("hidden", !state.stale);
    $("updated").textContent = "updated " + (state.generated_at || "");
    pulseHeartbeat();

    const toasts = detectToasts(state);
    renderKpis(state.summary || {});
    renderFloorMap(state);
    renderBeds(state.beds || []);
    renderPatients(state.patients || []);
    renderStaff(state.nurses || [], state.doctors || []);
    renderEquipment(state.equipment || []);
    renderDetail();
    syncSelectedCards();
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

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && selected) closeDetail();
});
$("detail-close").onclick = closeDetail;
$("detail-backdrop").onclick = closeDetail;

tick();
setInterval(tick, POLL_MS);
