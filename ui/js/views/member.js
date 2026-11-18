import { api, settle, toApiError } from "../api.js";
import {
  banner, clear, currentQuarter, emptyState, errorBanner, h, isQuarter, loading, METRICS, pageFrame,
  quarterLabel, quarterPicker, setBusy, showFieldErrors, statusTag, tableWrap, byMetric,
} from "../dom.js";

export async function render(ctx) {
  const id = Number(ctx.params[0]);
  const quarter = isQuarter(ctx.query.get("quarter")) ? ctx.query.get("quarter") : currentQuarter();
  ctx.setTitle("Team member");
  const page = pageFrame({ title: "Team member", intro: null, actions: null });
  page.el.prepend(h("a", { class: "back-link", href: "#/team" }, "← Team"));
  ctx.root.append(page.el);
  page.body.append(loading("Loading member…"));

  const [memberResult, kpisResult, targetsResult] = await settle([api.member(id), api.memberKpis(id), api.targets(id)]);
  if (!ctx.isCurrent()) return;
  clear(page.body);

  if (!memberResult.ok) {
    const notFound = memberResult.error.kind === "not_found";
    page.banners.append(notFound
      ? banner("error", "Member not found", `There is no team member with id ${id}.`)
      : errorBanner(memberResult.error, "This member could not be loaded", { retry: ctx.refresh }));
    page.body.append(emptyState(notFound ? "Nothing to show" : "Member details unavailable", null,
      h("a", { class: "btn btn-quiet", href: "#/team" }, "Back to Team")));
    return;
  }

  const member = memberResult.value;
  ctx.setTitle(member.name);
  page.el.querySelector(".page-title").textContent = member.name;
  const head = page.el.querySelector(".page-heading");
  head.append(h("p", { class: "page-intro" }, `${member.role_name} · ${member.email} `, statusTag(member.active)));

  if (!member.active) {
    page.banners.append(banner("notice", "This member is inactive", "Targets can still be edited for reporting, but they no longer receive leads."));
  }

  // Targets editor for one quarter
  const editor = h("section", { class: "card section-card", "aria-labelledby": "targets-heading" });
  page.body.append(editor);
  if (!kpisResult.ok || !targetsResult.ok) {
    const error = !kpisResult.ok ? kpisResult.error : targetsResult.error;
    clear(editor,
      h("h2", { class: "section-title", id: "targets-heading" }, "KPI targets"),
      errorBanner(error, "Targets could not be loaded", { retry: ctx.refresh }));
    return;
  }

  let kpis = [...kpisResult.value].sort(byMetric);
  let targets = targetsResult.value;

  const historySlot = h("section", { class: "section", "aria-labelledby": "history-heading" });
  const addKpiSlot = h("section", { class: "card section-card", "aria-labelledby": "add-kpi-heading" });
  page.body.append(addKpiSlot, historySlot);

  function renderEditor() {
    const [year, q] = quarter.split("-Q").map(Number);
    const current = new Map(targets.filter((t) => t.year === year && t.quarter === q).map((t) => [t.kpi_id, t.target_value]));
    const status = h("div", { "aria-live": "polite" });
    const head = h("div", { class: "section-head" },
      h("div", {},
        h("h2", { class: "section-title", id: "targets-heading" }, `KPI targets for ${quarterLabel(quarter)}`),
        h("p", { class: "section-intro" }, `Targets for every KPI defined for the ${member.role_name} role.`)),
      quarterPicker(quarter, (next) => ctx.navigate(`/team/${id}`, { quarter: next }), { id: "target-quarter" }));

    if (kpis.length === 0) {
      clear(editor, head, emptyState(`The ${member.role_name} role has no KPIs yet`,
        "Add a KPI below, then set this member’s target for it."));
      return;
    }

    const inputs = kpis.map((k) => h("input", {
      class: "input input-number", type: "number", min: "0", step: "1", inputmode: "numeric",
      id: `target-${k.id}`, name: `target-${k.id}`, autocomplete: "off", value: current.has(k.id) ? String(current.get(k.id)) : "",
      placeholder: "Not set", "aria-describedby": `metric-${k.id}`,
    }));
    const save = h("button", { class: "btn btn-primary", type: "submit" }, "Save targets");
    const form = h("form", { class: "targets-form", novalidate: true },
      status,
      h("ul", { class: "target-list" }, kpis.map((k, i) => h("li", { class: "target-row" },
        h("div", {},
          h("label", { class: "target-name", for: `target-${k.id}` }, k.name),
          h("p", { class: "cell-sub", id: `metric-${k.id}` }, `Measured as: ${METRICS[k.metric] || k.metric}`)),
        inputs[i]))),
      h("div", { class: "form-actions" }, save));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(status);
      const changes = [];
      const invalid = [];
      kpis.forEach((k, i) => {
        const raw = inputs[i].value.trim();
        if (raw === "") return;
        const value = Number(raw);
        if (!Number.isInteger(value) || value < 0) { invalid.push([inputs[i], "Use a whole number, 0 or more."]); return; }
        if (current.get(k.id) !== value) changes.push({ kpi_id: k.id, target_value: value, quarter, name: k.name });
      });
      if (showFieldErrors(form, invalid)) return;
      if (!changes.length) {
        status.append(banner("notice", "Nothing to save", "No target was changed."));
        return;
      }
      setBusy(save, true, "Saving…");
      const failed = [];
      for (const change of changes) {
        try {
          targets = (await api.setTarget(id, change)).targets;
        } catch (err) {
          failed.push(`${change.name}: ${toApiError(err).message}`);
        }
      }
      setBusy(save, false);
      renderEditor();
      renderHistory();
      const saved = changes.length - failed.length;
      const statusNow = editor.querySelector("[aria-live]");
      if (failed.length) {
        statusNow.append(banner("error", saved ? `Saved ${saved}, but ${failed.length} failed` : "Targets could not be saved", failed.join(" ")));
      } else {
        statusNow.append(banner("success", `Saved ${saved} target${saved === 1 ? "" : "s"} for ${quarterLabel(quarter)}`, null));
      }
    });
    clear(editor, head, form);
  }

  function renderAddKpi() {
    const errorSlot = h("div", { "aria-live": "polite" });
    const name = h("input", { class: "input", id: "kpi-name", name: "kpi_name", autocomplete: "off", maxlength: "100", placeholder: "e.g. Deals closed…" });
    const metric = h("select", { class: "input input-select", id: "kpi-metric", name: "metric" },
      Object.entries(METRICS).map(([value, label]) => h("option", { value }, label)));
    const submit = h("button", { class: "btn btn-quiet", type: "submit" }, "Add KPI");
    const form = h("form", { class: "form-inline", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "kpi-name" }, "KPI name"), name),
      h("div", { class: "field" }, h("label", { for: "kpi-metric" }, "Measured as"), metric),
      submit);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errorSlot);
      if (showFieldErrors(form, name.value.trim() ? [] : [[name, "Give the KPI a name, for example “Deals closed”."]])) return;
      setBusy(submit, true, "Adding…");
      try {
        await api.addKpi(id, { name: name.value.trim(), metric: metric.value });
        kpis = (await api.memberKpis(id)).sort(byMetric);
        renderEditor();
        renderAddKpi();
        addKpiSlot.querySelector("[aria-live]").append(banner("success", "KPI added", `Every ${member.role_name} member now has it. Set this member’s target above.`));
      } catch (err) {
        errorSlot.append(errorBanner(toApiError(err), "The KPI could not be added"));
        setBusy(submit, false);
      }
    });
    clear(addKpiSlot,
      h("h2", { class: "section-title", id: "add-kpi-heading" }, `Add a KPI to the ${member.role_name} role`),
      h("p", { class: "section-intro" }, "Actuals come from the routing service, so a KPI must be measured as one of the four lead metrics."),
      errorSlot, form);
  }

  function renderHistory() {
    clear(historySlot, h("h2", { class: "section-title", id: "history-heading" }, "All targets"));
    if (!targets.length) {
      historySlot.append(emptyState("No targets yet", "Targets saved for any quarter are listed here."));
      return;
    }
    historySlot.append(tableWrap(h("table", { class: "table" },
      h("thead", {}, h("tr", {},
        h("th", { scope: "col" }, "Quarter"),
        h("th", { scope: "col" }, "KPI"),
        h("th", { scope: "col", class: "num" }, "Target"))),
      h("tbody", {}, targets.map((t) => h("tr", {},
        h("td", {}, h("a", { href: `#/team/${id}?quarter=${t.year}-Q${t.quarter}` }, quarterLabel(`${t.year}-Q${t.quarter}`))),
        h("td", {}, t.kpi_name),
        h("td", { class: "num" }, String(t.target_value))))))));
  }

  renderEditor();
  renderAddKpi();
  renderHistory();
}
