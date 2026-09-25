"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const fmt = (s) => Math.floor(s / 60) + ":" + String(Math.round(s) % 60).padStart(2, "0");
const pct = (v) => (v == null ? "–" : Math.round(v * 100) + "%");

const VERDICTS = {
  approve: { label: "Approve", sub: "Safe to merge", cls: "ok" },
  nits: { label: "Approve with nits", sub: "Merge, fix small things", cls: "ok" },
  changes: { label: "Request changes", sub: "Blocks the merge", cls: "no" },
  ask: { label: "Can't judge yet", sub: "Need context or tests", cls: "ask" },
};
const CONF = { 1: "Low", 2: "Medium", 3: "High" };
const CATS = ["correctness", "security", "performance", "design", "spec"];
const CALIBRATION = {
  "sure-right": ["good", "Sure and right."],
  overconfident: ["bad", "Overconfident: sure and wrong. The costliest kind of miss."],
  "unsure-right": ["warn", "Right but unsure. Trust this pattern next time."],
  "unsure-wrong": ["warn", "Unsure and wrong. \"Can't judge yet\" would have been the honest call."],
  "medium-right": ["good", "Right at medium confidence."],
  "medium-wrong": ["bad", "Wrong at medium confidence."],
};
const LANG_NAME = { python: "Python", sql: "SQL", typescript: "TypeScript", javascript: "JavaScript" };
const FORMAT_NAME = { function: "Single function", diff: "Diff", multi: "Multi-file" };

const state = {
  problems: [],
  current: null,
  problem: null,
  file: null,
  view: "review",
  draft: null,
  attempt: null,
  composer: null,
  tab: "practice",
  badgeMode: storageGet("rd-badge") || "after",
};

function storageGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function storageSet(key, value) {
  try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* storage blocked */ }
}
const loadDraft = (id) => { try { return JSON.parse(storageGet("rd-draft-" + id)); } catch (e) { return null; } };
const saveDraft = () => state.current && state.draft && storageSet("rd-draft-" + state.current, JSON.stringify(state.draft));
const clearDraft = (id) => storageSet("rd-draft-" + id, null);
const newDraft = () => ({ elapsed: 0, verdict: null, conf: null, comments: [], next: 1 });

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* not json */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

// Syntax highlighting: small tokenizer, enough for review drills.
const KW = {
  python: "def|return|for|in|if|else|elif|None|True|False|and|or|not|import|from|class|try|except|finally|raise|with|as|await|async|lambda|is|while|yield",
  typescript: "export|async|function|await|const|let|var|return|if|else|try|catch|finally|throw|new|null|undefined|true|false|import|from|type|interface|for|of|while|class",
  sql: "SELECT|FROM|WHERE|UPDATE|SET|ALTER|TABLE|ADD|COLUMN|CREATE|INDEX|ON|INSERT|INTO|VALUES|JOIN|LEFT|RIGHT|INNER|AND|OR|NOT|NULL|IS|AS|GROUP|ORDER|BY|HAVING|LIMIT|OFFSET|VARCHAR|CONCURRENTLY|DELETE|DROP|BEGIN|COMMIT|interval|now",
};
KW.javascript = KW.typescript;
const COM = { python: "#.*$", typescript: "//.*$", javascript: "//.*$", sql: "--.*$" };
const STR = String.raw`"""[\s\S]*?"""|f?"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|` + "`(?:[^`\\\\]|\\\\.)*`";
const HL_CACHE = {};

function hl(src, lang) {
  const re = HL_CACHE[lang] || (HL_CACHE[lang] = new RegExp("(" + COM[lang] + ")|(" + STR + ")|\\b(" + KW[lang] + ")\\b|\\b(\\d+)\\b|\\b([A-Za-z_]\\w*)(?=\\()", lang === "sql" ? "gi" : "g"));
  re.lastIndex = 0;
  let out = "", last = 0;
  src.replace(re, (m, c, s, k, n, f, idx) => {
    out += esc(src.slice(last, idx));
    out += '<span class="t-' + (c ? "com" : s ? "str" : k ? "kw" : n ? "num" : "fn") + '">' + esc(m) + "</span>";
    last = idx + m.length;
    return m;
  });
  return out + esc(src.slice(last));
}

