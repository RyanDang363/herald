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
let selected = null; // { kind: "patient" | "nurse" | "doctor" | "equipment", id: string }
let currentState = null;
let selectedKey = "";
let floorPositions = new Map(); // key -> { x, y } in floor viewBox units
let floorView = null;

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

// Shared floor geometry + placement live in floor.js (window.Floor), which loads before this script.
// Sourcing them here keeps the live 3D map and the replay 2D map on one coordinate system, so token
// positions, zones, beds, and the low-O2 threshold can't drift between the two. @spec REPLAY-FRAME-001
const Floor = window.Floor;
const {
  LOW_O2,
  isLowO2,
  FLOOR_ZONES,
  FLOOR_VIEWBOX,
  BED_LAYOUT,
  FLOOR_WALLS,
  normalizeFloorZone,
  zoneNameForPatient,
  reserveFloorPosition,
  floorPercent,
  sameFloorPoint,
  escapeAttr,
} = Floor;

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
  refreshSelectionViews();
}

function showAlertsDetail() {
  selected = { kind: "alerts", id: "active" };
  renderDetail();
  refreshSelectionViews();
}

function closeDetail() {
  selected = null;
  renderDetail();
  refreshSelectionViews();
}

function refreshSelectionViews() {
  if (currentState) {
    renderFloorMap(currentState);
  } else {
    syncSelectedCards();
  }
}

