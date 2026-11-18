// Hash router: #/path?query. Each view module exports render(ctx) and fills ctx.root.
import { health } from "./api.js";
import { banner, clear, emptyState, h } from "./dom.js";
import * as dashboard from "./views/dashboard.js";
import * as leadDetail from "./views/lead-detail.js";
import * as leadNew from "./views/lead-new.js";
import * as leaderboard from "./views/leaderboard.js";
import * as leads from "./views/leads.js";
import * as member from "./views/member.js";
import * as team from "./views/team.js";

const ROUTES = [
  { pattern: /^\/dashboard$/, view: dashboard, nav: "dashboard" },
  { pattern: /^\/team$/, view: team, nav: "team" },
  { pattern: /^\/team\/(\d+)$/, view: member, nav: "team" },
  { pattern: /^\/leads$/, view: leads, nav: "leads" },
  { pattern: /^\/leads\/new$/, view: leadNew, nav: "lead-new" },
  { pattern: /^\/leads\/(\d+)$/, view: leadDetail, nav: "leads" },
  { pattern: /^\/leaderboard$/, view: leaderboard, nav: "leaderboard" },
];

const main = document.getElementById("main");
let renderCount = 0;

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/dashboard";
  const [path, search = ""] = raw.split("?");
  return { path: path || "/dashboard", query: new URLSearchParams(search) };
}

export function navigate(path, query) {
  const search = query ? new URLSearchParams(Object.entries(query).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString() : "";
  const target = "#" + path + (search ? "?" + search : "");
  if (location.hash === target) render({ keepFocus: true });
  else location.hash = target;
}

async function render({ keepFocus = false } = {}) {
  const { path, query } = parseHash();
  if (path === "/") return navigate("/dashboard");
  const route = ROUTES.find((r) => r.pattern.test(path));
  const id = ++renderCount;

  document.querySelectorAll("[data-nav]").forEach((a) => {
    const active = route && a.dataset.nav === route.nav;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });

  const root = h("div", { class: "view" });
  clear(main, root);

  if (!route) {
    document.title = "Page not found · Brokerage Desk";
    root.append(h("div", { class: "page" },
      h("header", { class: "page-head" }, h("h1", { class: "page-title", tabindex: "-1" }, "Page not found")),
      emptyState("There is no page at this address.", null, h("a", { class: "btn btn-primary", href: "#/dashboard" }, "Go to the dashboard"))));
    focusTitle(root, keepFocus);
    return;
  }

  const ctx = {
    root,
    params: path.match(route.pattern).slice(1),
    query,
    navigate,
    refresh: () => render({ keepFocus: true }),
    isCurrent: () => id === renderCount,
    setTitle: (title) => { document.title = `${title} · Brokerage Desk`; },
  };
  try {
    await route.view.render(ctx);
  } catch (err) {
    // last line of defence: a bug in a view still leaves a readable page, never a blank one
    console.error(err);
    if (!ctx.isCurrent()) return;
    clear(root, h("div", { class: "page" },
      h("header", { class: "page-head" }, h("h1", { class: "page-title", tabindex: "-1" }, "Something went wrong")),
      banner("error", "This page could not be displayed", "An unexpected error happened in the browser. Try again, and if it keeps happening, reload the page.", { retry: ctx.refresh })));
  }
  if (ctx.isCurrent()) focusTitle(root, keepFocus);
}

function focusTitle(root, keepFocus) {
  if (keepFocus) return;
  const title = root.querySelector(".page-title");
  if (title) title.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

// ---------- service status in the sidebar ----------

function setStatus(service, state, text) {
  const item = document.querySelector(`#service-status [data-service="${service}"]`);
  if (!item) return;
  item.dataset.state = state;
  item.querySelector(".status-text").textContent = text;
}

async function checkHealth() {
  const [kpi, routing] = await Promise.all([health("kpi"), health("routing")]);
  setStatus("kpi", kpi.state, kpi.text);
  setStatus("routing", routing.state, routing.text);
}

// A page's call just succeeded or failed: if that contradicts the sidebar, ask /health again
// (it can tell "service down" from "database down", which a failed call cannot).
let recheck = null;
window.addEventListener("service-seen", (e) => {
  const item = document.querySelector(`#service-status [data-service="${e.detail.service}"]`);
  if (!item || (item.dataset.state === "up") === e.detail.up || recheck) return;
  recheck = checkHealth().finally(() => { recheck = null; });
});

window.addEventListener("hashchange", () => render());
render();
checkHealth();
setInterval(checkHealth, 20000);
