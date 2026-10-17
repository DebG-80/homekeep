// The service desk surface (BRD §11.3; TDD §4.10; plan Slice 3 P3-2).
//
// The queue (a technician's own jobs, or every case for a coordinator), with pending
// reconciliation shown apart from confirmed visits; the case view with personal fields masked
// unless the role needs them; visit and provider events; and, for coordinators, assignment,
// manual review and safety clearing. Every action is checked again by the server.

import { Api } from "../api";
import { h, newId } from "../dom";

interface Appointment {
  date_words: string;
  window_words: string;
}
interface CaseSummary {
  case_id: string;
  state: string;
  pending: boolean;
  issue_summary: string;
  appliance: string | null;
  safety_flag: boolean;
  appointment: Appointment | null;
  fee: { amount_paise: number | null; status: string };
  exception: string | null;
}
interface CaseView extends CaseSummary {
  version: number;
  checks: { step_id: string; result: string }[];
  issue_status: string;
  address: string | null;
  contact: string | null;
  work_reports: { summary: string; at: string; actor_role: string }[];
}

function fee(summary: CaseSummary): string {
  if (summary.fee.amount_paise === null) return "fee not known yet";
  return `about ${summary.fee.amount_paise / 100} rupees (${summary.fee.status.toLowerCase()})`;
}

function when(summary: CaseSummary): string {
  return summary.appointment
    ? `${summary.appointment.date_words}, ${summary.appointment.window_words}`
    : "no time fixed";
}