function syncSelectedCards() {
  const nextKey = selected ? `${selected.kind}:${selected.id}` : "";
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

function patientMonogram(patient) {
  const name = String(patient?.name || "").trim();
  if (name) {
    const initials = name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() || "")
      .join("");
    if (initials) return initials;
  }
  return String(patient?.id || "PT").replace(/[^a-z0-9]/gi, "").slice(0, 2).toUpperCase() || "PT";
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
      detailSection("Floor", [
        ["Map marker", patientMonogram(record), "good"],
        ["Location", patientFloorLabel(record)],
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
      detailSection("Floor", [
        ["Map marker", equipmentMarkerLabel(record), useTone],
        ["Location", floorZoneLabel(equipmentFloorLocation(record, currentState.patients || []))],
      ]) +
      detailSection("Supply", [
        ["Current level", level, supplyTone(record.supply_level)],
        ["Alert threshold", record.type === "oxygen" ? `< ${LOW_O2}%` : "—", record.type === "oxygen" ? "bad" : ""],
      ]);
  } else {
    const role = selected.kind === "nurse" ? "Nurse" : "Doctor";
    const mapMarker = selected.kind === "nurse" ? "N" : "D";
    const floorLocation =
      selected.kind === "doctor" ? doctorFloorLocation(record, currentState.patients || []) : record.location || "nurses-station";
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
      detailSection("Floor", [
        ["Map marker", mapMarker, record.available ? "good" : "warn"],
        ["Location", floorZoneLabel(floorLocation)],
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

// 3D-only render config. The shared geometry (FLOOR_ZONES, FLOOR_VIEWBOX, BED_LAYOUT, FLOOR_LABELS,
// FLOOR_WALLS) is destructured from window.Floor near the top of this file.
const FLOOR_FOCUS_GROUPS = [
  { label: "All", zone: "" },
  { label: "Waiting", zone: "waiting" },
  { label: "Triage", zone: "triage" },
  { label: "Trauma", zone: "trauma" },
  { label: "Bays", zone: "general-a" },
  { label: "Nurse", zone: "nurses-station" },
  { label: "Supply", zone: "storage" },
];

const FLOOR_3D = {
  scale: 0.023,
  defaultYaw: -0.64,
  minPitch: 0.54,
  maxPitch: 1.5,
  defaultPitch: 0.98,
  focusPitch: 0.88,
  minDistance: 4.9,
  maxDistance: 31,
  defaultDistance: 17.8,
  orthoHeight: 15.8,
  panMarginX: 150,
  panMarginY: 110,
};

const ROOM_3D_COLORS = {
  waiting: 0xf1f1ee,
  triage: 0xe3e6e2,
  trauma: 0xe7dfdb,
  "nurses-station": 0xe1e4e2,
  storage: 0xe3e0da,
  cardiology: 0xece9e2,
  "general-a": 0xe9e7e0,
  "general-b": 0xe7e5de,
  corridor: 0xd2d0ca,
};

const TOKEN_3D_COLORS = {
  patient: 0x547089,
  nurse: 0x5e7466,
  doctor: 0x72697f,
  bed: 0x8d9498,
  equipment: 0x987a57,
  alert: 0xa06259,
  busy: 0x907152,
  ok: 0x617868,
};

// normalizeFloorLocation, normalizeFloorZone, and zoneNameForPatient are destructured from
// window.Floor near the top of this file (shared with the replay page).
function floorZoneLabel(zoneId) {
  const zone = FLOOR_ZONES.find((z) => z.id === normalizeFloorZone(zoneId));
  return zone ? zone.label : "Main Corridor";
}

function patientFloorLabel(patient) {
  if (patient.assigned_bed && BED_LAYOUT[patient.assigned_bed]) {
    return `${patient.assigned_bed.toUpperCase()} / ${floorZoneLabel(BED_LAYOUT[patient.assigned_bed].zone)}`;
  }
  return floorZoneLabel(zoneNameForPatient(patient));
}

function doctorFloorLocation(doctor, patients) {
  const assignedPatient = patients.find((p) => (doctor.assignments || []).includes(p.id));
  if (assignedPatient && assignedPatient.assigned_bed && BED_LAYOUT[assignedPatient.assigned_bed]) {
    return assignedPatient.assigned_bed;
  }
  return doctor.location || (doctor.specialty === "cardiology" ? "cardiology" : "nurses-station");
}

function equipmentFloorLocation(item, patients) {
  if (item.location && BED_LAYOUT[item.location]) return item.location;
  if (item.in_use_by) {
    const patient = patients.find((p) => p.id === item.in_use_by);
    return patient && patient.assigned_bed ? patient.assigned_bed : "storage";
  }
  return item.location || "storage";
}

function equipmentMarkerLabel(item) {
  if (item.type === "oxygen") return "O2";
  if (item.type === "defibrillator") return "DF";
  return "IV";
}

function selectedFloorZoneForState(state) {
  if (!selected || selected.kind === "alerts") return "";
  const patients = state.patients || [];

  if (selected.kind === "patient") {
    const patient = patients.find((p) => p.id === selected.id);
    return patient ? zoneNameForPatient(patient) : "";
  }
  if (selected.kind === "nurse") {
    const nurse = (state.nurses || []).find((n) => n.id === selected.id);
    return nurse ? normalizeFloorZone(nurse.location || "nurses-station") : "";
  }
  if (selected.kind === "doctor") {
    const doctor = (state.doctors || []).find((d) => d.id === selected.id);
    return doctor ? normalizeFloorZone(doctorFloorLocation(doctor, patients)) : "";
  }
  if (selected.kind === "equipment") {
    const item = (state.equipment || []).find((e) => e.id === selected.id);
    return item ? normalizeFloorZone(equipmentFloorLocation(item, patients)) : "";
  }
  return "";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function wrapAngle(value) {
  const fullTurn = Math.PI * 2;
  let next = value % fullTurn;
  if (next <= -Math.PI) next += fullTurn;
  if (next > Math.PI) next -= fullTurn;
  return next;
}

function clampFloorTarget3d(view) {
  const minX = (FLOOR_3D.panMarginX - FLOOR_VIEWBOX.w / 2) * FLOOR_3D.scale;
  const maxX = ((FLOOR_VIEWBOX.w - FLOOR_3D.panMarginX) - FLOOR_VIEWBOX.w / 2) * FLOOR_3D.scale;
  const minZ = (FLOOR_3D.panMarginY - FLOOR_VIEWBOX.h / 2) * FLOOR_3D.scale;
  const maxZ = ((FLOOR_VIEWBOX.h - FLOOR_3D.panMarginY) - FLOOR_VIEWBOX.h / 2) * FLOOR_3D.scale;
  view.controls.target.x = clamp(view.controls.target.x, minX, maxX);
  view.controls.target.z = clamp(view.controls.target.z, minZ, maxZ);
}

// Token placement (reserveFloorPosition + its slot helpers) plus floorPercent / sameFloorPoint /
// escapeAttr are destructured from window.Floor near the top — the same primitives the replay page
// uses, so live and replay token coordinates are identical.
function floorMarker(kind, id, label, x, y, extraClass = "", title = "", nextPositions = null, caption = id) {
  const key = `${kind}:${id}`;
  const activeClass = selected && selected.kind === kind && selected.id === id ? " active" : "";
  const previous = floorPositions.get(key);
  const next = { x, y };
  const moved = !firstLoad && previous && !sameFloorPoint(previous, next);
  if (nextPositions) nextPositions.set(key, next);
  const markerTitle = title || `${kind} ${id}`;
  const style = [
    `left:${floorPercent(x, "x")}`,
    `top:${floorPercent(y, "y")}`,
    previous ? `--from-left:${floorPercent(previous.x, "x")}` : "",
    previous ? `--from-top:${floorPercent(previous.y, "y")}` : "",
    `--to-left:${floorPercent(x, "x")}`,
    `--to-top:${floorPercent(y, "y")}`,
  ].filter(Boolean).join(";");
  return `<button type="button" class="floor-token ${kind}${activeClass} ${moved ? "moving" : ""} ${extraClass}" data-key="${escapeAttr(key)}" data-floor-x="${escapeAttr(x)}" data-floor-y="${escapeAttr(y)}" style="${style}" title="${escapeAttr(markerTitle)}" aria-label="${escapeAttr(markerTitle)}">
    <span class="token-core">${escapeAttr(label)}</span>
    <span class="token-label">${escapeAttr(caption)}</span>
  </button>`;
}

// The 2D SVG blueprint (renderBlueprint) lives in floor.js (Floor.renderBlueprint) and is shared with
// the replay page; the no-WebGL fallback below calls it directly.
function floor3dAvailable() {
  return typeof window !== "undefined" && !!window.THREE && !!window.THREE.WebGLRenderer;
}

function floorWorld(x, y, height = 0) {
  const THREE = window.THREE;
  return new THREE.Vector3(
    (x - FLOOR_VIEWBOX.w / 2) * FLOOR_3D.scale,
    height,
    (y - FLOOR_VIEWBOX.h / 2) * FLOOR_3D.scale
  );
}

function disposeMaterial(material) {
  if (!material) return;
  if (Array.isArray(material)) {
    material.forEach(disposeMaterial);
    return;
  }
  if (material.map) material.map.dispose();
  material.dispose();
}

function disposeObject3d(object) {
  object.traverse((node) => {
    if (node.geometry) node.geometry.dispose();
    disposeMaterial(node.material);
  });
}

function clearGroup3d(group) {
  while (group.children.length) {
    const child = group.children.pop();
    disposeObject3d(child);
  }
}

function zoneBounds(zoneId) {
  const bayIds = ["cardiology", "general-a", "general-b"];
  const zones = !zoneId
    ? FLOOR_ZONES
    : zoneId === "general-a"
      ? FLOOR_ZONES.filter((zone) => bayIds.includes(zone.id))
      : FLOOR_ZONES.filter((zone) => zone.id === zoneId);

  const selectedZones = zones.length ? zones : FLOOR_ZONES;
  const left = Math.min(...selectedZones.map((zone) => zone.x));
  const top = Math.min(...selectedZones.map((zone) => zone.y));
  const right = Math.max(...selectedZones.map((zone) => zone.x + zone.w));
  const bottom = Math.max(...selectedZones.map((zone) => zone.y + zone.h));
  return {
    x: left,
    y: top,
    w: right - left,
    h: bottom - top,
    cx: left + (right - left) / 2,
    cy: top + (bottom - top) / 2,
  };
}

function focusMatches(buttonZone, activeZone) {
  if (!buttonZone) return !activeZone;
  if (buttonZone === "general-a") return ["cardiology", "general-a", "general-b"].includes(activeZone);
  return buttonZone === activeZone;
}

function updateFocusButtons3d(shell, activeZone) {
  shell.querySelectorAll("[data-view-zone]").forEach((button) => {
    button.classList.toggle("active", focusMatches(button.dataset.viewZone || "", activeZone));
  });
}

function wireFloorControls3d(shell) {
  shell.querySelectorAll("[data-view-action]").forEach((button) => {
    button.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!floorView) return;
      const action = button.dataset.viewAction;
      if (action === "zoom-in") {
        floorView.controls.distance = clamp(floorView.controls.distance * 0.82, FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
      } else if (action === "zoom-out") {
        floorView.controls.distance = clamp(floorView.controls.distance * 1.18, FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
      } else if (action === "top") {
        floorView.controls.pitch = FLOOR_3D.maxPitch;
        floorView.controls.distance = 17;
      } else if (action === "reset") {
        resetFloorCamera3d(floorView);
      }
    };
  });

  shell.querySelectorAll("[data-view-zone]").forEach((button) => {
    button.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      focusFloorZone3d(button.dataset.viewZone || "");
    };
  });
}

function ensureFloor3dShell(map) {
  let shell = map.querySelector(".floor-shell-3d");
  if (!shell) {
    map.innerHTML = `
      <div class="floor-shell floor-shell-3d">
        <div class="floor-canvas-wrap" aria-hidden="true"></div>
        <div class="floor-room-label-layer" aria-hidden="true"></div>
        <div class="floor-token-layer"></div>
        <div class="floor-hud" aria-hidden="true"></div>
        <div class="floor-view-controls" aria-label="3D map controls">
          <button type="button" data-view-action="zoom-in" title="Zoom in">+</button>
          <button type="button" data-view-action="zoom-out" title="Zoom out">-</button>
          <button type="button" data-view-action="top" title="Top view">Top</button>
          <button type="button" data-view-action="reset" title="Reset view">Reset</button>
        </div>
        <div class="floor-focus-strip">
          ${FLOOR_FOCUS_GROUPS.map((item) => `<button type="button" data-view-zone="${escapeAttr(item.zone)}">${escapeAttr(item.label)}</button>`).join("")}
        </div>
        <div class="floor-legend">
          <span><i class="legend-dot patient"></i>Patients</span>
          <span><i class="legend-dot nurse"></i>Nurses</span>
          <span><i class="legend-dot doctor"></i>Doctors</span>
          <span><i class="legend-dot bed"></i>Beds</span>
          <span><i class="legend-dot equipment"></i>Devices</span>
        </div>
      </div>
    `;
    shell = map.querySelector(".floor-shell-3d");
    initFloor3d(shell);
  } else if (!floorView || floorView.shell !== shell) {
    initFloor3d(shell);
  }
  wireFloorControls3d(shell);
  return shell;
}

function initFloor3d(shell) {
  const THREE = window.THREE;
  const container = shell.querySelector(".floor-canvas-wrap");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xf6f1e7);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 80);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  if (THREE.SRGBColorSpace) renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = false;
  container.replaceChildren(renderer.domElement);

  const modelGroup = new THREE.Group();
  scene.add(modelGroup);

  const ambient = new THREE.HemisphereLight(0xffffff, 0xcac1b0, 2.8);
  scene.add(ambient);

  const key = new THREE.DirectionalLight(0xffffff, 1.15);
  key.position.set(-4, 12, 8);
  key.castShadow = true;
  key.shadow.mapSize.width = 1024;
  key.shadow.mapSize.height = 1024;
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xe8eee9, 0.72);
  fill.position.set(8, 5, -8);
  scene.add(fill);

  floorView = {
    shell,
    container,
    scene,
    camera,
    renderer,
    modelGroup,
    tokenAnchors: new Map(),
    roomAnchors: new Map(),
    pickables: [],
    focusZone: "",
    raycaster: new THREE.Raycaster(),
    pointer: new THREE.Vector2(),
    controls: {
      yaw: FLOOR_3D.defaultYaw,
      pitch: FLOOR_3D.defaultPitch,
      distance: FLOOR_3D.defaultDistance,
      target: new THREE.Vector3(0, 0, 0),
    },
  };

  bindFloor3dControls(floorView);
  resizeFloor3d(floorView);
  startFloor3dLoop();
}

function bindFloor3dControls(view) {
  const { shell, container } = view;
  let drag = null;
  const runAction = (action) => {
    if (action === "zoom-in") {
      view.controls.distance = clamp(view.controls.distance * 0.82, FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
    } else if (action === "zoom-out") {
      view.controls.distance = clamp(view.controls.distance * 1.18, FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
    } else if (action === "top") {
      view.controls.pitch = FLOOR_3D.maxPitch;
      view.controls.distance = 17;
    } else if (action === "reset") {
      resetFloorCamera3d(view);
    }
  };

  shell.querySelectorAll("[data-view-action]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      runAction(button.dataset.viewAction);
    });
  });

  shell.querySelectorAll("[data-view-zone]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      focusFloorZone3d(button.dataset.viewZone || "");
    });
  });

  container.addEventListener("contextmenu", (event) => event.preventDefault());
  container.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 && event.button !== 2) return;
    container.setPointerCapture(event.pointerId);
    drag = {
      x: event.clientX,
      y: event.clientY,
      moved: false,
      mode: event.button === 2 || event.altKey ? "orbit" : "pan",
    };
    container.classList.add("dragging");
  });

  container.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    drag.x = event.clientX;
    drag.y = event.clientY;

    if (drag.mode === "pan") {
      const panScale = view.controls.distance * 0.0025;
      view.controls.target.x -= dx * panScale;
      view.controls.target.z -= dy * panScale;
      clampFloorTarget3d(view);
    } else {
      view.controls.yaw = wrapAngle(view.controls.yaw - dx * 0.004);
      view.controls.pitch = clamp(view.controls.pitch + dy * 0.004, FLOOR_3D.minPitch, FLOOR_3D.maxPitch);
    }
  });

  container.addEventListener("pointerup", (event) => {
    if (!drag) return;
    const wasClick = !drag.moved;
    drag = null;
    container.classList.remove("dragging");
    if (wasClick) pickFloorZone3d(view, event);
  });

  container.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomFloor3d(view, event.deltaY > 0 ? 1.1 : 0.9, event.clientX, event.clientY);
  }, { passive: false });

  shell.addEventListener("click", (event) => {
    const actionButton = event.target.closest("[data-view-action]");
    if (actionButton) {
      event.preventDefault();
      runAction(actionButton.dataset.viewAction);
      return;
    }

    const zoneButton = event.target.closest("[data-view-zone]");
    if (zoneButton) {
      event.preventDefault();
      focusFloorZone3d(zoneButton.dataset.viewZone || "");
    }
  });
}

