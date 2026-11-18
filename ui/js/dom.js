// Small helpers shared by the views. Elements are built with h(), which only ever creates
// text nodes from data, so a lead source or member name can never inject HTML.

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "text") el.textContent = value;
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

// ---------- page frame ----------

// Every view starts from this frame, so a page always has a title and a banner area even
// when every call fails.
export function pageFrame({ title, intro, actions }) {
  const banners = h("div", { class: "banners", "aria-live": "polite" });
  const body = h("div", { class: "page-body" });
  const el = h("div", { class: "page" },
    h("header", { class: "page-head" },
      h("div", { class: "page-heading" },
        h("h1", { class: "page-title", tabindex: "-1" }, title),
        intro ? h("p", { class: "page-intro" }, intro) : null),
      actions ? h("div", { class: "page-actions" }, actions) : null),
    banners,
    body);
  return { el, banners, body };
}

// kind: "error" | "notice" | "success"
export function banner(kind, title, message, { retry, action } = {}) {
  const el = h("div", { class: `banner banner-${kind}`, role: kind === "error" ? "alert" : "status" },
    h("span", { class: "banner-icon", "aria-hidden": "true" }, kind === "error" ? "!" : kind === "notice" ? "i" : "✓"),
    h("div", { class: "banner-body" },
      h("p", { class: "banner-title" }, title),
      message ? h("p", { class: "banner-text" }, message) : null),
    retry ? h("button", { class: "btn btn-quiet btn-small", type: "button", onclick: retry }, "Try again") : null,
    action || null);
  return el;
}

export function errorBanner(error, title, { retry, consequence } = {}) {
  const message = [error.message, consequence].filter(Boolean).join(" ");
  return banner("error", title, message, { retry });
}

// Puts each message right under its field, links it with aria-describedby, marks the field
// invalid and focuses the first one. Returns true when there was something to show.
export function showFieldErrors(form, problems) {
  form.querySelectorAll(".field-error").forEach((el) => el.remove());
  form.querySelectorAll("[aria-invalid]").forEach((input) => {
    input.removeAttribute("aria-invalid");
    const original = input.dataset.describedby;
    if (original) input.setAttribute("aria-describedby", original);
    else input.removeAttribute("aria-describedby");
    delete input.dataset.describedby;
  });
  for (const [input, message] of problems) {
    const id = `${input.id}-error`;
    const note = h("p", { class: "field-error", id }, message);
    input.dataset.describedby = input.getAttribute("aria-describedby") || "";
    input.setAttribute("aria-describedby", [id, input.dataset.describedby].filter(Boolean).join(" "));
    input.setAttribute("aria-invalid", "true");
    const row = input.closest(".target-row");
    if (row) row.firstElementChild.append(note);
    else input.insertAdjacentElement("afterend", note);
  }
  if (problems.length) problems[0][0].focus();
  return problems.length > 0;
}

export function emptyState(title, text, action) {
  return h("div", { class: "empty" },
    h("p", { class: "empty-title" }, title),
    text ? h("p", { class: "empty-text" }, text) : null,
    action || null);
}

export function loading(label = "Loading…") {
  return h("div", { class: "loading", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), label);
}

export function tableWrap(table) {
  return h("div", { class: "table-wrap" }, table);
}

