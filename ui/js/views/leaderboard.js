import { api, settle } from "../api.js";
import {
  banner, clear, emptyState, errorBanner, fmtScore, h, loading, memberLookup, memberName, pageFrame, tableWrap,
} from "../dom.js";

export async function render(ctx) {
  ctx.setTitle("Leaderboard");
  const page = pageFrame({
    title: "Leaderboard",
    intro: "Brokers ranked by how their leads turned out compared with what each lead’s band predicted, weighted toward the last 30 days. 0 means exactly as expected.",
  });
  ctx.root.append(page.el);
  page.body.append(loading("Loading the leaderboard…"));

  const [boardResult, membersResult] = await settle([api.leaderboard(), api.members()]);
  if (!ctx.isCurrent()) return;
  clear(page.body);

  if (!boardResult.ok) {
    page.banners.append(errorBanner(boardResult.error, "The leaderboard could not be loaded", {
      retry: ctx.refresh,
      consequence: boardResult.error.kind === "unavailable" ? "Scores are calculated by the routing service." : null,
    }));
    page.body.append(emptyState("No ranking", "The ranking appears here once the routing service answers."));
    return;
  }

  const { brokers, notice } = boardResult.value;
  if (notice || !membersResult.ok) {
    const parts = [];
    if (notice) parts.push(notice);
    if (!membersResult.ok) parts.push("Broker names cannot be loaded either, so brokers are shown by id.");
    page.banners.append(banner("notice", notice ? "Showing a fallback ranking" : "Broker names unavailable", parts.join(" "), { retry: ctx.refresh }));
  }

  if (brokers.length === 0) {
    page.body.append(emptyState("No brokers to rank",
      "Brokers appear once there is an active member with the Broker role.",
      h("a", { class: "btn btn-primary", href: "#/team?add=1" }, "Add a broker")));
    return;
  }

  const lookup = memberLookup(membersResult.ok ? membersResult.value : null);
  page.body.append(tableWrap(h("table", { class: "table table-board" },
    h("caption", { class: "visually-hidden" }, "Broker ranking"),
    h("thead", {}, h("tr", {},
      h("th", { scope: "col", class: "num col-rank" }, "Rank"),
      h("th", { scope: "col" }, "Broker"),
      h("th", { scope: "col", class: "num" }, "Score"),
      h("th", { scope: "col", class: "num" }, "Open leads"))),
    h("tbody", {}, brokers.map((b, i) => h("tr", { class: i === 0 ? "row-lead" : null },
      h("td", { class: "num col-rank" }, h("span", { class: "rank" }, String(i + 1))),
      h("td", {}, memberName(lookup, b.member_id)),
      h("td", { class: "num" }, h("span", { class: "score " + (b.score > 0 ? "score-up" : b.score < 0 ? "score-down" : "") }, fmtScore(b.score))),
      h("td", { class: "num" }, String(b.open_leads))))))));
  page.body.append(h("p", { class: "table-foot" }, "Open leads are assigned leads that have not been closed. Ties are broken by fewer open leads."));
}