function resetFloorCamera3d(view = floorView) {
  if (!view) return;
  view.controls.yaw = FLOOR_3D.defaultYaw;
  view.controls.pitch = FLOOR_3D.defaultPitch;
  view.controls.distance = FLOOR_3D.defaultDistance;
  view.controls.target.set(0, 0, 0);
  clampFloorTarget3d(view);
  view.focusZone = "";
  updateFocusButtons3d(view.shell, "");
}

function focusFloorZone3d(zoneId) {
  if (!floorView) return;
  const bounds = zoneBounds(zoneId);
  const center = floorWorld(bounds.cx, bounds.cy, 0);
  const span = Math.max(bounds.w, bounds.h) * FLOOR_3D.scale;
  floorView.controls.target.set(center.x, 0, center.z);
  clampFloorTarget3d(floorView);
  floorView.controls.yaw = FLOOR_3D.defaultYaw;
  floorView.controls.distance = clamp(span * (zoneId ? 2.6 : 1.05), FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
  floorView.controls.pitch = zoneId ? FLOOR_3D.focusPitch : FLOOR_3D.defaultPitch;
  floorView.focusZone = zoneId;
  updateFocusButtons3d(floorView.shell, zoneId);
}

function pickFloorZone3d(view, event) {
  const rect = view.renderer.domElement.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  view.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  view.pointer.y = -(((event.clientY - rect.top) / rect.height) * 2 - 1);
  view.raycaster.setFromCamera(view.pointer, view.camera);
  const hit = view.raycaster.intersectObjects(view.pickables, false)[0];
  if (hit && hit.object.userData.zoneId) focusFloorZone3d(hit.object.userData.zoneId);
}

function resizeFloor3d(view) {
  const width = Math.max(1, view.container.clientWidth);
  const height = Math.max(1, view.container.clientHeight);
  const canvas = view.renderer.domElement;
  if (canvas.width !== Math.round(width * view.renderer.getPixelRatio()) || canvas.height !== Math.round(height * view.renderer.getPixelRatio())) {
    view.renderer.setSize(width, height, false);
    const aspect = width / height;
    view.camera.left = -FLOOR_3D.orthoHeight * aspect / 2;
    view.camera.right = FLOOR_3D.orthoHeight * aspect / 2;
    view.camera.top = FLOOR_3D.orthoHeight / 2;
    view.camera.bottom = -FLOOR_3D.orthoHeight / 2;
    view.camera.updateProjectionMatrix();
  }
}

function floorPointerWorldPoint(view, clientX, clientY) {
  const rect = view.renderer.domElement.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  view.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  view.pointer.y = -(((clientY - rect.top) / rect.height) * 2 - 1);
  view.raycaster.setFromCamera(view.pointer, view.camera);
  const plane = new window.THREE.Plane(new window.THREE.Vector3(0, 1, 0), 0);
  const point = new window.THREE.Vector3();
  return view.raycaster.ray.intersectPlane(plane, point) ? point : null;
}

function zoomFloor3d(view, factor, clientX = null, clientY = null) {
  const before = clientX == null || clientY == null ? null : floorPointerWorldPoint(view, clientX, clientY);
  view.controls.distance = clamp(view.controls.distance * factor, FLOOR_3D.minDistance, FLOOR_3D.maxDistance);
  updateFloorCamera3d(view);
  // Keep the hovered room under the cursor while zooming so off-center areas stay reachable.
  if (before && clientX != null && clientY != null) {
    const after = floorPointerWorldPoint(view, clientX, clientY);
    if (after) view.controls.target.add(before.sub(after));
  }
  clampFloorTarget3d(view);
}

function updateFloorCamera3d(view) {
  const { camera, controls } = view;
  const zoom = clamp(FLOOR_3D.defaultDistance / controls.distance, FLOOR_3D.defaultDistance / FLOOR_3D.maxDistance, FLOOR_3D.defaultDistance / FLOOR_3D.minDistance);
  if (Math.abs(camera.zoom - zoom) > 0.001) {
    camera.zoom = zoom;
    camera.updateProjectionMatrix();
  }
  const horizontal = Math.cos(controls.pitch) * controls.distance;
  camera.position.set(
    controls.target.x + Math.sin(controls.yaw) * horizontal,
    Math.sin(controls.pitch) * controls.distance,
    controls.target.z + Math.cos(controls.yaw) * horizontal
  );
  camera.lookAt(controls.target.x, 0, controls.target.z);
}

function startFloor3dLoop() {
  if (floorView.animationId) return;
  const render = () => {
    if (!floorView) return;
    resizeFloor3d(floorView);
    updateFloorCamera3d(floorView);
    floorView.renderer.render(floorView.scene, floorView.camera);
    syncFloorRoomLabels3d();
    syncFloorTokenPositions3d();
    floorView.animationId = requestAnimationFrame(render);
  };
  render();
}

function roomMaterial3d(zone, active) {
  const THREE = window.THREE;
  return new THREE.MeshStandardMaterial({
    color: active ? 0xd8ddd9 : ROOM_3D_COLORS[zone.id] || 0xece9e2,
    roughness: 0.97,
    metalness: 0,
    transparent: true,
    opacity: active ? 0.98 : 0.92,
  });
}

function addRoom3d(view, zone, active) {
  const THREE = window.THREE;
  const height = active ? 0.06 : 0.03;
  const geometry = new THREE.BoxGeometry(zone.w * FLOOR_3D.scale, height, zone.h * FLOOR_3D.scale);
  const mesh = new THREE.Mesh(geometry, roomMaterial3d(zone, active));
  const center = floorWorld(zone.x + zone.w / 2, zone.y + zone.h / 2, height / 2);
  mesh.position.copy(center);
  mesh.receiveShadow = true;
  mesh.userData.zoneId = zone.id;
  view.modelGroup.add(mesh);
  view.pickables.push(mesh);

  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({ color: active ? 0x6d7d78 : 0xa29d93, transparent: true, opacity: active ? 0.44 : 0.18 })
  );
  edges.position.copy(center);
  view.modelGroup.add(edges);
  view.roomAnchors.set(zone.id, {
    label: zone.label,
    position: floorWorld(zone.x + zone.w / 2, zone.y + zone.h / 2, active ? 0.16 : 0.12),
  });
}

