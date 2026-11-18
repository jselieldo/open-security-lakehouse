const state = { token: sessionStorage.getItem("osl_token") || "", alerts: [], selectedAlertId: null, events: [], selectedEvent: null, searchPayload: null, currentPage: 1, totalPages: 1, auth: null };
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

function eventDisplay(item) {
  const raw = parseRawEvent(item);
  const windows = raw.windows && typeof raw.windows === "object" ? raw.windows : {};
  const syslog = raw.syslog && typeof raw.syslog === "object" ? raw.syslog : raw;
  const typeParts = String(item.event_type || "").split(".");
  const isWindows = typeParts[0] === "windows";
  return {
    raw,
    windows,
    isWindows,
    eventCode: windows.event_id ?? (isWindows ? typeParts.at(-1) : item.event_id),
    channel: windows.channel || (isWindows ? typeParts.slice(1, -1).join(".").replaceAll("_", " ") : item.source),
    provider: windows.provider_name || item.application || raw.application || syslog.appname || syslog.application || "—",
    hostname: windows.computer || item.hostname || raw.hostname || syslog.hostname || "—",
    recordId: windows.record_id ?? "—",
    level: windows.level || "—",
    message: raw.message || windows.message || syslog.message || "Mensagem não informada",
    facility: syslog.facility || syslog.facility_name || "—",
  };
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
    if (["limit", "min_severity", "windows_event_id"].includes(key)) payload[key] = Number(value);
    else if (["start_time", "end_time"].includes(key)) payload[key] = new Date(value).toISOString();
    else payload[key] = value;
  }
  state.searchPayload = payload;
  await executeSearch(1);
}

async function executeSearch(page) {
  if (!state.searchPayload) return;
  const payload = { ...state.searchPayload };
  payload.offset = (page - 1) * payload.limit;
  $("#result-title").textContent = "Consultando o lake…";
  try {
    const result = await api("/api/v1/investigations/search", { method: "POST", body: JSON.stringify(payload) });
    state.events = result.events;
    state.selectedEvent = null;
    $("#event-details").classList.add("hidden");
    state.currentPage = Math.floor(result.offset / result.limit) + 1;
    state.totalPages = Math.max(1, Math.ceil(result.total_count / result.limit));
    $("#result-title").textContent = `${result.total_count} eventos encontrados`;
    $("#query-meta").textContent = `${result.scanned_objects} objetos examinados · ${result.duration_ms} ms`;
    $("#result-hint").textContent = result.total_count > result.returned_count ? `Exibindo ${result.returned_count} eventos nesta página.` : "Todos os eventos correspondentes cabem nesta página.";
    $("#result-hint").classList.toggle("hidden", !result.events.length);
    $("#events-body").innerHTML = result.events.length ? result.events.map((item, index) => {
      const display = eventDisplay(item);
      const host = item.src_ip ? `${display.hostname} · ${item.src_ip}` : display.hostname;
      return `<tr class="event-row" tabindex="0" data-event-index="${index}" aria-label="Abrir detalhes do evento ${escapeHtml(item.event_id)}"><td>${formatDate(item.event_time)}</td><td><span class="event-code">${escapeHtml(display.eventCode)}</span><small class="cell-secondary">${escapeHtml(item.event_id)}</small></td><td>${escapeHtml(display.channel)}<small class="cell-secondary">${escapeHtml(item.source)}</small></td><td>${escapeHtml(display.provider)}</td><td>${escapeHtml(host)}</td><td><span class="severity severity-${item.severity_id}">${item.severity_id} · ${escapeHtml(severityLabels[item.severity_id] || "Desconhecida")}</span></td><td class="row-arrow">›</td></tr>`;
    }).join("") : '<tr><td colspan="7" class="empty-state">Nenhum evento corresponde aos filtros.</td></tr>';
    $$("[data-event-index]").forEach((row) => {
      row.addEventListener("click", () => showEventDetails(Number(row.dataset.eventIndex)));
      row.addEventListener("keydown", (keyEvent) => { if (["Enter", " "].includes(keyEvent.key)) { keyEvent.preventDefault(); showEventDetails(Number(row.dataset.eventIndex)); } });
    });
    renderPagination(result);
  } catch (error) { handleError(error); }
}