// ---------- data loading ----------

async function refreshProblems() {
  state.problems = await api("/api/problems");
  renderQueue();
}

async function openProblem(id, opts = {}) {
  saveDraft();
  state.composer = null;
  state.current = id;
  state.problem = await api("/api/problems/" + encodeURIComponent(id));
  state.file = state.problem.files[0].path;
  const summary = state.problems.find((p) => p.id === id);
  const saved = loadDraft(id);
  state.attempt = null;
  state.draft = null;
  if (opts.attemptId) {
    state.attempt = await api("/api/attempts/" + encodeURIComponent(opts.attemptId));
  } else if (opts.retry || saved) {
    state.draft = opts.retry ? newDraft() : saved;
  } else if (summary && summary.latest) {
    state.attempt = await api("/api/attempts/" + encodeURIComponent(summary.latest.attempt_id));
  } else {
    state.draft = newDraft();
  }
  state.view = state.attempt ? "attempt" : "review";
  if (opts.retry) saveDraft();
  render();
}

async function reloadAttempt() {
  if (state.view !== "attempt" || !state.attempt) return;
  state.attempt = await api("/api/attempts/" + encodeURIComponent(state.attempt.attempt_id));
  renderWork();
  renderPanel();
}

// ---------- rendering ----------

function render() {
  renderQueue();
  renderWork();
  renderPanel();
}

function queueItem(p) {
  const draft = loadDraft(p.id);
  let status = "";
  if (p.id === state.current && state.view === "review" && state.draft) status = '<span class="q-status wip">draft ' + fmt(state.draft.elapsed) + "</span>";
  else if (draft) status = '<span class="q-status wip">draft ' + fmt(draft.elapsed) + "</span>";
  else if (p.latest && p.latest.graded) status = '<span class="q-status">' + p.latest.score + "</span>";
  else if (p.latest) status = '<span class="q-status wip">grading</span>';
  const files = p.format === "multi" ? " · " + p.files + " files" : "";
  return '<button class="q-item' + (p.id === state.current ? " active" : "") + '" data-open="' + esc(p.id) + '">' +
    '<span class="q-name">' + esc(p.title) + "</span>" +
    '<span class="q-meta">' + LANG_NAME[p.language] + " · " + FORMAT_NAME[p.format].toLowerCase() + files +
    ' <span class="diff ' + p.difficulty + '">' + p.difficulty + "</span>" + status + "</span></button>";
}

function renderQueue() {
  const todo = state.problems.filter((p) => !p.latest || loadDraft(p.id) || (p.id === state.current && state.view === "review"));
  const done = state.problems.filter((p) => !todo.includes(p));
  let html = '<div class="queue-head"><span class="label">To review</span><span class="hint">' + todo.length + "</span></div>";
  html += todo.length ? todo.map(queueItem).join("") : '<p class="empty">All reviewed.</p>';
  if (done.length) html += '<div class="queue-head"><span class="label">Reviewed</span><span class="hint">' + done.length + "</span></div>" + done.map(queueItem).join("");
  html += '<div class="gen-hint">Need more? In Claude Code run <code>/generate sql hard 3</code> or <code>/import-real 2</code>. New problems appear here on their own.</div>';
  $("queue").innerHTML = html;
}

function sourceBadge(problem, revealed) {
  const s = problem.source;
  if (state.badgeMode === "after" && !revealed) return '<span class="badge hidden">Source shown after submit</span>';
  if (s.kind === "real") {
    const text = "Real · " + esc(s.repo) + (s.sha ? "@" + esc(s.sha) : "") + (s.dataset ? " · " + esc(s.dataset) : "");
    return '<a class="badge real" href="' + esc(s.ref) + '" target="_blank" rel="noopener">' + text + " ↗</a>";
  }
  return '<span class="badge gen">Generated · ' + esc(s.date) + "</span>";
}