export function staffView(api: Api, groups: string[]): HTMLElement {
  const coordinator = groups.includes("coordinator");
  const root = h("section", { class: "staff", "aria-labelledby": "staff-heading" });
  const status = h("p", { id: "staff-status", class: "notice", "aria-live": "polite" });
  const detail = h("div", { id: "case-detail" });

  async function act(path: string, body: unknown, done: string): Promise<boolean> {
    try {
      await api.request("POST", path, body);
      status.textContent = done;
      return true;
    } catch (error) {
      status.textContent = `Not done: ${error instanceof Error ? error.message : "error"}.`;
      return false;
    }
  }

  async function openCase(caseId: string): Promise<void> {
    let view: CaseView;
    try {
      view = await api.request<CaseView>("GET", `/api/staff/cases/${caseId}`);
    } catch {
      status.textContent = "That case could not be opened. It may have moved to someone else.";
      return;
    }
    const summaryBox = h("textarea", { id: "work-summary", rows: "3", "aria-label": "Work summary" });
    const post = async (type: string): Promise<void> => {
      const ok = await act(
        `/api/staff/cases/${caseId}/events`,
        { event_id: newId("evt"), type, expected_version: view.version, summary: summaryBox.value || null },
        `${type.toLowerCase().replaceAll("_", " ")} recorded.`,
      );
      if (ok) await refresh(caseId);
    };
    const eventButton = (type: string, label: string) =>
      h("button", { type: "button", "data-event": type, onclick: () => void post(type) }, label);
    const checks = h("ul", {});
    for (const check of view.checks) checks.append(h("li", {}, `${check.step_id}: ${check.result.toLowerCase()}`));
    const reports = h("ul", {});
    for (const report of view.work_reports) reports.append(h("li", {}, `${report.summary} (${report.actor_role})`));
    const actions = h(
      "div",
      { class: "actions" },
      view.state === "CONFIRMED" ? eventButton("VISIT_STARTED", "Visit started") : null,
      ["CONFIRMED", "IN_PROGRESS"].includes(view.state) ? eventButton("WORK_NOTE", "Add work note") : null,
      ["CONFIRMED", "IN_PROGRESS"].includes(view.state) ? eventButton("VISIT_COMPLETED", "Visit completed") : null,
      coordinator && view.state === "CONFIRMED" ? eventButton("NO_SHOW", "Technician did not come") : null,
      coordinator && view.state === "REQUESTED" ? eventButton("PROVIDER_CONFIRMED", "Service desk confirmed") : null,
      coordinator && view.state === "REQUESTED" ? eventButton("PROVIDER_REJECTED", "Service desk rejected") : null,
    );
    const assign = coordinator ? await assignControl(caseId) : null;
    detail.replaceChildren(
      h(
        "article",
        { class: "case", "aria-labelledby": "case-heading" },
        h("h2", { id: "case-heading" }, `${view.appliance ?? "Appliance"}: ${view.issue_summary}`),
        h(
          "dl",
          {},
          h("dt", {}, "State"),
          h("dd", { id: "case-state" }, view.pending ? `${view.state} (waiting for the service desk)` : view.state),
          h("dt", {}, "Visit"),
          h("dd", {}, when(view)),
          h("dt", {}, "Fee"),
          h("dd", {}, fee(view)),
          h("dt", {}, "Address"),
          h("dd", { id: "case-address" }, view.address ?? "not provided"),
          h("dt", {}, "Contact"),
          h("dd", {}, view.contact ?? "not provided"),
          h("dt", {}, "Warning sign"),
          h("dd", {}, view.safety_flag ? "Yes: handle with care" : "No"),
          h("dt", {}, "Customer's problem status"),
          h("dd", {}, view.issue_status.toLowerCase().replaceAll("_", " ")),
        ),
        h("h3", {}, "Checks already done"),
        view.checks.length ? checks : h("p", {}, "None recorded."),
        h("h3", {}, "Work reports"),
        view.work_reports.length ? reports : h("p", {}, "None yet."),
        h("label", { for: "work-summary" }, "Work summary (needed for a note or completion)"),
        summaryBox,
        actions,
        assign,
      ),
    );
  }

  async function assignControl(caseId: string): Promise<HTMLElement> {
    const technicians = (await api.request<{ technicians: { sub: string; username: string }[] }>(
      "GET",
      "/api/staff/technicians",
    )).technicians;
    const select = h("select", { id: "assign-to", "aria-label": "Assign to technician" });
    for (const technician of technicians) {
      select.append(h("option", { value: technician.sub }, technician.username));
    }
    return h(
      "p",
      {},
      select,
      h(
        "button",
        {
          type: "button",
          onclick: async () => {
            if (await act(`/api/staff/cases/${caseId}/assign`, { technician_sub: select.value }, "Assigned.")) {
              await refresh(caseId);
            }
          },
        },
        "Assign",
      ),
    );
  }

  async function coordinatorLists(): Promise<HTMLElement[]> {
    if (!coordinator) return [];
    const manual = (await api.request<{ items: { item_id: string; case_id: string; reason: string; status: string }[] }>(
      "GET",
      "/api/staff/manual",
    )).items;
    const manualList = h("ul", { class: "manual" });
    for (const item of manual) {
      const note = h("input", { type: "text", "aria-label": "Resolution note" });
      manualList.append(
        h(
          "li",
          {},
          `${item.reason.toLowerCase().replaceAll("_", " ")} (${item.status.toLowerCase()}) `,
          item.status === "OPEN" ? note : null,
          item.status === "OPEN"
            ? h(
                "button",
                {
                  type: "button",
                  onclick: async () => {
                    if (await act(`/api/staff/manual/${item.item_id}/resolve`, { note: note.value }, "Resolved.")) await refresh();
                  },
                },
                "Resolve",
              )
            : null,
        ),
      );
    }
    const safety = (await api.request<{ items: { ref_id: string; kind: string }[] }>("GET", "/api/staff/safety")).items;
    const safetyList = h("ul", { class: "safety" });
    for (const item of safety) {
      const evidence = h("input", { type: "text", "aria-label": "Evidence for clearing" });
      const path =
        item.kind === "HOLD"
          ? `/api/staff/safety-holds/${item.ref_id}/clear`
          : `/api/staff/issues/${item.ref_id}/clear-safety`;
      safetyList.append(
        h(
          "li",
          {},
          `${item.kind === "HOLD" ? "Household safety hold" : "Flagged problem"} `,
          evidence,
          h(
            "button",
            {
              type: "button",
              onclick: async () => {
                if (await act(path, { evidence: evidence.value }, "Cleared.")) await refresh();
              },
            },
            "Clear with evidence",
          ),
        ),
      );
    }
    return [
      h("h2", {}, "Manual review"),
      manual.length ? manualList : h("p", {}, "Nothing to review."),
      h("h2", {}, "Warning signs"),
      safety.length ? safetyList : h("p", {}, "No open warning signs."),
    ];
  }

  async function refresh(openId?: string): Promise<void> {
    try {
      const cases = (await api.request<{ cases: CaseSummary[] }>("GET", "/api/staff/queue")).cases;
      const body = h("tbody");
      for (const item of cases) {
        body.append(
          h(
            "tr",
            { class: item.pending ? "pending" : "" },
            h(
              "th",
              { scope: "row" },
              h("button", { type: "button", class: "open-case", "data-case": item.case_id, onclick: () => void openCase(item.case_id) }, `${item.appliance ?? "Appliance"}: ${item.issue_summary}`),
            ),
            h("td", {}, item.pending ? `${item.state} — pending reconciliation` : item.state),
            h("td", {}, when(item)),
            h("td", {}, fee(item)),
            h("td", {}, item.safety_flag ? "Warning sign" : ""),
          ),
        );
      }
      root.replaceChildren(
        h("h1", { id: "staff-heading" }, coordinator ? "All cases" : "My jobs"),
        status,
        cases.length
          ? h(
              "table",
              { class: "queue" },
              h("caption", {}, "Queue"),
              h(
                "thead",
                {},
                h("tr", {}, ...["Case", "State", "Visit", "Fee", "Safety"].map((c) => h("th", { scope: "col" }, c))),
              ),
              body,
            )
          : h("p", {}, "No cases."),
        detail,
        ...(await coordinatorLists()),
      );
      if (openId) await openCase(openId);
    } catch {
      root.replaceChildren(h("h1", { id: "staff-heading" }, "Service desk"), h("p", { class: "notice" }, "The queue could not be loaded."));
    }
  }

  root.append(h("h1", { id: "staff-heading" }, "Service desk"), h("p", {}, "Loading…"));
  void refresh();
  return root;
}
