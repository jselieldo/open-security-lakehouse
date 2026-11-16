const state = { token: sessionStorage.getItem("osl_token") || "", alerts: [], events: [], selectedEvent: null, auth: null };
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

const severityLabels = { 0: "Debug", 1: "Informativa", 2: "Notice", 3: "Warning", 4: "Erro", 5: "Crítica", 6: "Emergência" };

function parseRawEvent(item) {
  try { return JSON.parse(item.raw_event_json || "{}"); }
  catch { return { message: item.raw_event_json || "" }; }
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

function base64Url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function beginOidcLogin() {
  state.auth ||= await fetch("/api/v1/auth/config").then((response) => response.json());
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(64)));
  const challenge = base64Url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  sessionStorage.setItem("osl_pkce_verifier", verifier);
  const params = new URLSearchParams({
    client_id: state.auth.client_id,
    redirect_uri: `${window.location.origin}/console/`,
    response_type: "code",
    scope: "openid profile email",
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.assign(`${state.auth.issuer_url}/protocol/openid-connect/auth?${params}`);
}

async function finishOidcLogin() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  if (!code) return;
  state.auth = await fetch("/api/v1/auth/config").then((response) => response.json());
  const verifier = sessionStorage.getItem("osl_pkce_verifier");
  if (!verifier) throw new Error("A sessão de autenticação expirou. Tente entrar novamente.");
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: state.auth.client_id,
    redirect_uri: `${window.location.origin}/console/`,
    code_verifier: verifier,
    code,
  });
  const response = await fetch(`${state.auth.issuer_url}/protocol/openid-connect/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) throw new Error("O provedor de identidade recusou o login.");
  const tokens = await response.json();
  state.token = tokens.access_token;
  sessionStorage.setItem("osl_token", state.token);
  sessionStorage.removeItem("osl_pkce_verifier");
  history.replaceState({}, document.title, "/console/");
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
    state.events = result.events;
    state.selectedEvent = null;
    $("#event-details").classList.add("hidden");
    const limitReached = result.returned_count >= (payload.limit || 100);
    $("#result-title").textContent = `${result.returned_count} eventos retornados${limitReached ? " (limite atingido)" : ""}`;
    $("#query-meta").textContent = `${result.scanned_objects} objetos examinados · ${result.duration_ms} ms`;
    $("#result-hint").textContent = limitReached ? "Há possivelmente mais eventos. Refine os filtros ou aumente o limite para ampliar a consulta." : "Todos os eventos correspondentes encontrados nos objetos examinados foram retornados.";
    $("#result-hint").classList.toggle("hidden", !result.events.length);
    $("#events-body").innerHTML = result.events.length ? result.events.map((item, index) => `<tr class="event-row" tabindex="0" data-event-index="${index}" aria-label="Abrir detalhes do evento ${escapeHtml(item.event_id)}"><td>${formatDate(item.event_time)}</td><td><span class="event-id">${escapeHtml(item.event_id)}</span></td><td>${escapeHtml(item.source)}</td><td>${escapeHtml(item.src_ip || "—")}</td><td><span class="severity severity-${item.severity_id}">${item.severity_id} · ${escapeHtml(severityLabels[item.severity_id] || "Desconhecida")}</span></td><td class="row-arrow">›</td></tr>`).join("") : '<tr><td colspan="6" class="empty-state">Nenhum evento corresponde aos filtros.</td></tr>';
    $$("[data-event-index]").forEach((row) => {
      row.addEventListener("click", () => showEventDetails(Number(row.dataset.eventIndex)));
      row.addEventListener("keydown", (keyEvent) => { if (["Enter", " "].includes(keyEvent.key)) { keyEvent.preventDefault(); showEventDetails(Number(row.dataset.eventIndex)); } });
    });
  } catch (error) { handleError(error); }
}

function showEventDetails(index) {
  const item = state.events[index];
  if (!item) return;
  state.selectedEvent = item;
  const raw = parseRawEvent(item);
  const syslog = raw.syslog || raw;
  const application = raw.application || syslog.appname || syslog.application || "—";
  const hostname = raw.hostname || syslog.hostname || "—";
  const facility = syslog.facility || syslog.facility_name || "—";
  const message = raw.message || syslog.message || "Mensagem não informada";
  $("#event-detail-title").textContent = item.event_id;
  $("#event-message").textContent = message;
  const metadata = [
    ["Horário do evento", formatDate(item.event_time)],
    ["Horário da ingestão", formatDate(item.ingested_at)],
    ["Fonte", item.source],
    ["IP de origem", item.src_ip || "—"],
    ["Aplicação", application],
    ["Hostname", hostname],
    ["Facility", facility],
    ["Severidade", `${item.severity_id} · ${severityLabels[item.severity_id] || "Desconhecida"}`],
    ["Classe", item.class_uid ?? "—"],
    ["Esquema", `${item.schema_name || "—"} ${item.schema_version || ""}`.trim()],
  ];
  $("#event-metadata").innerHTML = metadata.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  $("#event-json").textContent = JSON.stringify(raw, null, 2);
  $("#investigate-event-ip").disabled = !item.src_ip;
  $("#event-details").classList.remove("hidden");
  $$("[data-event-index]").forEach((row) => row.classList.toggle("selected", Number(row.dataset.eventIndex) === index));
  $("#event-details").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function searchFromSelected(mode) {
  const item = state.selectedEvent;
  if (!item) return;
  const form = $("#search-form");
  if (mode === "ip" && item.src_ip) form.elements.src_ip.value = item.src_ip;
  if (mode === "similar") {
    form.elements.source.value = item.source;
    form.elements.min_severity.value = item.severity_id;
  }
  form.requestSubmit();
  form.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function copySelectedJson() {
  if (!state.selectedEvent) return;
  await navigator.clipboard.writeText(JSON.stringify(parseRawEvent(state.selectedEvent), null, 2));
  showNotice("JSON do evento copiado para a área de transferência.");
  setTimeout(() => showNotice(""), 2200);
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
$("#close-event-details").addEventListener("click", () => $("#event-details").classList.add("hidden"));
$("#investigate-event-ip").addEventListener("click", () => searchFromSelected("ip"));
$("#similar-events").addEventListener("click", () => searchFromSelected("similar"));
$("#copy-event-json").addEventListener("click", () => copySelectedJson().catch(handleError));
$("#refresh-button").addEventListener("click", () => switchView($(".nav-item.active").dataset.view));
$("#token-button").addEventListener("click", () => $("#token-dialog").showModal());
$("#oidc-login").addEventListener("click", () => beginOidcLogin().catch(handleError));
$("#save-token").addEventListener("click", (event) => {
  event.preventDefault();
  state.token = $("#token-input").value.trim();
  if (!state.token) return;
  sessionStorage.setItem("osl_token", state.token);
  $("#token-dialog").close();
  loadDashboard();
});

finishOidcLogin().then(loadDashboard).catch(handleError);