export function setBusy(button, busy, busyLabel) {
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

// ---------- domain formatting ----------

export const STAGES = ["none", "showing_booked", "showing_performed", "closed"];
export const STAGE_LABELS = {
  none: "No outcome yet",
  showing_booked: "Showing booked",
  showing_performed: "Showing performed",
  closed: "Closed",
};
export const BAND_LABELS = { hot: "Hot", warm: "Warm", cold: "Cold" };
export const METRICS = {
  leads_assigned: "Leads assigned",
  showings_booked: "Showings booked",
  showings_performed: "Showings performed",
  deals_closed: "Deals closed",
};

// Funnel order (leads -> showings -> deals) instead of the API's alphabetical order.
export function byMetric(a, b) {
  const order = Object.keys(METRICS);
  return order.indexOf(a.metric) - order.indexOf(b.metric);
}

export function bandForScore(score) {
  if (score >= 70) return "hot";
  if (score >= 40) return "warm";
  return "cold";
}

export function bandTag(band) {
  return h("span", { class: `tag tag-${band}` }, BAND_LABELS[band] || band);
}

export function stageTag(stage) {
  return h("span", { class: `stage stage-${stage}` }, STAGE_LABELS[stage] || stage);
}

export function statusTag(active) {
  return active
    ? h("span", { class: "tag tag-active" }, "Active")
    : h("span", { class: "tag tag-inactive" }, "Inactive");
}

// the reader's own locale (navigator.languages), so dates read naturally wherever they are
const LOCALES = navigator.languages && navigator.languages.length ? navigator.languages : undefined;
const dateFormat = new Intl.DateTimeFormat(LOCALES, { day: "numeric", month: "short", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat(LOCALES, {
  day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});

const scoreFormat = new Intl.NumberFormat(LOCALES, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });
export function fmtScore(score) {
  return scoreFormat.format(score);
}

export function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFormat.format(d);
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateTimeFormat.format(d);
}

export function timeEl(iso, withTime = false) {
  return h("time", { datetime: iso || null }, withTime ? fmtDateTime(iso) : fmtDate(iso));
}

// ---------- quarters ----------

export function currentQuarter(date = new Date()) {
  return `${date.getUTCFullYear()}-Q${Math.floor(date.getUTCMonth() / 3) + 1}`;
}

export function isQuarter(text) {
  return /^\d{4}-Q[1-4]$/.test(text || "");
}

export function shiftQuarter(quarter, by) {
  const [year, q] = quarter.split("-Q").map(Number);
  const index = year * 4 + (q - 1) + by;
  return `${Math.floor(index / 4)}-Q${(index % 4) + 1}`;
}

export function quarterLabel(quarter) {
  const [year, q] = quarter.split("-Q");
  return `Q${q} ${year}`;
}

// A quarter picker: previous / select / next. Calls onChange(quarter).
export function quarterPicker(selected, onChange, { id = "quarter" } = {}) {
  const now = currentQuarter();
  const options = [];
  for (let i = -6; i <= 2; i++) options.push(shiftQuarter(now, i));
  if (!options.includes(selected)) options.push(selected);
  options.sort();
  const select = h("select", { id, name: id, class: "input input-select", onchange: (e) => onChange(e.target.value) },
    options.map((qtr) => h("option", { value: qtr, selected: qtr === selected }, quarterLabel(qtr) + (qtr === now ? " (current)" : ""))));
  return h("div", { class: "quarter-picker" },
    h("label", { class: "visually-hidden", for: id }, "Quarter"),
    h("button", { class: "btn btn-quiet btn-icon", type: "button", "aria-label": "Previous quarter", onclick: () => onChange(shiftQuarter(selected, -1)) }, "‹"),
    select,
    h("button", { class: "btn btn-quiet btn-icon", type: "button", "aria-label": "Next quarter", onclick: () => onChange(shiftQuarter(selected, 1)) }, "›"));
}

// ---------- member names ----------

// Builds a lookup from KPI /members. When KPI is down the map is null and names fall back to "#id".
export function memberLookup(members) {
  if (!members) return null;
  return new Map(members.map((m) => [m.id, m]));
}

export function memberName(lookup, id, { link = true } = {}) {
  if (id === null || id === undefined) return h("span", { class: "muted" }, "Unassigned");
  const m = lookup && lookup.get(id);
  if (!m) {
    return h("span", { class: "member-id", title: lookup ? "Not found in the KPI service" : "Name unavailable while the KPI service is down" }, `#${id}`);
  }
  const name = link ? h("a", { href: `#/team/${m.id}` }, m.name) : h("span", {}, m.name);
  return h("span", { class: "member-name" }, name, m.active ? null : h("span", { class: "tag tag-inactive tag-small" }, "Inactive"));
}
