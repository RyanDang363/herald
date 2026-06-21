// Incident library — lists this session's replays (out/replay/*.json) as cards with the Pika clip,
// description, event type, start/end times, and those involved. Entries without a video_url still
// render with a link to the in-browser /replay/{incident} fallback.
// @spec REPLAY-LIB-004 (list with video) @spec REPLAY-LIB-005 (no-video entries degrade gracefully)
"use strict";

const $ = (id) => document.getElementById(id);

const TYPE_LABELS = {
  patient_intake: "Patient intake",
  low_oxygen_alert: "Low-oxygen alert",
  er_status_summary: "Status summary",
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

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

function mediaBlock(entry) {
  if (entry.video_url) {
    return `<video class="lib-video" src="${esc(entry.video_url)}" controls preload="metadata" playsinline></video>`;
  }
  // @spec REPLAY-LIB-005 — no Pika clip yet: degrade to a placeholder + the in-browser replay fallback.
  return `<div class="lib-novideo">
      <span>No Pika clip yet</span>
      <a class="lib-fallback" href="${esc(entry.replay_url)}">▶ Play in-browser replay</a>
    </div>`;
}

function card(entry) {
  const typeLabel = TYPE_LABELS[entry.incident_type] || entry.incident_type || "incident";
  return `<article class="lib-card">
    ${mediaBlock(entry)}
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

async function load() {
  const root = $("library");
  let incidents = [];
  try {
    const r = await fetch("/api/library");
    if (!r.ok) throw new Error(`status ${r.status}`);
    incidents = (await r.json()).incidents || [];
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
}

load();