function renderPagination(result) {
  const first = result.total_count ? result.offset + 1 : 0;
  const last = result.offset + result.returned_count;
  $("#page-range").textContent = `${first}–${last} de ${result.total_count}`;
  $("#page-label").textContent = `Página ${state.currentPage} de ${state.totalPages}`;
  $("#first-page").disabled = state.currentPage <= 1;
  $("#previous-page").disabled = state.currentPage <= 1;
  $("#next-page").disabled = state.currentPage >= state.totalPages;
  $("#last-page").disabled = state.currentPage >= state.totalPages;
  $("#pagination").classList.toggle("hidden", result.total_count === 0);
}

function goToPage(page) {
  if (page < 1 || page > state.totalPages || page === state.currentPage) return;
  executeSearch(page).then(() => $("#result-title").scrollIntoView({ behavior: "smooth", block: "start" })).catch(handleError);
}

function showEventDetails(index) {
  const item = state.events[index];
  if (!item) return;
  state.selectedEvent = item;
  const display = eventDisplay(item);
  $("#event-detail-title").textContent = display.isWindows ? `Windows Event ID ${display.eventCode}` : item.event_id;
  $("#event-message").textContent = display.message;
  const metadata = [
    ["Horário do evento", formatDate(item.event_time)],
    ["Horário da ingestão", formatDate(item.ingested_at)],
    ["Fonte", item.source],
    ["Tipo de evento", item.event_type || "—"],
    ["IP de origem", item.src_ip || "—"],
    ["Aplicação / provedor", display.provider],
    ["Hostname", display.hostname],
    ["Canal do Windows", display.isWindows ? display.channel : "—"],
    ["Event ID do Windows", display.isWindows ? display.eventCode : "—"],
    ["Record ID do Windows", display.isWindows ? display.recordId : "—"],
    ["Nível original", display.isWindows ? display.level : "—"],
    ["Facility", display.facility],
    ["Severidade", `${item.severity_id} · ${severityLabels[item.severity_id] || "Desconhecida"}`],
    ["Classe", item.class_uid ?? "—"],
    ["Esquema", `${item.schema_name || "—"} ${item.schema_version || ""}`.trim()],
  ];
  $("#event-metadata").innerHTML = metadata.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  $("#event-json").textContent = JSON.stringify(display.raw, null, 2);
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
    const display = eventDisplay(item);
    if (display.isWindows) {
      form.elements.windows_channel.value = display.channel;
      form.elements.windows_event_id.value = display.eventCode;
    } else {
      form.elements.event_type.value = item.event_type || "";
    }
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
    $$('[data-alert]').forEach((button) => button.addEventListener("click", () => loadAlertDetail(button.dataset.alert)));
  } catch (error) { handleError(error); }
}

async function loadAlertDetail(alertId) {
  try {
    state.selectedAlertId = alertId;
    const [detail, evidence] = await Promise.all([
      api(`/api/v1/alerts/${encodeURIComponent(alertId)}`),
      api(`/api/v1/alerts/${encodeURIComponent(alertId)}/evidence`),
    ]);
    $("#evidence-title").textContent = evidence.rule.title;
    $("#evidence-content").textContent = JSON.stringify(evidence, null, 2);
    $("#alert-status").textContent = detail.alert.status.replaceAll("_", " ");
    $("#alert-status").classList.remove("hidden");
    $("#alert-status-select").value = detail.alert.status;
    const allowed = {
      open: ["open", "investigating", "resolved", "false_positive"],
      investigating: ["investigating", "open", "resolved", "false_positive"],
      resolved: ["resolved", "reopened"],
      false_positive: ["false_positive", "reopened"],
      reopened: ["reopened", "investigating", "resolved", "false_positive"],
    }[detail.alert.status] || [detail.alert.status];
    [...$("#alert-status-select").options].forEach((option) => { option.disabled = !allowed.includes(option.value); });
    $("#triage-controls").classList.remove("hidden");
    $("#alert-comment-form").classList.remove("hidden");
    $("#alert-assignee").textContent = detail.alert.assignee_username ? `Responsável: ${detail.alert.assignee_username}` : "Sem responsável";
    $("#alert-assignee").classList.remove("hidden");
    $("#assign-alert").dataset.assigned = detail.alert.assignee_username ? "true" : "false";
    $("#assign-alert").textContent = detail.alert.assignee_username ? "Liberar responsável" : "Assumir alerta";
    const timeline = [
      ...detail.history.map((item) => ({ at: item.created_at, title: item.action.replaceAll("_", " "), text: `${item.actor_username}${item.new_value ? ` · ${item.new_value}` : ""}` })),
      ...detail.comments.map((item) => ({ at: item.created_at, title: `Comentário · ${item.author_username}`, text: item.body })),
    ].sort((a, b) => new Date(b.at) - new Date(a.at));
    $("#alert-timeline").innerHTML = timeline.length ? timeline.map((item) => `<div><span></span><p><strong>${escapeHtml(item.title)}</strong><small>${formatDate(item.at)}</small>${escapeHtml(item.text)}</p></div>`).join("") : '<div class="empty-state">Nenhuma ação de triagem registrada.</div>';
    $("#alert-timeline").classList.remove("hidden");
  } catch (error) { handleError(error); }
}