function addWall3d(view, wall) {
  const THREE = window.THREE;
  const [x1, y1, x2, y2] = wall;
  const horizontal = Math.abs(x2 - x1) >= Math.abs(y2 - y1);
  const length = Math.max(Math.abs(horizontal ? x2 - x1 : y2 - y1) * FLOOR_3D.scale, 0.1);
  const thickness = 0.042;
  const height = 0.28;
  const geometry = horizontal
    ? new THREE.BoxGeometry(length, height, thickness)
    : new THREE.BoxGeometry(thickness, height, length);
  const material = new THREE.MeshStandardMaterial({ color: 0x767166, roughness: 0.98, metalness: 0 });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(floorWorld((x1 + x2) / 2, (y1 + y2) / 2, height / 2 + 0.02));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  view.modelGroup.add(mesh);
}

function addGround3d(view) {
  const THREE = window.THREE;
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(23.4, 0.035, 14.8),
    new THREE.MeshStandardMaterial({ color: 0xf1efea, roughness: 0.99, metalness: 0 })
  );
  base.position.y = -0.035;
  base.receiveShadow = true;
  view.modelGroup.add(base);

  const grid = new THREE.GridHelper(24, 24, 0xc3c0b8, 0xe6e4de);
  grid.position.y = 0.012;
  grid.material.transparent = true;
  grid.material.opacity = 0.06;
  view.modelGroup.add(grid);
}

