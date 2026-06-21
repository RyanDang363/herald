// Shared ER floor map: layout geometry, entity → position logic, and the blueprint SVG.
// Imported (as window.Floor) by BOTH the live dashboard (app.js) and the replay page (replay.js),
// so the replay map is byte-for-byte the same floor as the live dashboard. @spec REPLAY-FRAME-001
//
// This is pure geometry + a pure `placeEntities(state)` — no app state, no DOM, no animation. The
// callers wrap each placement spec in their own marker renderer (the dashboard adds change-flash +
// selection; the replay page tweens between snapshots).
"use strict";

(function (global) {
  const LOW_O2 = 50;
  const isLowO2 = (e) =>
    e && e.type === "oxygen" && e.supply_level != null && e.supply_level < LOW_O2;

  const FLOOR_VIEWBOX = { w: 1000, h: 620 };
  const PATIENT_ROOM_IDS = ["cardiology", "general-a", "general-b", "general-c", "general-d", "general-e", "general-f", "general-g"];
  const PATIENT_ROOM_W = 110;
  const PATIENT_ROOM_X = 60;
  const PATIENT_ROOM_Y = 70;
  const PATIENT_ROOM_H = 170;

  const FLOOR_ZONES = [
    ...PATIENT_ROOM_IDS.map((id, index) => ({
      id,
      label: `Room ${index + 1}`,
      x: PATIENT_ROOM_X + index * PATIENT_ROOM_W,
      y: PATIENT_ROOM_Y,
      w: PATIENT_ROOM_W,
      h: PATIENT_ROOM_H,
    })),
    { id: "waiting", label: "Waiting", x: 60, y: 350, w: 220, h: 200 },
    { id: "triage", label: "Triage", x: 760, y: 280, w: 180, h: 115 },
    { id: "trauma", label: "Trauma", x: 760, y: 395, w: 180, h: 155 },
    { id: "nurses-station", label: "Nurse Station", x: 390, y: 360, w: 200, h: 130 },
    { id: "storage", label: "Supply", x: 590, y: 360, w: 120, h: 130 },
    { id: "corridor", label: "Main Corridor", x: 60, y: 240, w: 700, h: 310 },
  ];

  const BED_LAYOUT = {
    bed1: { zone: "cardiology", x: 115, y: 155 },
    bed2: { zone: "general-a", x: 225, y: 155 },
    bed3: { zone: "general-b", x: 335, y: 155 },
    bed4: { zone: "general-c", x: 445, y: 155 },
    bed5: { zone: "general-d", x: 555, y: 155 },
    bed6: { zone: "general-e", x: 665, y: 155 },
    bed7: { zone: "general-f", x: 775, y: 155 },
    bed8: { zone: "general-g", x: 885, y: 155 },
  };

  const FLOOR_LABELS = {
    waiting: { x: 76, y: 382 },
    triage: { x: 776, y: 310 },
    trauma: { x: 776, y: 426 },
    "nurses-station": { x: 406, y: 395 },
    storage: { x: 606, y: 395 },
    cardiology: { x: 76, y: 104 },
    "general-a": { x: 186, y: 104 },
    "general-b": { x: 296, y: 104 },
    "general-c": { x: 406, y: 104 },
    "general-d": { x: 516, y: 104 },
    "general-e": { x: 626, y: 104 },
    "general-f": { x: 736, y: 104 },
    "general-g": { x: 846, y: 104 },
    corridor: { x: 300, y: 288 },
  };

  const PATIENT_ROOM_WALLS = [
    ...[170, 280, 390, 500, 610, 720, 830].map((x) => [x, 70, x, 240]),
    ...Array.from({ length: 8 }, (_, index) => {
      const left = PATIENT_ROOM_X + index * PATIENT_ROOM_W;
      const center = left + PATIENT_ROOM_W / 2;
      return [
        [left, 240, center - 18, 240],
        [center + 18, 240, left + PATIENT_ROOM_W, 240],
      ];
    }).flat(),
  ];

  // Interior + perimeter wall segments [x1, y1, x2, y2]. Single source for both the 2D blueprint
  // below and the live dashboard's 3D wall extrusion (app.js reads these via window.Floor).
  const FLOOR_WALLS = [
    [60, 70, 940, 70],
    [940, 70, 940, 550],
    [940, 550, 60, 550],
    [60, 550, 60, 70],
    ...PATIENT_ROOM_WALLS,
    [60, 350, 280, 350],
    [280, 350, 280, 425],
    [280, 465, 280, 550],
    [390, 360, 455, 360],
    [515, 360, 710, 360],
    [390, 360, 390, 490],
    [390, 490, 590, 490],
    [590, 360, 590, 490],
    [590, 490, 710, 490],
    [710, 360, 760, 360],
    [760, 280, 940, 280],
    [760, 280, 760, 315],
    [760, 355, 760, 455],
    [760, 495, 760, 550],
    [760, 395, 940, 395],
  ];

  const FLOOR_ZONE_ALIASES = {
    supply: "storage",
    "supply-room": "storage",
    "nurse-station": "nurses-station",
    "cardiac-bay": "cardiology",
    "general-bay-1": "cardiology",
    "general-bay-2": "general-a",
    "general-bay-3": "general-b",
    "general-bay-4": "general-c",
    "general-bay-5": "general-d",
    "general-bay-6": "general-e",
    "general-bay-7": "general-f",
    "general-bay-8": "general-g",
    "room-1": "cardiology",
    "room-2": "general-a",
    "room-3": "general-b",
    "room-4": "general-c",
    "room-5": "general-d",
    "room-6": "general-e",
    "room-7": "general-f",
    "room-8": "general-g",
    cardiac: "cardiology",
    "general-bay-a": "general-a",
    "general-bay-b": "general-b",
  };

  function normalizedFloorId(value) {
    const raw = String(value || "corridor").trim().toLowerCase().replaceAll("_", "-").replace(/\s+/g, "-");
    return FLOOR_ZONE_ALIASES[raw] || raw;
  }

  function normalizeFloorLocation(value) {
    const normalized = normalizedFloorId(value);
    if (BED_LAYOUT[normalized] || FLOOR_ZONES.some((zone) => zone.id === normalized)) return normalized;
    return "corridor";
  }

  function normalizeFloorZone(value) {
    const normalized = normalizeFloorLocation(value);
    return BED_LAYOUT[normalized] ? BED_LAYOUT[normalized].zone : normalized;
  }

  function zoneNameForPatient(patient) {
    if (patient.assigned_bed && BED_LAYOUT[patient.assigned_bed]) return BED_LAYOUT[patient.assigned_bed].zone;
    if (patient.status === "in_triage") return "triage";
    if (patient.status === "waiting") return "waiting";
    return "corridor";
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  const BED_TOKEN_SLOTS = {
    bed: [{ dx: 0, dy: 0 }],
    patient: [{ dx: 42, dy: -22 }, { dx: 42, dy: 14 }],
    doctor: [{ dx: -46, dy: -14 }, { dx: -14, dy: -46 }, { dx: 14, dy: -46 }],
    nurse: [{ dx: -46, dy: 30 }, { dx: -46, dy: 62 }, { dx: -10, dy: 66 }],
    equipment: [{ dx: 54, dy: 20 }, { dx: 54, dy: 58 }, { dx: 14, dy: 66 }, { dx: -28, dy: 66 }, { dx: -54, dy: 0 }],
  };

  function overflowSlot(index) {
    const angle = index * 2.399963;
    const radius = 34 + Math.floor(index / 6) * 24;
    return {
      dx: Math.round(Math.cos(angle) * radius),
      dy: Math.round(Math.sin(angle) * radius),
    };
  }

  function positionForBedSlot(bedId, role, index) {
    const bed = BED_LAYOUT[bedId];
    const zone = FLOOR_ZONES.find((z) => z.id === bed.zone);
    const slots = BED_TOKEN_SLOTS[role] || BED_TOKEN_SLOTS.equipment;
    const slot = slots[index] || overflowSlot(index - slots.length + 1);
    return {
      x: clamp(bed.x + slot.dx, zone.x + 28, zone.x + zone.w - 28),
      y: clamp(bed.y + slot.dy, zone.y + 38, zone.y + zone.h - 24),
    };
  }

  function positionForRoomSlot(roomId, index) {
    const zoneId = normalizeFloorZone(roomId);
    const zone = FLOOR_ZONES.find((z) => z.id === zoneId) || FLOOR_ZONES.find((z) => z.id === "corridor");
    const usableWidth = Math.max(44, zone.w - 56);
    const columns = Math.max(1, Math.min(4, Math.floor(usableWidth / 48)));
    const col = index % columns;
    const row = Math.floor(index / columns);
    return {
      x: clamp(zone.x + 34 + col * 48, zone.x + 30, zone.x + zone.w - 30),
      y: clamp(zone.y + 66 + row * 42, zone.y + 48, zone.y + zone.h - 28),
    };
  }

  function reserveFloorPosition(placements, location, role) {
    const group = normalizeFloorLocation(location);
    if (BED_LAYOUT[group]) {
      const roleKey = `${group}:${role}`;
      const roleIndex = placements.get(roleKey) || 0;
      placements.set(roleKey, roleIndex + 1);
      return positionForBedSlot(group, role, roleIndex);
    }
    const roomIndex = placements.get(group) || 0;
    placements.set(group, roomIndex + 1);
    return positionForRoomSlot(group, roomIndex);
  }

  function floorPercent(value, axis) {
    const total = axis === "x" ? FLOOR_VIEWBOX.w : FLOOR_VIEWBOX.h;
    return `${(value / total) * 100}%`;
  }

  function sameFloorPoint(a, b) {
    return !!a && !!b && Math.abs(a.x - b.x) <= 1 && Math.abs(a.y - b.y) <= 1;
  }

  function escapeAttr(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll('"', "&quot;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  // Compute an ordered list of marker placement specs for every entity in a snapshot/state.
  // Returns [{ kind, id, label, x, y, cls, title }] — the SAME placement the dashboard uses, so the
  // replay map matches the live floor. @spec REPLAY-FRAME-001
  function placeEntities(state) {
    const byId = (a, b) => String(a.id || "").localeCompare(String(b.id || ""));
    const beds = [...(state.beds || [])].sort(byId);
    const patients = [...(state.patients || [])].sort(byId);
    const nurses = [...(state.nurses || [])].sort(byId);
    const doctors = [...(state.doctors || [])].sort(byId);
    const equipment = [...(state.equipment || [])].sort(byId);

    const bedPatient = Object.fromEntries(patients.filter((p) => p.assigned_bed).map((p) => [p.assigned_bed, p]));
    const specs = [];
    const placements = new Map();

    for (const bed of beds) {
      const pos = reserveFloorPosition(placements, bed.id, "bed");
      specs.push({ kind: "bed", id: bed.id, label: "B", x: pos.x, y: pos.y, cls: `status-${bed.status || "available"}`, title: `${bed.id}: ${bed.status || "available"}` });
      const patient = bedPatient[bed.id];
      if (patient) {
        const pp = reserveFloorPosition(placements, patient.assigned_bed, "patient");
        specs.push({ kind: "patient", id: patient.id, label: "P", x: pp.x, y: pp.y, cls: "", title: `${patient.name || patient.id}: ${patient.status || "patient"}` });
      }
    }

    patients
      .filter((p) => !p.assigned_bed)
      .forEach((patient) => {
        const zone = zoneNameForPatient(patient);
        const pos = reserveFloorPosition(placements, zone, "patient");
        specs.push({ kind: "patient", id: patient.id, label: "P", x: pos.x, y: pos.y, cls: "", title: `${patient.name || patient.id}: ${patient.status || "patient"}` });
      });

    nurses.forEach((nurse) => {
      // An assigned nurse stands at their patient's bed (like doctors) so the care team visibly
      // converges on a new admit during replay; an unassigned nurse stays at their location/station.
      const assignedPatient = patients.find((p) => (nurse.assignments || []).includes(p.id));
      const location = assignedPatient && assignedPatient.assigned_bed && BED_LAYOUT[assignedPatient.assigned_bed]
        ? assignedPatient.assigned_bed
        : nurse.location || "nurses-station";
      const pos = reserveFloorPosition(placements, location, "nurse");
      specs.push({ kind: "nurse", id: nurse.id, label: "N", x: pos.x, y: pos.y, cls: nurse.available ? "status-free" : "status-busy", title: `${nurse.id}: ${nurse.available ? "available" : "busy"}` });
    });

    doctors.forEach((doctor) => {
      const assignedPatient = patients.find((p) => (doctor.assignments || []).includes(p.id));
      const location = assignedPatient && assignedPatient.assigned_bed && BED_LAYOUT[assignedPatient.assigned_bed]
        ? assignedPatient.assigned_bed
        : doctor.location || (doctor.specialty === "cardiology" ? "cardiology" : "nurses-station");
      const pos = reserveFloorPosition(placements, location, "doctor");
      specs.push({ kind: "doctor", id: doctor.id, label: "D", x: pos.x, y: pos.y, cls: doctor.available ? "status-free" : "status-busy", title: `${doctor.id}: ${doctor.available ? "available" : "busy"}` });
    });

    equipment.forEach((item) => {
      let location;
      if (item.location && BED_LAYOUT[item.location]) {
        location = item.location;
      } else if (item.in_use_by) {
        const patient = patients.find((p) => p.id === item.in_use_by);
        location = patient && patient.assigned_bed ? patient.assigned_bed : "storage";
      } else {
        location = item.location || "storage";
      }
      const pos = reserveFloorPosition(placements, location, "equipment");
      const cls = isLowO2(item) ? "status-alert" : "";
      const level = item.supply_level != null ? `, ${item.supply_level}%` : "";
      const label = item.type === "oxygen" ? "O2" : item.type === "defibrillator" ? "DF" : "IV";
      specs.push({ kind: "equipment", id: item.id, label, x: pos.x, y: pos.y, cls, title: `${item.id}: ${item.type}${level}` });
    });

    return specs;
  }

  function renderBlueprint() {
    const room = (id, fillClass) => {
      const zone = FLOOR_ZONES.find((z) => z.id === id);
      const label = FLOOR_LABELS[id] || { x: zone.x + 16, y: zone.y + 26 };
      return `<g class="bp-room ${fillClass}">
        <rect x="${zone.x}" y="${zone.y}" width="${zone.w}" height="${zone.h}" />
        <text x="${label.x}" y="${label.y}">${zone.label}</text>
      </g>`;
    };

    const wall = (x1, y1, x2, y2) => `<path class="bp-wall" d="M${x1} ${y1} L${x2} ${y2}" />`;
    const door = (x1, y1, x2, y2, swing = "") => `
      <path class="bp-door-gap" d="M${x1} ${y1} L${x2} ${y2}" />
      ${swing ? `<path class="bp-door-swing" d="${swing}" />` : ""}
    `;

    const bedFixture = (id) => {
      const bed = BED_LAYOUT[id];
      return `<g class="bp-bed-fixture">
        <rect x="${bed.x - 18}" y="${bed.y - 26}" width="36" height="52" rx="10" />
        <rect x="${bed.x - 12}" y="${bed.y - 18}" width="24" height="16" rx="6" />
        <text x="${bed.x}" y="${bed.y + 46}">${id.toUpperCase()}</text>
      </g>`;
    };
    const patientRoomDoors = Array.from({ length: 8 }, (_, index) => {
      const left = PATIENT_ROOM_X + index * PATIENT_ROOM_W;
      const center = left + PATIENT_ROOM_W / 2;
      return door(center - 18, 240, center + 18, 240, `M${center - 18} 240 Q${center - 18} 266 ${center + 8} 266`);
    }).join("");

    return `
      <svg class="floor-blueprint" viewBox="0 0 1000 620" aria-hidden="true">
        <path class="bp-footprint-shadow" d="M60 70 H940 V550 H60 Z" />
        <path class="bp-footprint" d="M60 70 H940 V550 H60 Z" />
        ${room("corridor", "corridor")}
        ${room("waiting", "soft")}
        ${room("nurses-station", "core")}
        ${room("storage", "support")}
        ${room("triage", "triage")}
        ${room("trauma", "alert")}
        ${PATIENT_ROOM_IDS.map((id) => room(id, "bay")).join("")}

        ${FLOOR_WALLS.map(([x1, y1, x2, y2]) => wall(x1, y1, x2, y2)).join("")}

        ${patientRoomDoors}
        ${door(455, 360, 515, 360, "M455 360 Q455 328 487 328")}
        ${door(710, 360, 760, 360, "M710 360 Q710 334 748 334")}
        ${door(760, 315, 760, 355, "M760 315 Q732 315 732 343")}
        ${door(760, 455, 760, 495, "M760 455 Q732 455 732 483")}
        ${door(280, 425, 280, 465, "M280 425 Q308 425 308 453")}
        ${Object.keys(BED_LAYOUT).map(bedFixture).join("")}
        <text class="bp-small bp-exit-label main" x="180" y="610">Main Entrance</text>
        <text class="bp-small bp-exit-label ambulance" x="986" y="318" transform="rotate(90 986 318)">Ambulance Bay</text>
        <text class="bp-small bp-exit-label ambulance" x="986" y="460" transform="rotate(90 986 460)">Ambulance Bay</text>
        <path class="bp-exit-arrow" d="M180 566 V590" />
        <path class="bp-exit-arrow" d="M954 318 H980" />
        <path class="bp-exit-arrow" d="M954 460 H980" />
      </svg>
    `;
  }

  global.Floor = {
    LOW_O2,
    isLowO2,
    FLOOR_ZONES,
    FLOOR_VIEWBOX,
    PATIENT_ROOM_IDS,
    BED_LAYOUT,
    FLOOR_LABELS,
    FLOOR_WALLS,
    normalizeFloorLocation,
    normalizeFloorZone,
    zoneNameForPatient,
    reserveFloorPosition,
    floorPercent,
    sameFloorPoint,
    escapeAttr,
    placeEntities,
    renderBlueprint,
  };
})(window);