function comments() {
  return state.view === "attempt" ? state.attempt.submission.comments : state.draft.comments;
}

function renderWork() {
  const p = state.problem;
  if (!p) {
    $("work").innerHTML = '<p class="placeholder">' + (state.problems.length ? "Pick a problem from the queue." : "No problems yet. Run /generate in Claude Code.") + "</p>";
    return;
  }
  const attempt = state.view === "attempt" ? state.attempt : null;
  const all = comments();
  const tabs = p.files.map((f) => {
    const n = all.filter((c) => c.file === f.path).length;
    return '<button role="tab" data-file="' + esc(f.path) + '" aria-selected="' + (f.path === state.file) + '">' + esc(f.path) + (n ? '<span class="count">' + n + "</span>" : "") + "</button>";
  }).join("");
  $("work").innerHTML =
    '<div class="prob-head"><div class="prob-meta"><span>' + LANG_NAME[p.language] + '</span><span class="sep"></span><span>' + FORMAT_NAME[p.format] +
    '</span><span class="sep"></span><span class="diff ' + p.difficulty + '">' + p.difficulty + '</span><span class="sep"></span>' + sourceBadge(p, !!attempt) + "</div>" +
    "<h1>" + esc(p.title) + "</h1>" +
    '<div class="spec"><div class="spec-top"><span class="label">Spec</span><span class="spec-id">' + esc(p.spec.id) + "</span></div><p>" + esc(p.spec.text) + "</p></div>" +
    (p.context ? '<p class="context">' + esc(p.context) + "</p>" : "") + "</div>" +
    '<div class="code"><div class="code-bar"><div class="file-tabs" role="tablist">' + tabs + "</div><span>" +
    (attempt ? "Review submitted" : "Click a line number to comment") + '</span></div><div class="code-scroll"><div class="rows">' + renderRows(p, attempt) + "</div></div></div>";
  const ta = $("c-text");
  if (ta) ta.focus();
}

function renderRows(p, attempt) {
  const file = p.files.find((f) => f.path === state.file);
  const all = comments();
  const onFile = all.map((c, i) => ({ c, i })).filter(({ c }) => c.file === file.path);
  const byLine = {};
  onFile.forEach(({ c, i }) => (byLine[c.line] ||= []).push(i));
  const result = attempt && attempt.result;
  const issues = attempt ? attempt.key.issues.filter((k) => k.file === file.path) : [];
  const fbNotes = {};
  if (attempt && attempt.feedback) attempt.feedback.comments.forEach((c) => (fbNotes[c.comment_id] = c));
  let html = "";
  file.rows.forEach((row, idx) => {
    const n = idx + 1;
    let cls = byLine[n] ? "flagged" : "";
    if (result) {
      const covering = issues.filter((k) => n >= k.start && n <= k.end);
      const missed = covering.some((k) => result.missed.includes(k.id));
      const found = covering.some((k) => result.found.includes(k.id));
      const falseAlarm = (byLine[n] || []).some((i) => !result.matches[all[i].id]);
      const hitHere = (byLine[n] || []).some((i) => result.matches[all[i].id]);
      cls = missed ? "r-miss" : found || hitHere ? "r-hit" : falseAlarm ? "r-fa" : "";
    }
    if (row.kind === "+") cls += " add";
    if (row.kind === "-") cls += " del";
    const sign = file.is_diff ? '<span class="sign">' + (row.kind === " " ? "" : row.kind) + "</span>" : "";
    html += '<div class="row ' + cls + '"><button class="ln" data-line="' + n + '" aria-label="Comment on line ' + n + '"' + (attempt ? " disabled" : "") + ">" + n +
      '</button><span class="mark"></span><pre class="src">' + sign + (hl(row.text, p.language) || " ") + "</pre></div>";
    (byLine[n] || []).forEach((i) => { html += renderThread(all[i], i, attempt, fbNotes); });
    if (!attempt && state.composer && state.composer.file === file.path && state.composer.line === n) html += renderComposer(n);
    issues.filter((k) => k.end === n && result.missed.includes(k.id)).forEach((k) => {
      html += '<div class="keynote"><div class="thread-top"><span class="cat">' + k.category + '</span><span class="verdict-tag">Missed · ' + esc(k.title) +
        " (" + k.severity + ')</span></div><div>' + esc(k.explanation) + "</div>" + (k.fix ? '<div class="claude-note"><b>Fix:</b> ' + esc(k.fix) + "</div>" : "") + "</div>";
    });
  });
  return html;
}