function addBed3d(view, bed) {
  const THREE = window.THREE;
  const layout = BED_LAYOUT[bed.id];
  if (!layout) return;
  const group = new THREE.Group();
  group.position.copy(floorWorld(layout.x, layout.y, 0.075));
  const statusColor = bed.status === "occupied" ? 0xa97432 : bed.status === "cleaning" ? 0x668d95 : 0x7c9a87;
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(0.82, 0.045, 1.18),
    new THREE.MeshStandardMaterial({ color: statusColor, roughness: 0.96, metalness: 0 })
  );
  base.position.y = 0.045;
  base.castShadow = true;
  group.add(base);

  const mattress = new THREE.Mesh(
    new THREE.BoxGeometry(0.7, 0.035, 0.94),
    new THREE.MeshStandardMaterial({ color: 0xf8f5ee, roughness: 0.96, metalness: 0 })
  );
  mattress.position.y = 0.105;
  mattress.castShadow = true;
  group.add(mattress);

  const pillow = new THREE.Mesh(
    new THREE.BoxGeometry(0.58, 0.026, 0.22),
    new THREE.MeshStandardMaterial({ color: 0xdfe8e4, roughness: 0.96, metalness: 0 })
  );
  pillow.position.set(0, 0.145, -0.34);
  group.add(pillow);
  view.modelGroup.add(group);
}

