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

  const FLOOR_ZONES = [
    { id: "waiting", label: "Waiting", x: 60, y: 350, w: 220, h: 200 },
    { id: "triage", label: "Triage", x: 760, y: 220, w: 180, h: 165 },
    { id: "trauma", label: "Trauma", x: 760, y: 385, w: 180, h: 165 },
    { id: "nurses-station", label: "Nurse Station", x: 440, y: 360, w: 200, h: 130 },
    { id: "storage", label: "Supply", x: 640, y: 360, w: 120, h: 130 },
    { id: "cardiology", label: "General Bay 1", x: 280, y: 70, w: 160, h: 170 },
    { id: "general-a", label: "General Bay 2", x: 440, y: 70, w: 160, h: 170 },
    { id: "general-b", label: "General Bay 3", x: 600, y: 70, w: 160, h: 170 },
    { id: "corridor", label: "Main Corridor", x: 280, y: 240, w: 480, h: 310 },
  ];

  const FLOOR_VIEWBOX = { w: 1000, h: 620 };

  const BED_LAYOUT = {
    bed1: { zone: "cardiology", x: 360, y: 155 },
    bed2: { zone: "general-a", x: 520, y: 155 },
    bed3: { zone: "general-b", x: 680, y: 155 },
    bed4: { zone: "trauma", x: 850, y: 470 },
  };

  const FLOOR_LABELS = {
    waiting: { x: 76, y: 382 },
    triage: { x: 776, y: 250 },
    trauma: { x: 776, y: 416 },
    "nurses-station": { x: 456, y: 395 },
    storage: { x: 656, y: 395 },
    cardiology: { x: 296, y: 104 },
    "general-a": { x: 456, y: 104 },
    "general-b": { x: 616, y: 104 },
    corridor: { x: 300, y: 288 },
  };

  const FLOOR_ZONE_ALIASES = {
    supply: "storage",
    "supply-room": "storage",
    "nurse-station": "nurses-station",
    "cardiac-bay": "cardiology",
    "general-bay-1": "cardiology",
    "general-bay-2": "general-a",
    "general-bay-3": "general-b",
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
      const pos = reserveFloorPosition(placements, nurse.location || "nurses-station", "nurse");
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

    return `
      <svg class="floor-blueprint" viewBox="0 0 1000 620" aria-hidden="true">
        <path class="bp-footprint-shadow" d="M280 70 H760 V220 H940 V550 H60 V350 H280 Z" />
        <path class="bp-footprint" d="M280 70 H760 V220 H940 V550 H60 V350 H280 Z" />
        ${room("corridor", "corridor")}
        ${room("waiting", "soft")}
        ${room("nurses-station", "core")}
        ${room("storage", "support")}
        ${room("triage", "triage")}
        ${room("trauma", "alert")}
        ${room("cardiology", "bay")}
        ${room("general-a", "bay")}
        ${room("general-b", "bay")}

        ${wall(280, 70, 760, 70)}
        ${wall(280, 70, 280, 350)}
        ${wall(760, 70, 760, 220)}
        ${wall(760, 220, 940, 220)}
        ${wall(940, 220, 940, 290)}
        ${wall(940, 345, 940, 430)}
        ${wall(940, 490, 940, 550)}
        ${wall(940, 550, 210, 550)}
        ${wall(140, 550, 60, 550)}
        ${wall(60, 550, 60, 350)}
        ${wall(60, 350, 280, 350)}

        ${wall(440, 70, 440, 240)}
        ${wall(600, 70, 600, 240)}
        ${wall(280, 240, 340, 240)}
        ${wall(380, 240, 500, 240)}
        ${wall(540, 240, 660, 240)}
        ${wall(700, 240, 760, 240)}

        ${wall(280, 350, 280, 425)}
        ${wall(280, 465, 280, 550)}
        ${wall(440, 360, 500, 360)}
        ${wall(560, 360, 690, 360)}
        ${wall(725, 360, 760, 360)}
        ${wall(440, 360, 440, 490)}
        ${wall(440, 490, 640, 490)}
        ${wall(640, 360, 640, 490)}
        ${wall(640, 490, 760, 490)}
        ${wall(760, 220, 760, 285)}
        ${wall(760, 325, 760, 455)}
        ${wall(760, 495, 760, 550)}

        ${wall(760, 385, 940, 385)}

        ${door(340, 240, 380, 240, "M340 240 Q340 268 368 268")}
        ${door(500, 240, 540, 240, "M500 240 Q500 268 528 268")}
        ${door(660, 240, 700, 240, "M660 240 Q660 268 688 268")}
        ${door(500, 360, 560, 360, "M500 360 Q500 328 532 328")}
        ${door(690, 360, 725, 360, "M690 360 Q690 334 716 334")}
        ${door(760, 285, 760, 325, "M760 285 Q732 285 732 313")}
        ${door(760, 455, 760, 495, "M760 455 Q732 455 732 483")}
        ${door(280, 425, 280, 465, "M280 425 Q308 425 308 453")}
        ${door(140, 550, 210, 550)}
        ${door(940, 290, 940, 345)}
        ${door(940, 430, 940, 490)}

        ${bedFixture("bed1")}
        ${bedFixture("bed2")}
        ${bedFixture("bed3")}
        ${bedFixture("bed4")}
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
    BED_LAYOUT,
    FLOOR_LABELS,
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