function renderThread(c, i, attempt, fbNotes) {
  let tag = "", note = "", gcls = "";
  if (attempt) {
    const keyId = attempt.result.matches[c.id];
    const k = keyId && attempt.key.issues.find((x) => x.id === keyId);
    const fb = fbNotes[c.id];
    gcls = k ? " g-hit" : " g-fa";
    tag = '<span class="verdict-tag">' + (k ? "Hit · " + esc(k.title) : "False alarm") + "</span>";
    if (fb) note = "<b>" + (k ? fb.quality + "/2. " : "") + "</b>" + esc(fb.note);
    else note = k ? "<b>Key:</b> " + esc(k.explanation) + (k.fix ? " <b>Fix:</b> " + esc(k.fix) : "") : "Not in the answer key. Claude's note arrives with /grade.";
  }
  return '<div class="thread' + gcls + '"><div class="thread-top"><span class="cat">' + esc(c.category) + "</span>" + tag +
    (attempt ? "" : '<button class="del-btn" data-del="' + i + '">Delete</button>') + "</div><div>" + esc(c.text) + "</div>" +
    (note ? '<div class="claude-note">' + note + "</div>" : "") + "</div>";
}

function renderComposer(n) {
  return '<div class="composer"><div class="composer-row"><span class="label">Line ' + n + '</span><select id="c-cat" aria-label="Issue type">' +
    CATS.map((c) => "<option>" + c + "</option>").join("") + "</select></div>" +
    '<textarea id="c-text" placeholder="What is wrong and what should change?"></textarea>' +
    '<div class="composer-row"><button class="btn primary small" id="c-save">Add comment</button><button class="btn small" id="c-cancel">Cancel</button><span class="kbd">Ctrl + Enter to add · Esc to cancel</span></div></div>';
}

function bar(label, value, frac) {
  const w = frac == null ? 0 : Math.round(Math.max(0, Math.min(1, frac)) * 100);
  return '<div class="bar-row"><span>' + label + '</span><span class="v">' + value + '</span><div class="track"><div class="fill" style="width:' + w + '%"></div></div></div>';
}

function renderPanel() {
  const el = $("panel");
  const p = state.problem;
  $("timer").classList.toggle("stopped", state.view !== "review");
  if (!p) { el.innerHTML = '<p class="empty">No problem open.</p>'; $("clock").textContent = "0:00"; $("target").textContent = ""; return; }
  $("target").textContent = "/ " + fmt(p.target_seconds) + " target";
  if (state.view === "review") renderReviewPanel(el);
  else renderAttemptPanel(el);
}

function renderReviewPanel(el) {
  const d = state.draft;
  $("clock").textContent = fmt(d.elapsed);
  const list = d.comments.length
    ? d.comments.map((c) => '<button class="c-item" data-jump="' + esc(c.file) + "|" + c.line + '"><span class="c-line">' + (state.problem.files.length > 1 ? esc(c.file.split("/").pop()) + ":" : "L") + c.line +
      '</span><span class="c-text">' + esc(c.text) + "</span></button>").join("")
    : '<p class="empty">No comments yet. Click a line number to flag it.</p>';
  const ready = d.verdict && d.conf;
  el.innerHTML = "<h2>Your review</h2>" +
    '<div class="c-list"><span class="label">' + d.comments.length + " comment" + (d.comments.length === 1 ? "" : "s") + "</span>" + list + "</div>" +
    '<div class="c-list"><span class="label">Verdict</span><div class="seg">' +
    Object.entries(VERDICTS).map(([k, v]) => '<button class="' + v.cls + '" data-verdict="' + k + '" aria-pressed="' + (d.verdict === k) + '">' + v.label + "<small>" + v.sub + "</small></button>").join("") + "</div></div>" +
    '<div class="c-list"><span class="label">How sure are you?</span><div class="seg three">' +
    Object.entries(CONF).map(([k, v]) => '<button data-conf="' + k + '" aria-pressed="' + (String(d.conf) === k) + '">' + v + "</button>").join("") + "</div></div>" +
    '<div class="foot"><button class="btn primary" id="submit"' + (ready ? "" : " disabled") + ">Submit review</button>" +
    '<p class="hint" id="submit-hint">' + (ready ? "Submitting stops the timer. Discussion afterward is not timed." : "Pick a verdict and a confidence to submit.") + "</p></div>";
}

