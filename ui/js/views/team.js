import { api, settle, toApiError } from "../api.js";
import {
  banner, clear, emptyState, errorBanner, h, loading, pageFrame, setBusy, showFieldErrors, statusTag, tableWrap,
} from "../dom.js";

export async function render(ctx) {
  ctx.setTitle("Team");
  const addButton = h("button", { class: "btn btn-primary", type: "button", "aria-expanded": "false", "aria-controls": "add-member" }, "Add member");
  const page = pageFrame({
    title: "Team",
    intro: "Everyone on the team, their role, and whether they can still receive leads.",
    actions: addButton,
  });
  ctx.root.append(page.el);
  const formSlot = h("div", { id: "add-member", hidden: true });
  const tableSlot = h("div", {});
  page.body.append(formSlot, tableSlot);
  tableSlot.append(loading("Loading members…"));

  const [membersResult, rolesResult] = await settle([api.members(), api.roles()]);
  if (!ctx.isCurrent()) return;

  if (!membersResult.ok) {
    page.banners.append(errorBanner(membersResult.error, "Members could not be loaded", {
      retry: ctx.refresh,
      consequence: membersResult.error.kind === "unavailable" ? "Members are stored in the KPI service." : null,
    }));
    addButton.disabled = true;
    clear(tableSlot, emptyState("No member list", "The team appears here once the KPI service answers."));
    return;
  }

  let roles = rolesResult.ok ? rolesResult.value : null;
  const members = sortMembers(membersResult.value);
  page.el.querySelector(".page-intro").textContent = countLine(members);

  const toggleForm = (open) => {
    formSlot.hidden = !open;
    addButton.setAttribute("aria-expanded", String(open));
    addButton.textContent = open ? "Close form" : "Add member";
    if (open) formSlot.querySelector("input")?.focus();
  };
  addButton.addEventListener("click", () => toggleForm(formSlot.hidden));

  formSlot.append(addMemberForm({
    roles,
    rolesError: rolesResult.ok ? null : rolesResult.error,
    onCancel: () => toggleForm(false),
    onAdded: (member) => {
      page.banners.replaceChildren(banner("success", `${member.name} was added`, `Role: ${member.role_name}.`));
      members.push(member);
      renderTable();
      page.el.querySelector(".page-intro").textContent = countLine(members);
    },
    onRolesChanged: (next) => { roles = next; },
  }));
  if (ctx.query.get("add") === "1") toggleForm(true);

  function renderTable() {
    sortMembers(members);
    if (members.length === 0) {
      clear(tableSlot, emptyState("No team members yet", "Add a member with the Broker role so leads can be assigned.",
        h("button", { class: "btn btn-primary", type: "button", onclick: () => toggleForm(true) }, "Add the first member")));
      return;
    }
    clear(tableSlot, tableWrap(h("table", { class: "table" },
      h("caption", { class: "visually-hidden" }, "Team members"),
      h("thead", {}, h("tr", {},
        h("th", { scope: "col" }, "Name"),
        h("th", { scope: "col" }, "Role"),
        h("th", { scope: "col" }, "Status"),
        h("th", { scope: "col", class: "col-actions" }, h("span", { class: "visually-hidden" }, "Actions")))),
      h("tbody", {}, members.map((m) => memberRow(m))))));
  }

  function memberRow(m) {
    const actions = h("td", { class: "col-actions" });
    const showDefault = () => clear(actions,
      h("a", { class: "btn btn-quiet btn-small", href: `#/team/${m.id}` }, "KPI targets"),
      m.active ? h("button", { class: "btn btn-quiet btn-small btn-danger-text", type: "button", onclick: showConfirm }, "Deactivate") : null);
    function showConfirm() {
      const confirmBtn = h("button", { class: "btn btn-danger btn-small", type: "button" }, "Confirm deactivate");
      const cancelBtn = h("button", { class: "btn btn-quiet btn-small", type: "button", onclick: showDefault }, "Cancel");
      confirmBtn.addEventListener("click", async () => {
        setBusy(confirmBtn, true, "Deactivating…");
        cancelBtn.disabled = true;
        try {
          const updated = await api.deactivate(m.id);
          Object.assign(m, updated);
          page.banners.replaceChildren(banner("success", `${m.name} was deactivated`, "They keep their history but no longer receive new leads."));
          renderTable();
          page.el.querySelector(".page-intro").textContent = countLine(members);
        } catch (err) {
          page.banners.replaceChildren(errorBanner(toApiError(err), `${m.name} could not be deactivated`));
          showDefault();
        }
      });
      clear(actions, h("span", { class: "confirm-text" }, "Stop new leads?"), confirmBtn, cancelBtn);
      confirmBtn.focus();
    }
    showDefault();
    return h("tr", { class: m.active ? null : "row-muted" },
      h("td", {}, h("a", { class: "strong-link", href: `#/team/${m.id}` }, m.name), h("div", { class: "cell-sub" }, m.email)),
      h("td", {}, m.role_name),
      h("td", {}, statusTag(m.active)),
      actions);
  }

  renderTable();
}

