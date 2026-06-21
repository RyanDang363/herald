// Incident replay playback — reuses the dashboard floor map (window.Floor) and plays a captured
// snapshot timeline back, tweening tokens between snapshots paced by real `ts` deltas.
// @spec REPLAY-FRAME-001 (shared floor layout) @spec REPLAY-FRAME-002 (ts-paced tween)
//
// Data: GET /api/replay/{incident} -> { snapshots: [{seq, ts, action, actor, target, entities}], ... }.
// No store/Redis dependency — the endpoint reads the out/replay/{incident}.json file directly.
"use strict";

const $ = (id) => document.getElementById(id);

// Below this real span (seconds) a timeline is treated as instantaneous (synchronous intake): we
// spread snapshots evenly so the milestones are still watchable instead of collapsing to one frame.
const MIN_REAL_SPAN = 0.5;
const SYNTH_STEP = 1.0; // seconds per milestone when synthesizing a span
const MIN_PLAY_SECONDS = 4;
const MAX_PLAY_SECONDS = 14;

const incidentId = decodeURIComponent(location.pathname.replace(/^\/replay\//, "").replace(/\/$/, ""));

let snapshots = [];
let rel = []; // per-snapshot virtual time (seconds from start), real or synthesized
let span = 0; // total virtual seconds
let placements = []; // per-snapshot Map(key -> {x,y,kind,label,cls,title})
let shell = null; // the .floor-shell element tokens are appended into
const tokenEls = new Map(); // key -> button element (reused across frames for smooth motion)

let playing = false;
let vt = 0; // current virtual time
let rafId = null;
let lastFrameMs = null;

function fmtClock(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `00:${String(s).padStart(2, "0")}`;
}

function buildTimeline(snaps) {
  const t0 = snaps[0].ts ?? 0;
  let r = snaps.map((s) => (s.ts ?? t0) - t0);
  let total = r[r.length - 1] || 0;
  if (total < MIN_REAL_SPAN) {
    // Synchronous incident: spread the milestones evenly so motion/captions are visible.
    r = snaps.map((_, i) => i * SYNTH_STEP);
    total = r[r.length - 1] || 0;
  }
  return { rel: r, span: total };
}

// How many wall-clock seconds the full replay should take (clamped so it's watchable).
function playSeconds() {
  return Math.min(MAX_PLAY_SECONDS, Math.max(MIN_PLAY_SECONDS, span || MIN_PLAY_SECONDS));
}

// Index of the snapshot active at virtual time `t` (latest snapshot whose rel <= t).
function indexAt(t) {
  let i = 0;
  for (let k = 0; k < rel.length; k++) {
    if (rel[k] <= t + 1e-9) i = k;
    else break;
  }
  return i;
}

function lerp(a, b, p) {
  return a + (b - a) * p;
}

// Interpolated marker specs at virtual time `t`: tween x/y between bracketing snapshots; carry the
// label/class/title from the snapshot the token is moving toward (or its only appearance).
function specsAt(t) {
  const i = indexAt(t);
  const j = Math.min(i + 1, placements.length - 1);
  const a = placements[i];
  const b = placements[j];
  const dt = rel[j] - rel[i];
  const p = dt > 0 ? Math.min(1, Math.max(0, (t - rel[i]) / dt)) : 0;

  const out = new Map();
  const keys = new Set([...a.keys(), ...b.keys()]);
  for (const key of keys) {
    const sa = a.get(key);
    const sb = b.get(key);
    if (sa && sb) {
      out.set(key, { ...sb, x: lerp(sa.x, sb.x, p), y: lerp(sa.y, sb.y, p) });
    } else if (sb && p > 0) {
      out.set(key, sb); // appears during the transition into the next snapshot (not at p === 0)
    } else if (sa && p < 1) {
      out.set(key, sa); // about to leave — held until the transition completes
    }
  }
  return out;
}

// Whether any token ever appears/disappears or changes position across the timeline. A deduplicated
// intake or a status snapshot has identical placements throughout — there is nothing to animate.
function hasMotion(frames) {
  if (frames.length < 2) return false;
  const first = frames[0];
  for (let i = 1; i < frames.length; i++) {
    const m = frames[i];
    if (m.size !== first.size) return true; // a token entered/left the floor
    for (const [key, spec] of m) {
      const a = first.get(key);
      if (!a || Math.abs(a.x - spec.x) > 0.5 || Math.abs(a.y - spec.y) > 0.5) return true;
    }
  }
  return false;
}

function ensureToken(key, spec) {
  let node = tokenEls.get(key);
  if (!node) {
    node = document.createElement("div");
    node.className = "floor-token";
    node.dataset.key = key;
    node.innerHTML = '<span class="token-core"></span><span class="token-label"></span>';
    shell.appendChild(node);
    tokenEls.set(key, node);
  }
  return node;
}

function paint(specMap) {
  for (const [key, node] of tokenEls) {
    if (!specMap.has(key)) {
      node.remove();
      tokenEls.delete(key);
    }
  }
  for (const [key, spec] of specMap) {
    const node = ensureToken(key, spec);
    node.className = `floor-token ${spec.kind} ${spec.cls || ""}`.trim();
    node.style.left = Floor.floorPercent(spec.x, "x");
    node.style.top = Floor.floorPercent(spec.y, "y");
    node.title = spec.title || `${spec.kind} ${spec.id}`;
    node.querySelector(".token-core").textContent = spec.label;
    node.querySelector(".token-label").textContent = spec.id;
  }
}

function caption(t) {
  const snap = snapshots[indexAt(t)];
  if (!snap) return "";
  const bits = [snap.actor, snap.action].filter(Boolean).join(" · ");
  return snap.target ? `${bits} → ${snap.target}` : bits;
}

function renderAt(t) {
  vt = Math.min(span, Math.max(0, t));
  paint(specsAt(vt));
  $("replay-caption").textContent = caption(vt) || "—";
  $("replay-clock").textContent = fmtClock(vt);
  const scrub = $("replay-scrub");
  if (document.activeElement !== scrub) {
    scrub.value = String(span > 0 ? Math.round((vt / span) * 1000) : 0);
  }
}

function frame(nowMs) {
  if (!playing) return;
  if (lastFrameMs == null) lastFrameMs = nowMs;
  const dtMs = nowMs - lastFrameMs;
  lastFrameMs = nowMs;
  const rate = span / playSeconds(); // virtual seconds per real second
  renderAt(vt + (dtMs / 1000) * rate);
  if (vt >= span) {
    pause();
    return;
  }
  rafId = requestAnimationFrame(frame);
}

function play() {
  if (playing || !snapshots.length) return;
  if (vt >= span) vt = 0; // replay from the start if at the end
  playing = true;
  lastFrameMs = null;
  $("replay-play").textContent = "❚❚ Pause";
  rafId = requestAnimationFrame(frame);
}

function pause() {
  playing = false;
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;
  $("replay-play").textContent = vt >= span ? "↻ Replay" : "▶ Play";
}

function mountFloor() {
  const map = $("floor-map");
  map.innerHTML = `<div class="floor-shell">${Floor.renderBlueprint()}
    <div class="floor-legend">
      <span><i class="legend-dot patient"></i>Patients</span>
      <span><i class="legend-dot nurse"></i>Nurses</span>
      <span><i class="legend-dot doctor"></i>Doctors</span>
      <span><i class="legend-dot equipment"></i>Devices</span>
    </div></div>`;
  shell = map.querySelector(".floor-shell");
}

// Seek API used by the headless frame capturer (scripts/capture_replay_frames.py) and manual seeking.
function exposeApi() {
  window.replayApi = {
    ready: true,
    incidentId,
    snapshotCount: () => snapshots.length,
    keyframeSeqs: () => snapshots.map((s) => s.seq),
    seekToSeq(seq) {
      const idx = snapshots.findIndex((s) => s.seq === seq);
      if (idx >= 0) {
        pause();
        renderAt(rel[idx]);
      }
      return idx >= 0;
    },
    seekToIndex(idx) {
      if (idx >= 0 && idx < snapshots.length) {
        pause();
        renderAt(rel[idx]);
        return true;
      }
      return false;
    },
    seekToFraction(f) {
      pause();
      renderAt((Number(f) || 0) * span);
    },
  };
}

async function init() {
  $("replay-id").textContent = incidentId;
  let data;
  try {
    const r = await fetch(`/api/replay/${encodeURIComponent(incidentId)}`);
    if (!r.ok) throw new Error(`status ${r.status}`);
    data = await r.json();
  } catch (e) {
    $("banner").classList.remove("hidden");
    $("replay-caption").textContent = "Replay data not found for this incident.";
    window.replayApi = { ready: true, error: true, snapshotCount: () => 0 };
    return;
  }

  snapshots = (data.snapshots || []).slice().sort((a, b) => a.seq - b.seq);
  $("replay-title").textContent = data.title || incidentId;
  $("replay-sub").textContent = data.summary || "";
  document.title = `Replay — ${data.title || incidentId}`;

  mountFloor();
  if (!snapshots.length) {
    $("replay-caption").textContent = "No snapshots captured for this incident.";
    exposeApi();
    return;
  }

  ({ rel, span } = buildTimeline(snapshots));
  placements = snapshots.map((s) => {
    const specs = Floor.placeEntities(s.entities || {});
    return new Map(specs.map((spec) => [`${spec.kind}:${spec.id}`, spec]));
  });

  $("replay-play").onclick = () => (playing ? pause() : play());
  $("replay-scrub").oninput = (e) => {
    pause();
    renderAt((Number(e.target.value) / 1000) * span);
  };

  renderAt(0);
  exposeApi();

  // Some incidents have nothing to animate: a single point-in-time snapshot (status summary), or
  // multiple snapshots with identical state (a deduplicated/no-op intake). Render the captured state
  // but disable the transport and say why — otherwise Play/scrub silently no-op and it looks broken.
  // @spec REPLAY-FRAME-002
  if (snapshots.length < 2 || span === 0 || !hasMotion(placements)) {
    const single = snapshots.length < 2;
    const playBtn = $("replay-play");
    playBtn.disabled = true;
    playBtn.textContent = single ? "Single snapshot" : "No motion";
    $("replay-scrub").disabled = true;
    const why = single
      ? "point-in-time snapshot (status view)"
      : "no ER state changes (e.g. a duplicate/deduplicated intake)";
    const base = caption(0);
    $("replay-caption").textContent = base
      ? `${base} — ${why}; nothing to play back`
      : `Nothing to play back — ${why}.`;
  }
}

init();
