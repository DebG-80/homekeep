// The household and history surface (BRD §11.2; TDD §8.6; plan P4-3).
//
// Appliances with how sure HomeKeep is of each fact ("not provided" is a label, never an
// error), open problems, service requests, and each appliance's history with who recorded what
// and when. The owner manages helpers' grants here; helpers see only their own. Judge households
// can reset their demo data.

import { Api, ApiError } from "../api";
import { h } from "../dom";

interface Field {
  value: string | null;
  status: string;
}
interface Appliance {
  appliance_id: string;
  nickname: string;
  category: string;
  room: string | null;
  fields: Record<string, Field>;
}
interface Household {
  appliances: Appliance[];
  open_issues: { issue_id: string; appliance_id: string; summary: string; status: string }[];
  service_requests: { request_id: string; state: string; appliance_id: string }[];
  storage_consent: string | null;
  sharing_consent: string | null;
  role: string | null;
  grants: string[];
  resettable: boolean;
}
interface Member {
  member_ref: string;
  display_name: string;
  role: string;
  grants: string[];
  status: string;
  is_you: boolean;
}
interface HistoryEntry {
  date_words: string;
  action: string;
  actor_role: string;
}

const CATEGORY: Record<string, string> = {
  AC: "Air conditioner",
  REFRIGERATOR: "Fridge",
  TELEVISION: "TV",
};
const CONFIDENCE: Record<string, string> = {
  VERIFIED: "checked against the manual",
  USER_REPORTED: "as you told us",
  UNKNOWN: "not provided",
};
const REQUEST_STATE: Record<string, string> = {
  DRAFT: "not sent yet",
  SUBMISSION_PENDING: "pending",
  REQUESTED: "pending",
  CONFIRMED: "demo visit confirmed",
  CHANGE_PENDING: "change pending",
  CANCEL_PENDING: "call-off pending",
  IN_PROGRESS: "visit in progress",
  COMPLETED: "visit done",
  CANCELLED: "called off",
  REJECTED: "not accepted",
  FAILED: "didn't go through",
};
const GRANTS: ReadonlyArray<[string, string]> = [
  ["view", "See the household"],
  ["edit", "Add and change details"],
  ["book", "Arrange demo visits"],
  ["updates", "Get updates"],
];

function words(action: string): string {
  return action.toLowerCase().replaceAll("_", " ");
}

function who(role: string): string {
  if (role.includes("technician")) return "Technician";
  if (role.includes("coordinator")) return "Service desk";
  if (role === "OWNER") return "Owner";
  if (role === "HELPER") return "Helper";
  if (role === "SYSTEM") return "HomeKeep";
  return role.charAt(0) + role.slice(1).toLowerCase();
}