function markerColor3d(marker) {
  const cls = marker.extraClass || "";
  if (cls.includes("status-alert")) return TOKEN_3D_COLORS.alert;
  if (cls.includes("status-occupied") || cls.includes("status-busy")) return TOKEN_3D_COLORS.busy;
  if (cls.includes("status-available") || cls.includes("status-free")) return TOKEN_3D_COLORS.ok;
  return TOKEN_3D_COLORS[marker.kind] || TOKEN_3D_COLORS.equipment;
}

function addMarker3d(view, marker) {
  const THREE = window.THREE;
  const key = `${marker.kind}:${marker.id}`;
  const active = selected && selected.kind === marker.kind && selected.id === marker.id;
  const group = new THREE.Group();
  group.position.copy(floorWorld(marker.x, marker.y, 0.08));
  group.userData.labelHeight = active ? 0.46 : 0.38;

  const color = markerColor3d(marker);
  const radius = marker.kind === "bed" ? 0.12 : active ? 0.2 : 0.16;
  const disk = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius, 0.045, 36),
    new THREE.MeshStandardMaterial({ color, roughness: 0.95, metalness: 0 })
  );
  disk.position.y = 0.08;
  disk.castShadow = true;
  group.add(disk);

  const outline = new THREE.Mesh(
    new THREE.TorusGeometry(radius + 0.035, 0.012, 6, 36),
    new THREE.MeshBasicMaterial({ color: active ? 0x667a74 : 0xf7f6f2, transparent: true, opacity: active ? 0.9 : 0.52 })
  );
  outline.rotation.x = Math.PI / 2;
  outline.position.y = 0.115;
  group.add(outline);

  if (active) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.34, 0.016, 8, 48),
      new THREE.MeshBasicMaterial({ color: 0x667a74, transparent: true, opacity: 0.62 })
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.035;
    group.add(ring);
  }

  view.tokenAnchors.set(key, group);
  view.modelGroup.add(group);
}

