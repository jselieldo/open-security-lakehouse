const state = { token: sessionStorage.getItem("osl_token") || "", alerts: [] };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function api(path, options = {}) {
  if (!state.token) throw new Error("TOKEN_REQUIRED");
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.token}`, ...(options.headers || {}) },
  });
  if (response.status === 401) throw new Error("TOKEN_INVALID");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Falha HTTP ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(new Date(value));
}

function showNotice(message) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("hidden", !message);
}

function requireToken() {
  if (!state.token) $("#token-dialog").showModal();
  return Boolean(state.token);
}

async function loadDashboard() {
  if (!requireToken()) return;
  try {
    const summary = await api("/api/v1/dashboard/summary");
    const items = [
      ["Eventos aceitos", summary.accepted_events, `${summary.ingestion_batches} lotes processados`],
      ["Em quarentena", summary.quarantined_events, "Falhas preservadas"],
      ["Alertas abertos", summary.open_alerts, `${summary.detection_runs} execuções`],
      ["Regras ativas", summary.detection_rules, "Detection-as-code"],
    ];
    $("#metrics").innerHTML = items.map(([label, value, sub]) => `<div class="metric"><small>${label}</small><strong>${value}</strong><span>${sub}</span></div>`).join("");
    renderRecentAlerts(summary.latest_alerts);
    $("#connection-label").textContent = "Operacional";
    $("#last-refresh").textContent = `Atualizado ${new Date().toLocaleTimeString("pt-BR")}`;
    showNotice("");
  } catch (error) { handleError(error); }
}

function renderRecentAlerts(alerts) {
  const target = $("#recent-alerts");
  if (!alerts.length) { target.innerHTML = '<div class="empty-state">Nenhum alerta aberto.</div>'; return; }
  target.innerHTML = alerts.map((alert) => `<div class="list-item"><div><strong>${escapeHtml(alert.title)}</strong><small>${formatDate(alert.created_at)} · ${alert.event_count} eventos</small></div><span class="badge">${escapeHtml(alert.severity)}</span></div>`).join("");
}

async function runSearch(event) {
  event.preventDefault();
  if (!requireToken()) return;
  const form = new FormData(event.currentTarget);
  const payload = {};
  for (const [key, value] of form.entries()) {
    if (!value) continue;
    if (["limit", "min_severity"].includes(key)) payload[key] = Number(value);
    else if (["start_time", "end_time"].includes(key)) payload[key] = new Date(value).toISOString();
    else payload[key] = value;
  }
  $("#result-title").textContent = "Consultando o lake…";
  try {
    const result = await api("/api/v1/investigations/search", { method: "POST", body: JSON.stringify(payload) });
    $("#result-title").textContent = `${result.returned_count} eventos encontrados`;
    $("#query-meta").textContent = `${result.scanned_objects} objetos · ${result.duration_ms} ms`;
    $("#events-body").innerHTML = result.events.length ? result.events.map((item) => `<tr><td>${formatDate(item.event_time)}</td><td>${escapeHtml(item.event_id)}</td><td>${escapeHtml(item.source)}</td><td>${escapeHtml(item.src_ip || "—")}</td><td><span class="severity">${item.severity_id}</span></td></tr>`).join("") : '<tr><td colspan="5" class="empty-state">Nenhum evento corresponde aos filtros.</td></tr>';
  } catch (error) { handleError(error); }
}

async function loadAlerts() {
  if (!requireToken()) return;
  try {
    state.alerts = await api("/api/v1/alerts?limit=100");
    const target = $("#alerts-list");
    target.innerHTML = state.alerts.length ? state.alerts.map((alert) => `<div class="list-item"><button data-alert="${escapeHtml(alert.alert_id)}"><strong>${escapeHtml(alert.title)}</strong><small>${formatDate(alert.created_at)} · ${alert.event_count} eventos</small></button><span class="badge">${escapeHtml(alert.severity)}</span></div>`).join("") : '<div class="empty-state">Nenhum alerta encontrado.</div>';
    $$('[data-alert]').forEach((button) => button.addEventListener("click", () => loadEvidence(button.dataset.alert)));
  } catch (error) { handleError(error); }
}

async function loadEvidence(alertId) {
  try {
    const evidence = await api(`/api/v1/alerts/${encodeURIComponent(alertId)}/evidence`);
    $("#evidence-title").textContent = evidence.rule.title;
    $("#evidence-content").textContent = JSON.stringify(evidence, null, 2);
  } catch (error) { handleError(error); }
}

async function loadRules() {
  if (!requireToken()) return;
  try {
    const rules = await api("/api/v1/detections/rules");
    $("#rules-grid").innerHTML = rules.map((rule) => `<article class="panel rule-card"><div class="panel-head"><div><p class="eyebrow">${escapeHtml(rule.id)}</p><h3>${escapeHtml(rule.title)}</h3></div><span class="status-dot"></span></div><p>${escapeHtml(rule.description)}</p><div class="rule-meta"><span>${escapeHtml(rule.severity)}</span><span>≥ ${rule.threshold} evento</span><span>${rule.schedule_minutes} min</span></div><button class="button secondary" data-run-rule="${escapeHtml(rule.id)}">Executar agora</button></article>`).join("");
    $$('[data-run-rule]').forEach((button) => button.addEventListener("click", () => runRule(button)));
  } catch (error) { handleError(error); }
}

async function runRule(button) {
  const original = button.textContent;
  button.disabled = true; button.textContent = "Executando…";
  try {
    const result = await api(`/api/v1/detections/rules/${encodeURIComponent(button.dataset.runRule)}/run`, { method: "POST" });
    button.textContent = `${result.matched_count} correspondências`;
    setTimeout(() => { button.textContent = original; button.disabled = false; }, 2200);
  } catch (error) { button.textContent = original; button.disabled = false; handleError(error); }
}

function handleError(error) {
  if (["TOKEN_REQUIRED", "TOKEN_INVALID"].includes(error.message)) {
    if (error.message === "TOKEN_INVALID") { state.token = ""; sessionStorage.removeItem("osl_token"); }
    $("#connection-label").textContent = "Autenticação necessária";
    $("#token-dialog").showModal();
    showNotice("Informe um token válido para acessar os dados da plataforma.");
  } else showNotice(error.message || "Não foi possível concluir a operação.");
}

function switchView(name) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `${name}-view`));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  const labels = { overview: "Visão geral", investigate: "Investigar", alerts: "Alertas", rules: "Detecções" };
  $("#page-title").textContent = labels[name];
  if (name === "overview") loadDashboard();
  if (name === "alerts") loadAlerts();
  if (name === "rules") loadRules();
}

$$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$$('[data-go]').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.go)));
$("#search-form").addEventListener("submit", runSearch);
$("#refresh-button").addEventListener("click", () => switchView($(".nav-item.active").dataset.view));
$("#token-button").addEventListener("click", () => $("#token-dialog").showModal());
$("#save-token").addEventListener("click", (event) => {
  event.preventDefault();
  state.token = $("#token-input").value.trim();
  if (!state.token) return;
  sessionStorage.setItem("osl_token", state.token);
  $("#token-dialog").close();
  loadDashboard();
});

loadDashboard();