function sortMembers(members) {
  return members.sort((a, b) => (b.active - a.active) || a.name.localeCompare(b.name));
}

function countLine(members) {
  const active = members.filter((m) => m.active);
  const brokers = active.filter((m) => m.role_name.toLowerCase() === "broker");
  return `${members.length} members · ${active.length} active · ${brokers.length} active brokers can receive leads.`;
}

function addMemberForm({ roles, rolesError, onCancel, onAdded, onRolesChanged }) {
  const errorSlot = h("div", { "aria-live": "polite" });
  const name = h("input", { class: "input", id: "m-name", name: "name", autocomplete: "off", required: true, maxlength: "200" });
  const email = h("input", { class: "input", id: "m-email", name: "email", type: "email", autocomplete: "off", spellcheck: "false", required: true, maxlength: "255" });
  const role = h("select", { class: "input input-select", id: "m-role", name: "role_id", required: true });
  const newRole = h("input", { class: "input", id: "m-new-role", name: "new_role", autocomplete: "off", maxlength: "100", placeholder: "e.g. Setter…" });
  const addRoleBtn = h("button", { class: "btn btn-quiet", type: "button" }, "Add role");
  const roleRow = h("div", { class: "inline-add", hidden: true },
    h("label", { class: "visually-hidden", for: "m-new-role" }, "New role name"), newRole, addRoleBtn);
  const showRoleRow = h("button", { class: "link-button", type: "button", onclick: () => { roleRow.hidden = false; newRole.focus(); } }, "New role…");
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, "Add member");

  function fillRoles(selectedId) {
    clear(role, h("option", { value: "" }, roles && roles.length ? "Choose a role…" : "No roles yet"),
      (roles || []).map((r) => h("option", { value: String(r.id), selected: r.id === selectedId }, r.name)));
  }
  fillRoles();
  if (rolesError) {
    role.disabled = true;
    submit.disabled = true;
    errorSlot.append(errorBanner(rolesError, "Roles could not be loaded", { consequence: "A member needs a role, so adding is disabled for now." }));
  }

  addRoleBtn.addEventListener("click", async () => {
    clear(errorSlot);
    const value = newRole.value.trim();
    if (!value) { newRole.focus(); return; }
    setBusy(addRoleBtn, true, "Adding…");
    try {
      const created = await api.addRole(value);
      roles = [...(roles || []), created].sort((a, b) => a.name.localeCompare(b.name));
      onRolesChanged(roles);
      fillRoles(created.id);
      newRole.value = "";
      roleRow.hidden = true;
    } catch (err) {
      errorSlot.append(errorBanner(toApiError(err), "The role could not be added"));
    } finally {
      setBusy(addRoleBtn, false);
    }
  });

  const form = h("form", { class: "card form-card", novalidate: true },
    h("h2", { class: "section-title" }, "Add a team member"),
    errorSlot,
    h("div", { class: "form-grid" },
      field("m-name", "Full name", name),
      field("m-email", "Email", email),
      h("div", { class: "field" },
        h("div", { class: "label-row" }, h("label", { for: "m-role" }, "Role"), showRoleRow),
        role, roleRow)),
    h("div", { class: "form-actions" },
      submit,
      h("button", { class: "btn btn-quiet", type: "button", onclick: onCancel }, "Cancel")));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errorSlot);
    const problems = [];
    if (!name.value.trim()) problems.push([name, "Enter the member’s full name."]);
    if (!/^\S+@\S+\.\S+$/.test(email.value.trim())) problems.push([email, "Enter an email address like name@example.com."]);
    if (!role.value) problems.push([role, "Choose a role, or add one with “New role…”."]);
    if (showFieldErrors(form, problems)) return;
    setBusy(submit, true, "Adding…");
    try {
      const created = await api.addMember({ name: name.value.trim(), email: email.value.trim(), role_id: Number(role.value) });
      form.reset();
      fillRoles();
      onAdded(created);
      name.focus();
    } catch (err) {
      errorSlot.append(errorBanner(toApiError(err), "The member could not be added"));
    } finally {
      setBusy(submit, false);
    }
  });
  return form;
}

function field(id, label, input) {
  return h("div", { class: "field" }, h("label", { for: id }, label), input);
}