function renderAttemptPanel(el) {
  const a = state.attempt, r = a.result, sub = a.submission, fb = a.feedback;
  $("clock").textContent = fmt(sub.elapsed_seconds);
  const hitsN = Object.values(r.matches).filter(Boolean).length;
  const [calCls, calText] = CALIBRATION[r.calibration];
  const verdictCls = r.verdict_credit === 1 ? "good" : r.verdict_credit > 0 ? "warn" : "bad";
  const issueRows = a.key.issues.map((k) => {
    const found = r.found.includes(k.id);
    return '<div class="issue"><span class="sw" style="background:var(' + (found ? "--hit" : "--miss") + ')"></span><span>' + esc(k.title) +
      ' <span class="ln-ref">' + esc(k.file.split("/").pop()) + ":" + k.start + (k.end !== k.start ? "-" + k.end : "") + "</span></span><span class=\"ln-ref\">" + (found ? "found" : "missed") + "</span></div>";
  }).join("") + sub.comments.filter((c) => !r.matches[c.id]).map((c) =>
    '<div class="issue"><span class="sw" style="background:var(--fa)"></span><span>Your flag <span class="ln-ref">' + esc(c.file.split("/").pop()) + ":" + c.line + '</span></span><span class="ln-ref">false alarm</span></div>').join("");

  let grading;
  if (fb) {
    grading = '<div class="summary"><span class="label">From Claude</span><p>' + esc(fb.summary) + "</p></div>" +
      (fb.key_revised ? '<p class="hint warn">The answer key was revised after a dispute.</p>' : "") +
      (fb.recap ? '<div class="summary"><span class="label">Discussion recap</span><p>' + esc(fb.recap) + "</p></div>"
        : '<p class="hint">Keep discussing in your Claude Code terminal, or run <code>/dispute</code> if the key looks wrong. Run <code>/recap</code> to save a summary here.</p>');
  } else {
    grading = '<p class="hint">Saved as <code>' + esc(a.attempt_id) + '</code>. Run this in Claude Code for comment grades and a summary:</p>' +
      '<div class="cmd"><span>/grade</span><button class="btn small" id="copy">Copy</button></div>' +
      '<div class="listen"><span class="pulse"></span>Waiting for feedback. This page updates on its own.</div>' +
      (a.feedback_error ? '<div class="error">The feedback file is not valid yet:\n' + esc(a.feedback_error) + "</div>" : "");
  }

  el.innerHTML = "<h2>" + (fb ? "Graded" : "Submitted") + "</h2>" +
    '<div class="score"><b>' + (r.score ?? "–") + "</b><span>" + (r.score == null ? "final score after /grade" : "/ 100") + "</span></div>" +
    '<div class="bars">' +
    bar("Issues found (severity-weighted)", r.found_weight + " / " + r.total_weight, r.recall) +
    bar("Flags that were real", hitsN + " / " + sub.comments.length, r.precision) +
    bar("Comment quality", r.quality == null ? "pending" : pct(r.quality), r.quality) +
    bar("Speed vs " + fmt(a.problem.target_seconds) + " target", fmt(sub.elapsed_seconds), r.speed) +
    "</div>" +
    '<dl class="kv"><dt>Your verdict</dt><dd class="' + verdictCls + '">' + VERDICTS[sub.verdict].label + (r.bad_approval ? ". Score capped at 30." : "") + "</dd>" +
    "<dt>Expected</dt><dd>" + VERDICTS[a.key.verdict].label + "</dd>" +
    '<dt>Confidence</dt><dd class="' + calCls + '">' + CONF[sub.confidence] + ". " + calText + "</dd>" +
    "<dt>Source</dt><dd>" + sourceBadge(a.problem, true) + "</dd></dl>" +
    '<div class="issues"><span class="label">Answer key</span>' + (issueRows || '<p class="empty">Clean code. Nothing to flag.</p>') + "</div>" +
    grading +
    '<div class="foot"><button class="btn primary" id="next">Next problem</button><button class="btn" id="retry">Review this again</button></div>';
}

