import { api, settle } from "../api.js";
import {
  banner, clear, currentQuarter, emptyState, errorBanner, h, isQuarter, loading, METRICS, pageFrame,
  quarterLabel, quarterPicker, statusTag, byMetric,
} from "../dom.js";

export async function render(ctx) {
  const quarter = isQuarter(ctx.query.get("quarter")) ? ctx.query.get("quarter") : currentQuarter();
  ctx.setTitle("Dashboard");
  const page = pageFrame({
    title: "Dashboard",
    intro: `Quarterly KPI targets against what each member actually did in ${quarterLabel(quarter)}.`,
    actions: quarterPicker(quarter, (q) => ctx.navigate("/dashboard", { quarter: q })),
  });
  ctx.root.append(page.el);
  page.body.append(loading("Loading the dashboard…"));

  const [result] = await settle([api.dashboard(quarter)]);
  if (!ctx.isCurrent()) return;
  clear(page.body);

  if (!result.ok) {
    page.banners.append(errorBanner(result.error, "The dashboard could not be loaded", {
      retry: ctx.refresh,
      consequence: result.error.kind === "unavailable"
        ? "Targets live in the KPI service, so nothing can be shown until it is back."
        : null,
    }));
    page.body.append(emptyState("No dashboard data", "Once the KPI service answers, each member’s targets and progress appear here."));
    return;
  }

  const data = result.value;
  if (!data.activity_available) {
    page.banners.append(banner("notice", "Actuals unavailable",
      `${data.notice || "The routing service did not answer, so targets are shown without actuals."} Progress fills in once it is back.`,
      { retry: ctx.refresh }));
  }

  // active members first; the API sorts by name only
  const withTargets = data.rows.filter((r) => r.progress.length > 0).sort((a, b) => b.member.active - a.member.active);
  const withoutTargets = data.rows.filter((r) => r.progress.length === 0);

  if (withTargets.length === 0) {
    page.body.append(emptyState(
      `No targets set for ${quarterLabel(quarter)}`,
      "Open a member on the Team page to set their KPI targets for this quarter.",
      h("a", { class: "btn btn-primary", href: "#/team" }, "Go to Team")));
  } else {
    page.body.append(summary(withTargets, data.activity_available));
    page.body.append(h("section", { class: "section", "aria-labelledby": "progress-heading" },
      h("h2", { class: "section-title", id: "progress-heading" }, "Progress by member"),
      h("div", { class: "member-grid" }, withTargets.map((row) => memberCard(row, data.activity_available)))));
  }

  if (withoutTargets.length > 0) {
    page.body.append(h("section", { class: "section", "aria-labelledby": "no-targets-heading" },
      h("h2", { class: "section-title", id: "no-targets-heading" }, `No targets for ${quarterLabel(quarter)}`),
      h("ul", { class: "plain-list" }, withoutTargets.map(({ member }) => h("li", {},
        h("a", { href: `#/team/${member.id}` }, member.name),
        h("span", { class: "muted" }, ` · ${member.role_name}`),
        member.active ? null : h("span", { class: "tag tag-inactive tag-small" }, "Inactive"),
        h("a", { class: "list-action", href: `#/team/${member.id}` }, "Set targets"))))));
  }
}

// Team totals per metric, across every member that has a target for it.
function summary(rows, available) {
  const totals = new Map();
  for (const { progress } of rows) {
    for (const p of progress) {
      const t = totals.get(p.metric) || { target: 0, actual: 0 };
      t.target += p.target;
      t.actual += p.actual || 0;
      totals.set(p.metric, t);
    }
  }
  const order = Object.keys(METRICS).filter((m) => totals.has(m));
  return h("section", { class: "summary", "aria-label": "Team totals" },
    order.map((metric) => {
      const t = totals.get(metric);
      const percent = available && t.target > 0 ? Math.round((t.actual / t.target) * 100) : null;
      return h("div", { class: "summary-item" },
        h("p", { class: "summary-label" }, METRICS[metric]),
        h("p", { class: "summary-value" },
          available ? h("span", {}, String(t.actual)) : h("span", { class: "muted" }, "—"),
          h("span", { class: "summary-of" }, ` / ${t.target}`)),
        bar(percent),
        h("p", { class: "summary-foot" }, percent === null ? "Actuals unavailable" : `${percent}% of team target`));
    }));
}

function memberCard({ member, progress }, available) {
  const percents = progress.map((p) => p.percent).filter((p) => p !== null);
  const overall = available && percents.length
    ? Math.round(percents.reduce((a, b) => a + Math.min(b, 100), 0) / percents.length)
    : null;
  return h("article", { class: "card member-card" },
    h("header", { class: "member-card-head" },
      h("div", {},
        h("h3", { class: "member-card-name" }, h("a", { href: `#/team/${member.id}` }, member.name)),
        h("p", { class: "member-card-role" }, member.role_name, member.active ? null : [" ", statusTag(false)])),
      h("div", { class: "member-card-overall", title: "Average progress across KPIs, each capped at 100%" },
        h("span", { class: "overall-value" }, overall === null ? "—" : `${overall}%`),
        h("span", { class: "overall-label" }, "overall"))),
    h("ul", { class: "kpi-list" }, [...progress].sort(byMetric).map((p) => h("li", { class: "kpi" },
      h("div", { class: "kpi-row" },
        h("span", { class: "kpi-name" }, p.kpi_name),
        p.actual === null
          ? h("span", { class: "kpi-figures muted" }, `target ${p.target}`)
          : h("span", { class: "kpi-figures" }, h("strong", {}, String(p.actual)), ` / ${p.target}`)),
      bar(p.percent, p.actual === null),
      h("p", { class: "kpi-foot" }, p.actual === null
        ? "Actuals unavailable"
        : p.percent === null ? "No target to measure against" : `${p.percent}%${p.percent >= 100 ? " · target reached" : ""}`)))));
}

function bar(percent, unavailable = false) {
  const width = percent === null ? 0 : Math.min(percent, 100);
  const el = h("div", {
    class: "bar" + (unavailable || percent === null ? " bar-empty" : "") + (percent !== null && percent >= 100 ? " bar-done" : ""),
    role: "progressbar",
    "aria-valuemin": "0",
    "aria-valuemax": "100",
    "aria-valuenow": percent === null ? null : String(width),
    "aria-valuetext": percent === null ? "Actual unavailable" : `${percent}% of target`,
  }, h("span", { class: "bar-fill" }));
  el.firstChild.style.transform = `scaleX(${width / 100})`;
  return el;
}