function updateFloor3dScene(shell, state, markers, activeZone) {
  if (!floorView) return;
  clearGroup3d(floorView.modelGroup);
  floorView.pickables = [];
  floorView.tokenAnchors.clear();
  floorView.roomAnchors.clear();
  addGround3d(floorView);

  const highlightedZone = activeZone || floorView.focusZone || "";
  FLOOR_ZONES.forEach((zone) => addRoom3d(floorView, zone, !!highlightedZone && focusMatches(highlightedZone, zone.id)));
  FLOOR_WALLS.forEach((wall) => addWall3d(floorView, wall));
  (state.beds || []).forEach((bed) => addBed3d(floorView, bed));
  markers.forEach((marker) => addMarker3d(floorView, marker));

  const labelLayer = shell.querySelector(".floor-room-label-layer");
  if (labelLayer) {
    labelLayer.innerHTML = FLOOR_ZONES.map((zone) => {
      const active = !!highlightedZone && focusMatches(highlightedZone, zone.id);
      return `<span class="floor-room-label ${active ? "active" : ""}" data-zone="${escapeAttr(zone.id)}">${escapeAttr(zone.label)}</span>`;
    }).join("");
  }

  updateFocusButtons3d(shell, activeZone || floorView.focusZone || "");
}

function syncFloorTokenPositions3d() {
  if (!floorView) return;
  const overlay = floorView.shell.querySelector(".floor-token-layer");
  if (!overlay) return;
  const canvasRect = floorView.renderer.domElement.getBoundingClientRect();
  const shellRect = floorView.shell.getBoundingClientRect();
  if (!canvasRect.width || !canvasRect.height) return;

  const world = new window.THREE.Vector3();
  overlay.querySelectorAll(".floor-token").forEach((token) => {
    const anchor = floorView.tokenAnchors.get(token.dataset.key);
    if (!anchor) return;
    anchor.getWorldPosition(world);
    world.y += anchor.userData.labelHeight || 0.78;
    world.project(floorView.camera);
    const visible = world.z > -1 && world.z < 1;
    const x = (world.x * 0.5 + 0.5) * canvasRect.width + canvasRect.left - shellRect.left;
    const y = (-world.y * 0.5 + 0.5) * canvasRect.height + canvasRect.top - shellRect.top;
    token.style.left = `${x}px`;
    token.style.top = `${y}px`;
    token.style.opacity = visible ? "1" : "0";
    token.style.pointerEvents = visible ? "auto" : "none";
    token.style.zIndex = String(Math.round((1 - world.z) * 100) + 10);
  });
}

function syncFloorRoomLabels3d() {
  if (!floorView) return;
  const layer = floorView.shell.querySelector(".floor-room-label-layer");
  if (!layer) return;
  const canvasRect = floorView.renderer.domElement.getBoundingClientRect();
  const shellRect = floorView.shell.getBoundingClientRect();
  if (!canvasRect.width || !canvasRect.height) return;

  const projected = new window.THREE.Vector3();
  layer.querySelectorAll(".floor-room-label").forEach((label) => {
    const anchor = floorView.roomAnchors.get(label.dataset.zone);
    if (!anchor) return;
    projected.copy(anchor.position).project(floorView.camera);
    const visible = projected.z > -1 && projected.z < 1;
    const x = (projected.x * 0.5 + 0.5) * canvasRect.width + canvasRect.left - shellRect.left;
    const y = (-projected.y * 0.5 + 0.5) * canvasRect.height + canvasRect.top - shellRect.top;
    label.style.left = `${x}px`;
    label.style.top = `${y}px`;
    label.style.opacity = visible ? "" : "0";
  });
}

