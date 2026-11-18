import { api, health, settle, toApiError } from "../api.js";
import {
  banner, bandForScore, bandTag, clear, errorBanner, h, pageFrame, setBusy, showFieldErrors,
} from "../dom.js";

const SOURCES = ["website", "referral", "boat show", "phone"];
const BAND_RULES = {
  hot: "Goes to the active broker with the best score.",
  warm: "Goes to the active broker who received a lead least recently.",
  cold: "Goes to the active broker who received a lead least recently.",
};

export async function render(ctx) {
  ctx.setTitle("Add lead");
  const page = pageFrame({
    title: "Add lead",
    intro: "Save a new lead. It is scored into a band and assigned to a broker straight away.",
  });
  ctx.root.append(page.el);

  const errorSlot = h("div", { "aria-live": "polite" });
  const source = h("input", {
    class: "input", id: "lead-source", name: "source", list: "lead-sources", autocomplete: "off",
    maxlength: "100", required: true, placeholder: "e.g. boat show…",
  });
  const score = h("input", {
    class: "input input-number", id: "lead-score", name: "score", type: "number", min: "0", max: "100",
    step: "1", inputmode: "numeric", autocomplete: "off", required: true, placeholder: "0–100", "aria-describedby": "score-help band-preview",
  });
  const preview = h("div", { class: "band-preview", id: "band-preview", "aria-live": "polite" });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Save and assign");

  const updatePreview = () => {
    const value = Number(score.value);
    if (score.value === "" || !Number.isInteger(value) || value < 0 || value > 100) {
      clear(preview, h("span", { class: "muted" }, "Enter a score to see its band."));
      return;
    }
    const band = bandForScore(value);
    clear(preview, bandTag(band), h("span", {}, ` ${BAND_RULES[band]}`));
  };
  // warn before the user fills the form, not only after a failed save
  health("routing").then((status) => {
    if (!ctx.isCurrent() || status.state === "up") return;
    page.banners.append(banner("notice", "The routing service is not available",
      "New leads cannot be saved until it is back. You can fill in the form and save once it returns.",
      { retry: ctx.refresh }));
  });
  score.addEventListener("input", updatePreview);
  updatePreview();

  const form = h("form", { class: "card form-card form-narrow", novalidate: true },
    errorSlot,
    h("div", { class: "field" },
      h("label", { for: "lead-source" }, "Source"),
      source,
      h("datalist", { id: "lead-sources" }, SOURCES.map((s) => h("option", { value: s })))),
    h("div", { class: "field" },
      h("label", { for: "lead-score" }, "Lead score"),
      score,
      h("p", { class: "help", id: "score-help" }, "70 or more is hot, 40 to 69 is warm, below 40 is cold.")),
    preview,
    h("div", { class: "form-actions" }, submit));

  const resultSlot = h("div", { class: "result-slot" });
  const rules = h("aside", { class: "card rules-card", "aria-labelledby": "rules-heading" },
    h("h2", { class: "section-title", id: "rules-heading" }, "How a lead is assigned"),
    h("dl", { class: "rules" },
      ["hot", "warm", "cold"].map((band) => h("div", { class: "rule" },
        h("dt", {}, bandTag(band)),
        h("dd", {}, BAND_RULES[band])))),
    h("p", { class: "help" }, "Ties go to the broker with fewer open leads. Only active members with the Broker role receive leads; if the KPI service is down, the lead is saved unassigned."));
  page.body.append(resultSlot, h("div", { class: "lead-new-grid" }, form, rules));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errorSlot);
    const problems = [];
    const value = Number(score.value);
    if (!source.value.trim()) problems.push([source, "Enter where the lead came from."]);
    if (score.value === "" || !Number.isInteger(value) || value < 0 || value > 100) problems.push([score, "Use a whole number from 0 to 100."]);
    if (showFieldErrors(form, problems)) return;

    setBusy(submit, true, "Saving…");
    let created;
    try {
      created = await api.addLead({ source: source.value.trim(), score: value });
    } catch (err) {
      const error = toApiError(err);
      errorSlot.append(errorBanner(error, "The lead was not saved", {
        consequence: error.kind === "unavailable" ? "Leads are stored in the routing service. Your entry is still in the form, so try again when it is back." : null,
      }));
      setBusy(submit, false);
      return;
    }
    setBusy(submit, false);
    await showResult(created);
    form.reset();
    updatePreview();
  });

  async function showResult({ lead, band, assignment, notice }) {
    let brokerLine;
    if (lead.assigned_member_id !== null && lead.assigned_member_id !== undefined) {
      const [memberResult] = await settle([api.member(lead.assigned_member_id)]);
      brokerLine = memberResult.ok
        ? h("p", { class: "result-main" }, "Assigned to ", h("a", { href: `#/team/${memberResult.value.id}` }, memberResult.value.name))
        : h("p", { class: "result-main" }, `Assigned to broker #${lead.assigned_member_id}`,
          h("span", { class: "result-sub" }, " (name unavailable: the KPI service did not answer)"));
    }
    const card = h("section", { class: "card result-card", "aria-labelledby": "result-heading", tabindex: "-1" },
      h("h2", { class: "section-title", id: "result-heading" }, `Lead #${lead.id} saved`),
      h("p", { class: "result-meta" }, bandTag(band), ` lead from ${lead.source}, score ${lead.score}.`),
      assignment === "assigned"
        ? brokerLine
        : banner("notice", "Saved without a broker",
          `${notice || "No broker could be chosen."} The lead is not lost: it stays in the list unassigned.`),
      h("div", { class: "form-actions" },
        h("a", { class: "btn btn-quiet", href: `#/leads/${lead.id}` }, "Open lead"),
        h("a", { class: "btn btn-quiet", href: "#/leads" }, "All leads")));
    clear(resultSlot, card);
    card.focus();
  }
}
