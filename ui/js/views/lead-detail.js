import { api, settle, toApiError } from "../api.js";
import {
  banner, bandTag, clear, emptyState, errorBanner, h, loading, memberLookup, memberName, pageFrame, setBusy,
  STAGE_LABELS, STAGES, stageTag, timeEl,
} from "../dom.js";

const STAGE_POINTS = { none: 0, showing_booked: 1, showing_performed: 2, closed: 4 };

export async function render(ctx) {
  const id = Number(ctx.params[0]);
  ctx.setTitle(`Lead #${id}`);
  const page = pageFrame({ title: `Lead #${id}`, intro: null });
  page.el.prepend(h("a", { class: "back-link", href: "#/leads" }, "← Leads"));
  ctx.root.append(page.el);
  page.body.append(loading("Loading lead…"));

  const [leadResult] = await settle([api.lead(id)]);
  if (!ctx.isCurrent()) return;
  clear(page.body);

  if (!leadResult.ok) {
    const notFound = leadResult.error.kind === "not_found";
    page.banners.append(notFound
      ? banner("error", "Lead not found", `There is no lead with id ${id}.`)
      : errorBanner(leadResult.error, "This lead could not be loaded", {
        retry: ctx.refresh,
        consequence: leadResult.error.kind === "unavailable" ? "Leads are stored in the routing service." : null,
      }));
    page.body.append(emptyState(notFound ? "Nothing to show" : "Lead details unavailable", null,
      h("a", { class: "btn btn-quiet", href: "#/leads" }, "Back to Leads")));
    return;
  }

  let lead = leadResult.value;
  let lookup = null;
  if (lead.assigned_member_id !== null) {
    const [memberResult] = await settle([api.member(lead.assigned_member_id)]);
    if (!ctx.isCurrent()) return;
    if (memberResult.ok) lookup = memberLookup([memberResult.value]);
    else if (memberResult.error.kind !== "not_found") {
      page.banners.append(banner("notice", "Broker name unavailable",
        `${memberResult.error.message} The broker is shown by id until it is back.`, { retry: ctx.refresh }));
    } else lookup = new Map();
  }

  page.el.querySelector(".page-heading").append(h("p", { class: "page-intro" }, "From ", h("span", { class: "capitalise" }, lead.source)));

  const info = h("section", { class: "card section-card", "aria-labelledby": "info-heading" });
  const history = h("section", { class: "card section-card", "aria-labelledby": "history-heading" });
  page.body.append(h("div", { class: "detail-grid" }, info, history));

  function furthest() {
    return lead.outcomes.reduce((best, o) => (STAGE_POINTS[o.outcome] > STAGE_POINTS[best] ? o.outcome : best), "none");
  }

  function renderInfo() {
    clear(info,
      h("h2", { class: "section-title", id: "info-heading" }, "Lead"),
      h("dl", { class: "facts" },
        fact("Band", bandTag(lead.band)),
        fact("Score", String(lead.score)),
        fact("Source", h("span", { class: "capitalise" }, lead.source)),
        fact("Furthest stage", stageTag(furthest())),
        fact("Broker", memberName(lookup, lead.assigned_member_id)),
        fact("Assigned", lead.assigned_at ? timeEl(lead.assigned_at, true) : h("span", { class: "muted" }, "Not assigned")),
        fact("Created", timeEl(lead.created_at, true))));
  }

  function renderHistory(message) {
    const status = h("div", { "aria-live": "polite" }, message || null);
    const select = h("select", { class: "input input-select", id: "outcome-stage", name: "stage" },
      STAGES.map((s) => h("option", { value: s, selected: s === nextStage() }, STAGE_LABELS[s])));
    const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Record outcome");
    const form = h("form", { class: "form-inline", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "outcome-stage" }, "New outcome"), select),
      submit);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(status);
      setBusy(submit, true, "Saving…");
      try {
        const result = await api.addOutcome(id, select.value);
        lead = { ...lead, outcomes: result.outcomes };
        renderInfo();
        renderHistory(banner("success", "Outcome recorded", `${STAGE_LABELS[select.value]} was added to the history.`));
        history.querySelector("select").focus();
      } catch (err) {
        status.append(errorBanner(toApiError(err), "The outcome was not recorded"));
        setBusy(submit, false);
      }
    });

    clear(history,
      h("h2", { class: "section-title", id: "history-heading" }, "Outcome history"),
      lead.outcomes.length === 0
        ? h("p", { class: "muted history-empty" }, "No outcome recorded yet.")
        : h("ol", { class: "timeline" }, lead.outcomes.map((o) => h("li", { class: "timeline-item" },
          h("span", { class: `timeline-dot stage-dot-${o.outcome}`, "aria-hidden": "true" }),
          h("div", {}, h("p", { class: "timeline-title" }, STAGE_LABELS[o.outcome] || o.outcome),
            h("p", { class: "cell-sub" }, timeEl(o.recorded_at, true)))))),
      status,
      form);
  }

  function nextStage() {
    const index = STAGES.indexOf(furthest());
    return STAGES[Math.min(index + 1, STAGES.length - 1)];
  }

  renderInfo();
  renderHistory();
}

function fact(label, value) {
  return h("div", { class: "fact" }, h("dt", {}, label), h("dd", {}, value));
}
