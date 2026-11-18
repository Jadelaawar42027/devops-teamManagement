import { api, settle } from "../api.js";
import {
  BAND_LABELS, banner, bandTag, clear, emptyState, errorBanner, h, loading, memberLookup, memberName,
  pageFrame, stageTag, tableWrap, timeEl,
} from "../dom.js";

const BANDS = ["all", "hot", "warm", "cold"];

export async function render(ctx) {
  const band = BANDS.includes(ctx.query.get("band")) ? ctx.query.get("band") : "all";
  ctx.setTitle("Leads");
  const page = pageFrame({
    title: "Leads",
    intro: "Every incoming lead, its temperature, how far it got, and which broker has it.",
    actions: h("a", { class: "btn btn-primary", href: "#/leads/new" }, "Add lead"),
  });
  ctx.root.append(page.el);
  page.body.append(loading("Loading leads…"));

  // names come from the KPI service; the list itself from routing. Either may be down.
  const [leadsResult, membersResult] = await settle([api.leads(), api.members()]);
  if (!ctx.isCurrent()) return;
  clear(page.body);

  if (!leadsResult.ok) {
    page.banners.append(errorBanner(leadsResult.error, "Leads could not be loaded", {
      retry: ctx.refresh,
      consequence: leadsResult.error.kind === "unavailable" ? "Leads are stored in the routing service." : null,
    }));
    page.body.append(emptyState("No lead list", "Leads appear here once the routing service answers. New leads cannot be added until then either."));
    return;
  }
  if (!membersResult.ok) {
    page.banners.append(banner("notice", "Broker names unavailable",
      `${membersResult.error.message} Brokers are shown by their id (for example #3) until it is back.`, { retry: ctx.refresh }));
  }

  const lookup = memberLookup(membersResult.ok ? membersResult.value : null);
  const leads = leadsResult.value;
  const counts = { all: leads.length, hot: 0, warm: 0, cold: 0 };
  leads.forEach((l) => { counts[l.band] += 1; });
  const shown = band === "all" ? leads : leads.filter((l) => l.band === band);

  page.body.append(h("nav", { class: "segmented", "aria-label": "Filter by band" },
    BANDS.map((b) => h("a", {
      href: b === "all" ? "#/leads" : `#/leads?band=${b}`,
      class: "segment" + (b === band ? " active" : ""),
      "aria-current": b === band ? "true" : null,
    }, b === "all" ? "All" : BAND_LABELS[b], h("span", { class: "segment-count" }, String(counts[b]))))));

  if (shown.length === 0) {
    page.body.append(leads.length === 0
      ? emptyState("No leads yet", "Add the first lead and it will be assigned to a broker automatically.",
        h("a", { class: "btn btn-primary", href: "#/leads/new" }, "Add lead"))
      : emptyState(`No ${BAND_LABELS[band].toLowerCase()} leads`, "Try another band.", h("a", { class: "btn btn-quiet", href: "#/leads" }, "Show all leads")));
    return;
  }

  page.body.append(tableWrap(h("table", { class: "table table-leads" },
    h("caption", { class: "visually-hidden" }, band === "all" ? "All leads" : `${BAND_LABELS[band]} leads`),
    h("thead", {}, h("tr", {},
      h("th", { scope: "col", class: "num" }, "Lead"),
      h("th", { scope: "col" }, "Source"),
      h("th", { scope: "col" }, "Band"),
      h("th", { scope: "col", class: "num" }, "Score"),
      h("th", { scope: "col" }, "Furthest stage"),
      h("th", { scope: "col" }, "Broker"),
      h("th", { scope: "col" }, "Created"))),
    h("tbody", {}, shown.map((lead) => h("tr", {},
      h("td", { class: "num" }, h("a", { class: "strong-link", href: `#/leads/${lead.id}` }, `#${lead.id}`)),
      h("td", { class: "cell-source" }, h("a", { href: `#/leads/${lead.id}` }, lead.source)),
      h("td", {}, bandTag(lead.band)),
      h("td", { class: "num" }, String(lead.score)),
      h("td", {}, stageTag(lead.stage)),
      h("td", {}, memberName(lookup, lead.assigned_member_id)),
      h("td", { class: "nowrap" }, timeEl(lead.created_at))))))));
  page.body.append(h("p", { class: "table-foot" }, `Showing ${shown.length} of ${leads.length} leads.`));
}
