// Every call to the two services goes through request(), which turns any failure into an
// ApiError with a sentence a user can read. Views never see a raw fetch error.
const config = window.APP_CONFIG || {};

export const SERVICES = {
  kpi: { name: "KPI service", base: (config.KPI_URL || "/api/kpi").replace(/\/$/, "") },
  routing: { name: "routing service", base: (config.ROUTING_URL || "/api/routing").replace(/\/$/, "") },
};

// Long enough for an Azure SQL serverless database to resume from auto-pause.
const TIMEOUT_MS = 30000;

export class ApiError extends Error {
  // kind: "unavailable" (down, unreachable, timed out), "not_found", "rejected" (4xx), "server" (5xx)
  constructor(service, status, kind, message) {
    super(message);
    this.service = service;
    this.status = status;
    this.kind = kind;
  }
}

async function request(service, path, { method = "GET", body } = {}) {
  const svc = SERVICES[service];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response;
  try {
    response = await fetch(svc.base + path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err) {
    const message = err.name === "AbortError"
      ? `The ${svc.name} did not answer within ${TIMEOUT_MS / 1000} seconds.`
      : `Could not reach the ${svc.name}. Check your network connection.`;
    announce(service, false);
    throw new ApiError(service, 0, "unavailable", message);
  } finally {
    clearTimeout(timer);
  }

  let data = null;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  const serverMessage = data && typeof data.error === "string" ? data.error : null;

  if (response.status === 502 || response.status === 503 || response.status === 504) {
    announce(service, false);
    throw new ApiError(service, response.status, "unavailable", `The ${svc.name} is unavailable right now.`);
  }
  announce(service, true);
  if (response.status === 404) {
    throw new ApiError(service, 404, "not_found", capitalise(serverMessage || "Not found."));
  }
  if (response.status >= 400 && response.status < 500) {
    throw new ApiError(service, response.status, "rejected", capitalise(serverMessage || `The request was rejected (HTTP ${response.status}).`));
  }
  if (!response.ok) {
    throw new ApiError(service, response.status, "server", `The ${svc.name} hit an internal error (HTTP ${response.status}).`);
  }
  if (data === null) {
    throw new ApiError(service, response.status, "server", `The ${svc.name} sent an answer that could not be read.`);
  }
  return data;
}

function capitalise(text) {
  const trimmed = text.trim();
  const sentence = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(sentence) ? sentence : sentence + ".";
}

// Lets the sidebar status react immediately when a call shows a service went up or down.
function announce(service, up) {
  window.dispatchEvent(new CustomEvent("service-seen", { detail: { service, up } }));
}

// Runs promises side by side and never throws: each result is {ok, value} or {ok: false, error}.
export function settle(promises) {
  return Promise.all(promises.map((p) => p.then(
    (value) => ({ ok: true, value }),
    (error) => ({ ok: false, error: toApiError(error) }),
  )));
}

export function toApiError(error) {
  if (error instanceof ApiError) return error;
  return new ApiError(null, 0, "server", "Something unexpected went wrong in the page.");
}

const q = encodeURIComponent;

export const api = {
  // KPI service
  dashboard: (quarter) => request("kpi", `/dashboard?quarter=${q(quarter)}`),
  roles: () => request("kpi", "/roles").then((d) => d.roles),
  addRole: (name) => request("kpi", "/roles", { method: "POST", body: { name } }),
  members: () => request("kpi", "/members").then((d) => d.members),
  member: (id) => request("kpi", `/members/${q(id)}`),
  addMember: (member) => request("kpi", "/members", { method: "POST", body: member }),
  deactivate: (id) => request("kpi", `/members/${q(id)}/deactivate`, { method: "POST", body: {} }),
  memberKpis: (id) => request("kpi", `/members/${q(id)}/kpis`).then((d) => d.kpis),
  addKpi: (id, kpi) => request("kpi", `/members/${q(id)}/kpis`, { method: "POST", body: kpi }),
  targets: (id) => request("kpi", `/members/${q(id)}/targets`).then((d) => d.targets),
  setTarget: (id, target) => request("kpi", `/members/${q(id)}/targets`, { method: "PUT", body: target }),

  // Routing service
  leads: () => request("routing", "/leads").then((d) => d.leads),
  lead: (id) => request("routing", `/leads/${q(id)}`),
  addLead: (lead) => request("routing", "/leads", { method: "POST", body: lead }),
  addOutcome: (id, stage) => request("routing", `/leads/${q(id)}/outcomes`, { method: "POST", body: { stage } }),
  leaderboard: () => request("routing", "/leaderboard"),
};

// Health is read directly so a 503 body ({db: "unavailable"}) can be told apart from "unreachable".
export async function health(service) {
  const svc = SERVICES[service];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(svc.base + "/health", { cache: "no-store", signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (response.ok) return { state: "up", text: "Running" };
    if (data && data.db === "unavailable") return { state: "degraded", text: "Database down" };
    return { state: "down", text: "Unavailable" };
  } catch {
    return { state: "down", text: "Unreachable" };
  } finally {
    clearTimeout(timer);
  }
}