// ---------- history and stats ----------

async function renderHistory() {
  const rows = await api("/api/history");
  const body = rows.map((r) => {
    const vcls = r.verdict_credit === 1 ? "good" : r.verdict_credit > 0 ? "warn" : "bad";
    return '<tr data-attempt="' + esc(r.attempt_id) + '" data-problem="' + esc(r.problem_id) + '"><td>' + esc(r.submitted_at.replace("T", " ").slice(0, 16)) + "</td><td>" + esc(r.title) +
      "</td><td>" + (r.source === "real" ? "Real" : "Generated") + "</td><td>" + LANG_NAME[r.language] + '</td><td><span class="diff ' + r.difficulty + '">' + r.difficulty +
      '</span></td><td class="' + vcls + '">' + VERDICTS[r.verdict].label + "</td><td>" + CONF[r.confidence] + '</td><td class="num">' + r.found + " / " + r.issues +
      '</td><td class="num">' + r.false_alarms + '</td><td class="num">' + fmt(r.elapsed_seconds) + '</td><td class="num">' + (r.graded ? r.score : "grading") + "</td></tr>";
  }).join("");
  $("tab-history").innerHTML = "<h2>History</h2>" + (rows.length
    ? '<div class="tbl-wrap"><table><thead><tr><th>When</th><th>Problem</th><th>Source</th><th>Lang</th><th>Level</th><th>Verdict</th><th>Confidence</th><th>Found</th><th>False alarms</th><th>Time</th><th>Score</th></tr></thead><tbody>' + body + "</tbody></table></div>" +
      '<p class="hint">"0 / 0" is a clean problem. Click a row to open that attempt.</p>'
    : '<p class="empty">No attempts yet.</p>');
}

function hbars(obj, fmtValue, order) {
  const keys = order ? order.filter((k) => k in obj) : Object.keys(obj).sort((a, b) => (obj[b] ?? 0) - (obj[a] ?? 0));
  if (!keys.length) return '<p class="empty">No data yet.</p>';
  return keys.map((k) => {
    const v = obj[k];
    return '<div class="hbar"><span>' + esc(k) + '</span><div class="track"><div class="fill" style="width:' + Math.round(Math.min(1, v ?? 0) * 100) + '%"></div></div><span class="v">' + fmtValue(v) + "</span></div>";
  }).join("");
}

function trendSvg(points) {
  if (points.length < 2) return '<p class="empty">Grade at least two reviews to see a trend.</p>';
  const s = points.map((p) => p.score);
  const x = (i) => 30 + i * (280 / (s.length - 1));
  const y = (v) => 100 - v * 0.9;
  const pts = s.map((v, i) => x(i).toFixed(1) + "," + y(v).toFixed(1));
  const last = s[s.length - 1];
  return '<svg viewBox="0 0 320 120" width="100%" role="img" aria-label="Score trend, latest ' + last + '">' +
    '<g stroke="var(--line)" stroke-width="1"><line x1="30" x2="310" y1="10" y2="10"/><line x1="30" x2="310" y1="55" y2="55"/><line x1="30" x2="310" y1="100" y2="100"/></g>' +
    '<text x="24" y="13" text-anchor="end">100</text><text x="24" y="58" text-anchor="end">50</text><text x="24" y="103" text-anchor="end">0</text>' +
    '<path fill="var(--accent-soft)" d="M' + x(0) + ",100 L" + pts.join(" L") + " L" + x(s.length - 1) + ',100 Z"></path>' +
    '<polyline fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" points="' + pts.join(" ") + '"></polyline>' +
    '<circle r="3.5" fill="var(--accent)" cx="' + x(s.length - 1) + '" cy="' + y(last) + '"></circle>' +
    '<text text-anchor="end" style="fill:var(--ink);font-weight:500" x="' + (x(s.length - 1) - 6) + '" y="' + Math.max(12, y(last) - 8) + '">' + last + "</text></svg>";
}