export function householdView(api: Api, onReset: () => void): HTMLElement {
  const root = h("section", { class: "household", "aria-labelledby": "household-heading" });
  const status = h("p", { id: "household-status", class: "notice", "aria-live": "polite" });

  async function showHistory(appliance: Appliance, target: HTMLElement): Promise<void> {
    target.replaceChildren(h("p", {}, "Loading…"));
    try {
      const history = await api.request<{ entries: HistoryEntry[] }>(
        "GET",
        `/api/appliances/${appliance.appliance_id}/history`,
      );
      const list = h("ol", { class: "history" });
      for (const entry of history.entries) {
        list.append(h("li", {}, h("strong", {}, `${entry.date_words}: `), `${words(entry.action)} (${who(entry.actor_role)})`));
      }
      target.replaceChildren(history.entries.length ? list : h("p", {}, "Nothing recorded yet."));
    } catch {
      target.replaceChildren(h("p", {}, "The history could not be loaded."));
    }
  }

  function applianceRows(household: Household): HTMLElement {
    const body = h("tbody");
    for (const appliance of household.appliances) {
      const model = appliance.fields["model"] ?? { value: null, status: "UNKNOWN" };
      const historyCell = h("td", {});
      const historyRow = h("tr", { class: "history-row" }, h("td", { colspan: "5" }, historyCell));
      historyRow.hidden = true;
      body.append(
        h(
          "tr",
          {},
          h("th", { scope: "row" }, appliance.nickname),
          h("td", {}, CATEGORY[appliance.category] ?? appliance.category),
          h("td", {}, appliance.room ?? "not provided"),
          h("td", {}, `${model.value ?? "not provided"} (${CONFIDENCE[model.status] ?? model.status})`),
          h(
            "td",
            {},
            h(
              "button",
              {
                type: "button",
                class: "history-button",
                "data-appliance": appliance.appliance_id,
                onclick: () => {
                  historyRow.hidden = false;
                  void showHistory(appliance, historyCell);
                },
              },
              `History of ${appliance.nickname}`,
            ),
          ),
        ),
        historyRow,
      );
    }
    return h(
      "table",
      { class: "appliances" },
      h("caption", {}, "Your appliances"),
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", { scope: "col" }, "Name"),
          h("th", { scope: "col" }, "Type"),
          h("th", { scope: "col" }, "Room"),
          h("th", { scope: "col" }, "Model"),
          h("th", { scope: "col" }, "History"),
        ),
      ),
      body,
    );
  }

  function memberCard(member: Member, owner: boolean): HTMLElement {
    const card = h("li", { class: "member", "data-member": member.display_name });
    card.append(
      h("p", {}, h("strong", {}, member.display_name), ` — ${who(member.role)}, ${member.status.toLowerCase()}${member.is_you ? " (you)" : ""}`),
    );
    const editable = owner && member.role === "HELPER" && member.status === "ACTIVE";
    const boxes = h("fieldset", { class: "grants" }, h("legend", {}, `What ${member.display_name} may do`));
    for (const [grant, label] of GRANTS) {
      const box = h("input", { type: "checkbox", name: grant, id: `${member.member_ref}-${grant}` });
      box.checked = member.grants.includes(grant);
      box.disabled = !editable || grant === "view";
      boxes.append(h("label", { for: box.id }, box, ` ${label}`));
    }
    card.append(boxes);
    if (editable) {
      card.append(
        h(
          "button",
          {
            type: "button",
            class: "save-grants",
            onclick: async () => {
              const grants = [...boxes.querySelectorAll<HTMLInputElement>("input:checked")].map((b) => b.name);
              try {
                await api.request("POST", `/api/household/members/${member.member_ref}/grants`, { grants });
                status.textContent = `Saved what ${member.display_name} may do.`;
              } catch {
                status.textContent = "That change could not be saved.";
              }
            },
          },
          "Save",
        ),
        h(
          "button",
          {
            type: "button",
            class: "revoke danger",
            onclick: async () => {
              if (!confirm(`Remove ${member.display_name}'s access to this household?`)) return;
              try {
                await api.request("POST", `/api/household/members/${member.member_ref}/revoke`);
                status.textContent = `${member.display_name} no longer has access.`;
                await load();
              } catch {
                status.textContent = "Access could not be removed.";
              }
            },
          },
          `Remove ${member.display_name}'s access`,
        ),
      );
    }
    return card;
  }

  async function load(): Promise<void> {
    let household: Household;
    let members: Member[] = [];
    try {
      household = await api.request<Household>("GET", "/api/household");
      members = (await api.request<{ members: Member[] }>("GET", "/api/household/members")).members;
    } catch (error) {
      const denied = error instanceof ApiError && (error.status === 401 || error.status === 403);
      root.replaceChildren(
        h("h1", { id: "household-heading" }, "Your household"),
        h("p", { class: "notice" }, denied ? "You no longer have access to this household." : "The household could not be loaded."),
      );
      return;
    }
    const owner = household.role === "OWNER";
    const issues = h("ul", { class: "issues" });
    for (const issue of household.open_issues) {
      const appliance = household.appliances.find((a) => a.appliance_id === issue.appliance_id);
      issues.append(h("li", {}, `${appliance?.nickname ?? "Appliance"}: ${issue.summary} (${words(issue.status)})`));
    }
    const requests = h("ul", { class: "requests" });
    for (const request of household.service_requests) {
      const appliance = household.appliances.find((a) => a.appliance_id === request.appliance_id);
      requests.append(h("li", {}, `${appliance?.nickname ?? "Appliance"}: ${REQUEST_STATE[request.state] ?? words(request.state)}`));
    }
    const memberList = h("ul", { class: "members" });
    for (const member of members) memberList.append(memberCard(member, owner));
    root.replaceChildren(
      h("h1", { id: "household-heading" }, "Your household"),
      status,
      household.appliances.length ? applianceRows(household) : h("p", {}, "No appliances yet. Tell HomeKeep about one on the Talk page."),
      h("h2", {}, "Open problems"),
      household.open_issues.length ? issues : h("p", {}, "No open problems."),
      h("h2", {}, "Demo visits"),
      household.service_requests.length ? requests : h("p", {}, "No visits arranged."),
      h("h2", {}, owner ? "People who can use this household" : "Your access"),
      memberList,
      household.resettable && owner
        ? h(
            "p",
            {},
            h(
              "button",
              {
                id: "reset",
                type: "button",
                class: "danger",
                onclick: async () => {
                  if (!confirm("Reset your demo data? Everything you added will be removed.")) return;
                  try {
                    await api.request("POST", "/api/household/reset");
                    status.textContent = "Your demo data has been reset.";
                    onReset();
                    await load();
                  } catch {
                    status.textContent = "The reset did not complete. Please try again.";
                  }
                },
              },
              "Reset my demo data",
            ),
          )
        : "",
    );
  }

  root.append(h("h1", { id: "household-heading" }, "Your household"), h("p", {}, "Loading…"));
  void load();
  return root;
}
