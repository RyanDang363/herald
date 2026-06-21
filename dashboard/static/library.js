// Incident library — lists this session's replays (out/replay/*.json) as cards with the Pika clip,
// description, event type, start/end times, and those involved. Entries without a video_url render
// with a link to the in-browser /replay/{incident} fallback, and — when DASHBOARD_ALLOW_PIKA is on —
// a one-click "Generate clip" action that drives the offline Pika render and polls it to completion.
// @spec REPLAY-LIB-004 (list with video) @spec REPLAY-LIB-005 (no-video entries degrade gracefully)
// @spec REPLAY-PIKA-003 (on-demand, gated generation from the dashboard)
"use strict";

const $ = (id) => document.getElementById(id);

const TYPE_LABELS = {
  patient_intake: "Patient intake",
  low_oxygen_alert: "Low-oxygen alert",
  er_status_summary: "Status summary",
};

let PIKA_ENABLED = false;

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function clockFromTs(ts) {
  if (ts == null) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function elapsedLabel(start, end) {
  if (start == null || end == null) return "—";
  const secs = Math.max(0, end - start);
  if (secs < 1) return "<1s";
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  return `${m}m ${Math.round(secs % 60)}s`;
}

function involvedChips(involved) {
  if (!involved || !involved.length) return '<span class="muted">—</span>';
  return involved.map((name) => `<span class="lib-chip">${esc(name)}</span>`).join("");
}

function videoHtml(url) {
  return `<video class="lib-video" src="${esc(url)}" controls preload="metadata" playsinline></video>`;
}

// The inner markup of a card's .lib-media region for an entry without a clip yet. When Pika is
// enabled, offer the one-click generate action; always offer the in-browser replay fallback.
function noVideoHtml(entry) {
  const generate = PIKA_ENABLED
    ? `<button class="gen-btn" data-incident="${esc(entry.incident_id)}">🎬 Generate clip</button>`
    : `<span>No Pika clip yet</span>`;
  return `<div class="lib-novideo">
      ${generate}
      <a class="lib-fallback" href="${esc(entry.replay_url)}">▶ Play in-browser replay</a>
    </div>`;
}

function renderingHtml() {
  return `<div class="lib-novideo gen-working">
      <span class="gen-spinner" aria-hidden="true"></span>
      <span class="gen-msg">Rendering with Pika… (~1–2 min)</span>
    </div>`;
}

function failedHtml(incidentId, replayUrl, message) {
  return `<div class="lib-novideo">
      <span class="gen-error">Render failed: ${esc(message || "unknown error")}</span>
      <button class="gen-btn" data-incident="${esc(incidentId)}">↻ Retry</button>
      <a class="lib-fallback" href="${esc(replayUrl)}">▶ Play in-browser replay</a>
    </div>`;
}

function mediaBlock(entry) {
  if (entry.video_url) return videoHtml(entry.video_url);
  return noVideoHtml(entry);
}

function card(entry) {
  const typeLabel = TYPE_LABELS[entry.incident_type] || entry.incident_type || "incident";
  return `<article class="lib-card">
    <div class="lib-media" data-incident="${esc(entry.incident_id)}" data-replay="${esc(entry.replay_url)}">${mediaBlock(entry)}</div>
    <div class="lib-body">
      <div class="lib-card-top">
        <h3 class="lib-title">${esc(entry.title || entry.incident_id)}</h3>
        <span class="lib-badge lib-badge-${esc(entry.incident_type || "other")}">${esc(typeLabel)}</span>
      </div>
      <p class="lib-summary">${esc(entry.summary || "")}</p>
      <div class="lib-meta">
        <span><strong>Start</strong> ${esc(clockFromTs(entry.start_ts))}</span>
        <span><strong>End</strong> ${esc(clockFromTs(entry.end_ts))}</span>
        <span><strong>Elapsed</strong> ${esc(elapsedLabel(entry.start_ts, entry.end_ts))}</span>
        <span><strong>Milestones</strong> ${esc(entry.snapshot_count ?? 0)}</span>
      </div>
      <div class="lib-involved"><strong>Involved:</strong> ${involvedChips(entry.involved)}</div>
      <div class="lib-actions">
        <a class="lib-link" href="${esc(entry.replay_url)}">Open replay →</a>
      </div>
    </div>
  </article>`;
}

// The .lib-media region for one incident (ids match ^[A-Za-z0-9_-]+$, safe to interpolate).
function mediaEl(incidentId) {
  return document.querySelector(`.lib-media[data-incident="${incidentId}"]`);
}

async function pollUntilDone(incidentId) {
  const el = mediaEl(incidentId);
  const replayUrl = el ? el.getAttribute("data-replay") : "";
  for (let i = 0; i < 240; i++) {  // ~12 min ceiling at 3s/poll
    await sleep(3000);
    let job;
    try {
      const r = await fetch(`/api/replay/${incidentId}/status`);
      if (!r.ok) throw new Error(`status ${r.status}`);
      job = await r.json();
    } catch (e) {
      // transient read error — keep polling rather than giving up
      continue;
    }
    if (job.status === "completed" && job.video_url) {
      const m = mediaEl(incidentId);
      if (m) m.innerHTML = videoHtml(job.video_url);
      return;
    }
    if (job.status === "failed") {
      const m = mediaEl(incidentId);
      if (m) m.innerHTML = failedHtml(incidentId, replayUrl, job.error);
      return;
    }
  }
  const m = mediaEl(incidentId);
  if (m) m.innerHTML = failedHtml(incidentId, replayUrl, "timed out waiting for the render");
}

async function generate(incidentId) {
  const el = mediaEl(incidentId);
  const replayUrl = el ? el.getAttribute("data-replay") : "";
  if (el) el.innerHTML = renderingHtml();
  try {
    const r = await fetch(`/api/replay/${incidentId}/generate`, { method: "POST" });
    if (!r.ok) {
      let detail = `request failed (${r.status})`;
      try { detail = (await r.json()).detail || detail; } catch (e) { /* ignore */ }
      const m = mediaEl(incidentId);
      if (m) m.innerHTML = failedHtml(incidentId, replayUrl, detail);
      return;
    }
  } catch (e) {
    const m = mediaEl(incidentId);
    if (m) m.innerHTML = failedHtml(incidentId, replayUrl, "could not reach the server");
    return;
  }
  pollUntilDone(incidentId);
}

function onClick(event) {
  const btn = event.target.closest(".gen-btn");
  if (!btn) return;
  event.preventDefault();
  const incidentId = btn.getAttribute("data-incident");
  if (incidentId) generate(incidentId);
}

async function load() {
  const root = $("library");
  let incidents = [];
  try {
    const r = await fetch("/api/library");
    if (!r.ok) throw new Error(`status ${r.status}`);
    const body = await r.json();
    incidents = body.incidents || [];
    PIKA_ENABLED = body.pika_enabled === true;
  } catch (e) {
    root.innerHTML = `<p class="empty">Could not load the incident library.</p>`;
    return;
  }
  $("lib-count").textContent = `${incidents.length} incident${incidents.length === 1 ? "" : "s"}`;
  if (!incidents.length) {
    root.innerHTML = `<p class="empty">No incidents yet this session. Run an ER event, then it appears here.</p>`;
    return;
  }
  root.innerHTML = incidents.map(card).join("");
  root.addEventListener("click", onClick);
}

load();