async function renderStats() {
  const s = await api("/api/stats");
  if (!s.graded) { $("tab-stats").innerHTML = '<h2>Stats</h2><p class="empty">Grade a few reviews to see stats.</p>'; return; }
  const conf = {};
  Object.entries(s.verdict_right_by_confidence).forEach(([k, v]) => (conf[CONF[k]] = v));
  const src = {};
  Object.entries(s.avg_score_by_source).forEach(([k, v]) => (src[k === "real" ? "Real" : "Generated"] = v / 100));
  $("tab-stats").innerHTML = "<h2>Stats</h2><p class=\"hint\">" + s.graded + ' graded reviews.</p><div class="cards">' +
    '<div class="card"><h3>Score trend</h3>' + trendSvg(s.trend) + "</div>" +
    '<div class="card"><h3>Calibration: verdict right, by confidence</h3>' + hbars(conf, pct, ["High", "Medium", "Low"]) +
    '<p class="hint">Well calibrated: High near 90% or more, Low near 50%.</p></div>' +
    '<div class="card"><h3>Miss rate by issue type</h3>' + hbars(s.miss_rate_by_category, pct) + "</div>" +
    '<div class="card"><h3>Miss rate by language</h3>' + hbars(s.miss_rate_by_language, pct) + "</div>" +
    '<div class="card"><h3>Time used vs target</h3>' + hbars(s.time_vs_target_by_difficulty, pct, ["easy", "medium", "hard"]) +
    '<p class="hint">Over 100% means slower than target.</p></div>' +
    '<div class="card"><h3>Average score by source</h3>' + hbars(src, (v) => Math.round(v * 100), ["Generated", "Real"]) +
    '<p class="hint">A big gap means generated bugs are too easy.</p></div></div>';
}

function showTab(tab) {
  state.tab = tab;
  document.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  ["practice", "history", "stats"].forEach((id) => ($("tab-" + id).hidden = id !== tab));
  if (tab === "history") renderHistory().catch(showError);
  if (tab === "stats") renderStats().catch(showError);
}

function showError(err) {
  const el = $("panel");
  el.insertAdjacentHTML("afterbegin", '<div class="error">' + esc(err.message || err) + "</div>");
}

// ---------- actions ----------

function saveComment() {
  const text = $("c-text").value.trim();
  if (!text) return;
  const d = state.draft;
  d.comments.push({ id: "c" + d.next++, file: state.composer.file, line: state.composer.line, category: $("c-cat").value, text });
  d.comments.sort((a, b) => (a.file === b.file ? a.line - b.line : a.file.localeCompare(b.file)));
  state.composer = null;
  saveDraft();
  render();
}

async function submitReview() {
  const d = state.draft;
  const btn = $("submit");
  btn.disabled = true;
  try {
    const attempt = await api("/api/problems/" + encodeURIComponent(state.current) + "/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ elapsed_seconds: Math.round(d.elapsed), verdict: d.verdict, confidence: Number(d.conf), comments: d.comments }),
    });
    clearDraft(state.current);
    state.draft = null;
    state.attempt = attempt;
    state.view = "attempt";
    state.composer = null;
    await refreshProblems();
    render();
  } catch (err) {
    btn.disabled = false;
    $("submit-hint").innerHTML = '<span class="bad">Could not submit: ' + esc(err.message) + "</span>";
  }
}