async function updateSelectedAlert(payload) {
  if (!state.selectedAlertId) return;
  await api(`/api/v1/alerts/${encodeURIComponent(state.selectedAlertId)}`, { method: "PATCH", body: JSON.stringify(payload) });
  await loadAlertDetail(state.selectedAlertId);
  await loadAlerts();
}

async function submitAlertComment(event) {
  event.preventDefault();
  const input = $("#alert-comment");
  const body = input.value.trim();
  if (!body || !state.selectedAlertId) return;
  await api(`/api/v1/alerts/${encodeURIComponent(state.selectedAlertId)}/comments`, { method: "POST", body: JSON.stringify({ body }) });
  input.value = "";
  await loadAlertDetail(state.selectedAlertId);
}

async function loadRules() {
  if (!requireToken()) return;
  try {
    const rules = await api("/api/v1/detections/rules");
    $("#rules-grid").innerHTML = rules.map((rule) => `<article class="panel rule-card"><div class="panel-head"><div><p class="eyebrow">${escapeHtml(rule.id)}</p><h3>${escapeHtml(rule.title)}</h3></div><span class="status-dot"></span></div><p>${escapeHtml(rule.description)}</p><div class="rule-meta"><span>${escapeHtml(rule.severity)}</span><span>≥ ${rule.threshold} evento</span><span>${rule.schedule_minutes} min</span></div><button class="button secondary" data-run-rule="${escapeHtml(rule.id)}">Executar agora</button></article>`).join("");
    $$('[data-run-rule]').forEach((button) => button.addEventListener("click", () => runRule(button)));
  } catch (error) { handleError(error); }
}

async function loadSources() {
  if (!requireToken()) return;
  try {
    const sources = await api("/api/v1/sources");
    $("#sources-list").innerHTML = sources.length ? sources.map((item) =>
      `<div class="list-item"><div><strong>${escapeHtml(item.display_name)}</strong><small>${escapeHtml(item.source_id)} · ${escapeHtml(item.kind)} · ${escapeHtml(item.hostname || "todos os hosts")} · ${item.configured ? "configurada" : "observada"}</small><small>Último evento: ${formatDate(item.last_received_at)} · ${item.accepted_events} aceitos · ${item.rejected_events} rejeitados</small></div><span class="badge">${escapeHtml(item.status)}</span></div>`
    ).join("") : '<div class="empty-state">Nenhuma fonte registrada ou observada.</div>';
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
  const labels = { overview: "Visão geral", investigate: "Investigar", alerts: "Alertas", rules: "Detecções", sources: "Fontes" };
  $("#page-title").textContent = labels[name];
  if (name === "overview") loadDashboard();
  if (name === "alerts") loadAlerts();
  if (name === "rules") loadRules();
  if (name === "sources") loadSources();
}

$$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$$('[data-go]').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.go)));
$("#search-form").addEventListener("submit", runSearch);
$("#close-event-details").addEventListener("click", () => $("#event-details").classList.add("hidden"));
$("#investigate-event-ip").addEventListener("click", () => searchFromSelected("ip"));
$("#similar-events").addEventListener("click", () => searchFromSelected("similar"));
$("#copy-event-json").addEventListener("click", () => copySelectedJson().catch(handleError));
$("#first-page").addEventListener("click", () => goToPage(1));
$("#previous-page").addEventListener("click", () => goToPage(state.currentPage - 1));
$("#next-page").addEventListener("click", () => goToPage(state.currentPage + 1));
$("#last-page").addEventListener("click", () => goToPage(state.totalPages));
$("#save-alert-status").addEventListener("click", () => updateSelectedAlert({ status: $("#alert-status-select").value }).catch(handleError));
$("#assign-alert").addEventListener("click", () => updateSelectedAlert({ assign_to_me: $("#assign-alert").dataset.assigned !== "true" }).catch(handleError));
$("#alert-comment-form").addEventListener("submit", (event) => submitAlertComment(event).catch(handleError));
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