function renderFloorMap(state) {
  const map = $("floor-map");
  const patients = state.patients || [];
  const nurses = state.nurses || [];
  const doctors = state.doctors || [];
  const activeZone = selectedFloorZoneForState(state);
  const patientsById = Object.fromEntries(patients.map((p) => [p.id, p]));

  const nextFloorPositions = new Map();
  const markers = [];
  const markerModels = [];
  const addMarker = (kind, id, label, x, y, extraClass = "", title = "", caption = id) => {
    markerModels.push({ kind, id, label, x, y, extraClass, title, caption });
    markers.push(floorMarker(kind, id, label, x, y, extraClass, title, nextFloorPositions, caption));
  };

  // Token positions come from the shared Floor.placeEntities so the live 3D map and the replay 2D
  // map land every entity on the exact same spot. Patients get the dashboard's richer presentation
  // (monogram glyph, name caption, floor-zone label) layered on top of the shared placement.
  Floor.placeEntities(state).forEach((spec) => {
    let { label, title } = spec;
    let caption = spec.id;
    if (spec.kind === "patient") {
      const patient = patientsById[spec.id];
      if (patient) {
        label = patientMonogram(patient);
        title = `${patient.name || patient.id}: ${patientFloorLabel(patient)}`;
        caption = patient.name || patient.id;
      }
    }
    addMarker(spec.kind, spec.id, label, spec.x, spec.y, spec.cls, title, caption);
  });

  const use3d = floor3dAvailable();
  let tokenRoot = map;
  if (use3d) {
    const shell = ensureFloor3dShell(map);
    shell.querySelector(".floor-hud").innerHTML = `
      <span>ER-01</span>
      <span>${patients.filter((p) => p.status !== "discharged").length} patients</span>
      <span>${nurses.length + doctors.length} staff</span>
      <span>3D</span>
    `;
    tokenRoot = shell.querySelector(".floor-token-layer");
    tokenRoot.innerHTML = markers.join("");
    updateFloor3dScene(shell, state, markerModels, activeZone);
    syncFloorRoomLabels3d();
    syncFloorTokenPositions3d();
  } else {
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
          <span><i class="legend-dot bed"></i>Beds</span>
          <span><i class="legend-dot equipment"></i>Devices</span>
        </div>
      </div>
    `;
  }
  floorPositions = nextFloorPositions;

  tokenRoot.querySelectorAll(".floor-token").forEach((node) => {
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
      const monogram = patientMonogram(p);
      const mapCue = `Marker ${monogram} - ${patientFloorLabel(p)}`;
      const card = el("button", `card interactive-card ${diffClass("patient", p.id, p)}`);
      card.type = "button";
      card.dataset.key = `patient:${p.id}`;
      card.onclick = () => toggleSelection("patient", p.id);
      card.append(
        el("div", "card-top", `<div class="patient-heading"><span class="patient-icon" aria-hidden="true">${monogram}</span><strong class="patient-name">${p.name || p.id}</strong></div><span class="pill acuity-${p.acuity}">ESI ${p.acuity ?? "—"}</span>`),
        el("div", "card-line", `${p.chief_complaint || "—"} · ${p.status}`),
        el("div", "card-line muted", `HR ${v.hr ?? "—"} · SpO₂ ${v.spo2 ?? "—"} · BP ${v.bp ?? "—"}`),
        el("div", "card-line muted", `Bed ${p.assigned_bed || "—"} · Team ${(p.care_team || []).join(", ") || "—"}`),
        el("div", "card-hint card-map-cue", mapCue)
      );
      return card;
    })
  );
}

function renderStaff(nurses, doctors, patients = []) {
  const mk = (s, role, type) => {
    const free = s.available;
    const marker = type === "nurse" ? "N" : "D";
    const location = type === "doctor" ? doctorFloorLocation(s, patients) : s.location || "nurses-station";
    const mapCue = `Marker ${marker} - ${floorZoneLabel(location)}`;
    const card = el("button", `card interactive-card ${diffClass(type, s.id, s)}`);
    card.type = "button";
    card.dataset.key = `${type}:${s.id}`;
    card.onclick = () => toggleSelection(type, s.id);
    card.append(
      el("div", "card-top", `<strong>${s.id}</strong><span class="pill ${free ? "ok" : "busy"}">${free ? "free" : "busy"}</span>`),
      el("div", "card-line muted", `${role}${s.specialty ? " · " + s.specialty : ""}${s.location ? " · " + s.location : ""}`),
      el("div", "card-line muted", `Assigned: ${(s.assignments || []).join(", ") || "—"}`),
      el("div", "card-hint card-map-cue", mapCue)
    );
    return card;
  };
  const cards = [...nurses.map((n) => mk(n, "nurse", "nurse")), ...doctors.map((d) => mk(d, "doctor", "doctor"))];
  $("staff").replaceChildren(...(cards.length ? cards : [el("p", "empty", "No staff on shift.")]));
}

function renderEquipment(equipment, patients = []) {
  const root = $("equipment");
  if (!equipment.length) return root.replaceChildren(el("p", "empty", "No equipment tracked."));
  root.replaceChildren(
    ...equipment.map((e) => {
      const low = isLowO2(e);
      const card = el("button", `card interactive-card ${low ? "card-alert" : ""} ${diffClass("equipment", e.id, e)}`);
      card.type = "button";
      card.dataset.key = `equipment:${e.id}`;
      card.onclick = () => toggleSelection("equipment", e.id);
      const level = e.supply_level != null ? `${e.supply_level}%` : e.in_use_by ? "in use" : "available";
      const mapCue = `Marker ${equipmentMarkerLabel(e)} - ${floorZoneLabel(equipmentFloorLocation(e, patients))}`;
      card.append(
        el("div", "card-top", `<strong>${e.id}</strong><span class="pill ${low ? "busy" : "ok"}">${level}</span>`),
        el("div", "card-line muted", `${e.type} · ${e.location || "—"}${e.in_use_by ? " · " + e.in_use_by : ""}`),
        el("div", "card-hint card-map-cue", mapCue)
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
    renderStaff(state.nurses || [], state.doctors || [], state.patients || []);
    renderEquipment(state.equipment || [], state.patients || []);
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