function nextProblem() {
  const next = state.problems.find((p) => p.id !== state.current && (!p.latest || loadDraft(p.id)));
  if (next) openProblem(next.id).catch(showError);
  else $("next").textContent = "Queue done. Run /generate for more";
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("button, tr[data-attempt]");
  if (!t) return;
  if (t.dataset.tab) return showTab(t.dataset.tab);
  if (t.dataset.attempt) { showTab("practice"); openProblem(t.dataset.problem, { attemptId: t.dataset.attempt }).catch(showError); return; }
  if (t.dataset.open) { openProblem(t.dataset.open).catch(showError); return; }
  if (t.dataset.file) { state.file = t.dataset.file; state.composer = null; renderWork(); return; }
  if (t.dataset.line) { state.composer = { file: state.file, line: Number(t.dataset.line) }; renderWork(); return; }
  if (t.dataset.del) { state.draft.comments.splice(Number(t.dataset.del), 1); saveDraft(); render(); return; }
  if (t.dataset.verdict) { state.draft.verdict = t.dataset.verdict; saveDraft(); renderPanel(); return; }
  if (t.dataset.conf) { state.draft.conf = Number(t.dataset.conf); saveDraft(); renderPanel(); return; }
  if (t.dataset.jump) {
    const [file, line] = t.dataset.jump.split("|");
    if (state.file !== file) { state.file = file; renderWork(); }
    const btn = document.querySelector('.ln[data-line="' + line + '"]');
    if (btn) btn.scrollIntoView({ block: "center", behavior: "smooth" });
    return;
  }
  switch (t.id) {
    case "c-save": saveComment(); break;
    case "c-cancel": state.composer = null; renderWork(); break;
    case "submit": submitReview(); break;
    case "next": nextProblem(); break;
    case "retry": openProblem(state.current, { retry: true }).catch(showError); break;
    case "copy":
      if (navigator.clipboard) navigator.clipboard.writeText("/grade").then(() => (t.textContent = "Copied"), () => (t.textContent = "Select it"));
      break;
  }
});

document.addEventListener("keydown", (e) => {
  if (e.target.id !== "c-text") return;
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveComment(); }
  if (e.key === "Escape") { state.composer = null; renderWork(); }
});

$("badge-mode").value = state.badgeMode;
$("badge-mode").addEventListener("change", (e) => {
  state.badgeMode = e.target.value;
  storageSet("rd-badge", state.badgeMode);
  renderWork();
});

// Timer runs only while reviewing and the tab is visible.
setInterval(() => {
  if (state.view !== "review" || !state.draft || document.hidden || state.tab !== "practice") return;
  state.draft.elapsed++;
  $("clock").textContent = fmt(state.draft.elapsed);
  if (state.draft.elapsed % 5 === 0) saveDraft();
}, 1000);
window.addEventListener("beforeunload", saveDraft);

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onopen = () => { $("live").classList.add("on"); $("live").textContent = "Live"; };
  es.onerror = () => { $("live").classList.remove("on"); $("live").textContent = "Reconnecting"; };
  es.addEventListener("feedback", (e) => {
    const data = JSON.parse(e.data);
    refreshProblems().catch(() => {});
    if (state.attempt && state.attempt.attempt_id === data.attempt_id) reloadAttempt().catch(showError);
    if (state.tab === "history") renderHistory().catch(() => {});
    if (state.tab === "stats") renderStats().catch(() => {});
  });
  es.addEventListener("problems", () => refreshProblems().catch(() => {}));
}

(async function init() {
  connectEvents();
  try {
    await refreshProblems();
    const first = state.problems.find((p) => loadDraft(p.id)) || state.problems.find((p) => !p.latest) || state.problems[0];
    if (first) await openProblem(first.id);
    else render();
  } catch (err) {
    $("work").innerHTML = '<p class="placeholder">Could not load problems: ' + esc(err.message) + "</p>";
  }
})();
