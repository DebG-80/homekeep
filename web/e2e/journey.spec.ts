// The BRD §3.3 path on the text channel, judge household 1: consent, register, report, draft,
// address and contact, slots, read-back, "yes", demo confirmation, technician completion, the
// customer's own answer, close, history (AT-01, AT-12, AT-19 paths at E2E level).

import { expect, test } from "@playwright/test";
import { apiGet, resetJudge, sayText, script, signIn, stubSpeech, tomorrowMorning } from "./helpers";

interface Household {
  appliances: { appliance_id: string; nickname: string }[];
  open_issues: { issue_id: string }[];
  service_requests: { request_id: string; version: number }[];
}

test("judge books a demo visit by text and closes it after the technician's visit", async ({ page, browser, request }) => {
  await resetJudge(request, "j1_owner");
  await stubSpeech(page);
  await signIn(page, "j1_owner");
  const household = () => apiGet<Household>(request, "j1_owner", "/api/household");

  await script(request, [{ call: "prepare_action", input: { kind: "CONSENT_STORAGE" } }, { say: "" }]);
  expect(await sayText(page, "Please remember my appliances")).toContain("May I save your appliances");
  expect(await sayText(page, "yes")).toContain("I'll save your appliances");

  await script(request, [
    { call: "register_appliance", input: { category: "AC", nickname: "Bedroom AC" } },
    { say: "I've saved your bedroom AC. What seems to be the problem?" },
  ]);
  await sayText(page, "I have an AC in the bedroom");
  const applianceId = (await household()).appliances[0]!.appliance_id;

  await script(request, [
    {
      call: "report_issue",
      input: { appliance_id: applianceId, symptom_text: "It is not cooling", symptom_category: "NOT_COOLING" },
    },
    { say: "I've noted that it isn't cooling. Would you like a demo technician visit?" },
  ]);
  await sayText(page, "It is not cooling");
  const issueId = (await household()).open_issues[0]!.issue_id;

  await script(request, [
    { call: "draft_service_request", input: { issue_id: issueId } },
    { say: "What address should the technician come to?" },
  ]);
  await sayText(page, "Yes, send someone");
  let sr = (await household()).service_requests[0]!;
  await script(request, [
    {
      call: "record_service_details",
      input: { request_id: sr.request_id, field: "address", value: "Flat 2, Sample Nagar, Pune", expected_version: sr.version },
    },
    { say: "Thank you. What phone number should they use?" },
  ]);
  await sayText(page, "Flat 2, Sample Nagar, Pune");
  sr = (await household()).service_requests[0]!;
  await script(request, [
    {
      call: "record_service_details",
      input: { request_id: sr.request_id, field: "contact", value: "Landline 000 0000 0000", expected_version: sr.version },
    },
    { say: "Thank you. Shall I look for a time?" },
  ]);
  await sayText(page, "Landline 000 0000 0000");

  await script(request, [
    { call: "list_slots", input: { request_id: sr.request_id } },
    { say: "There is a morning time tomorrow. Would that suit you?" },
  ]);
  await sayText(page, "What times are there?");
  await script(request, [
    { call: "prepare_action", input: { kind: "SUBMIT", request_id: sr.request_id, slot_id: tomorrowMorning() } },
    { say: "" },
  ]);
  const readback = await sayText(page, "Tomorrow morning is fine");
  expect(readback).toContain("HomeKeep Demo Service Desk");
  expect(readback).toContain("Shall I book it?");
  await expect(page.locator("#next-action")).toContainText("say “yes”");

  const confirmed = await sayText(page, "yes");
  expect(confirmed).toContain("Your demo booking is confirmed");
  expect(confirmed).toContain("No real technician will visit.");

  // The assigned technician completes the visit in the staff console.
  const staffContext = await browser.newContext();
  const staff = await staffContext.newPage();
  await stubSpeech(staff);
  await signIn(staff, "tech_assigned");
  await staff.locator(`[data-case="${sr.request_id}"]`).click();
  await staff.locator("#work-summary").fill("Cleaned the filter.");
  await staff.locator('[data-event="VISIT_COMPLETED"]').click();
  await expect(staff.locator("#case-state")).toHaveText("COMPLETED");
  await staffContext.close();

  // Only the customer's answer resolves and closes the problem (invariant 8).
  await script(request, [
    { call: "confirm_resolution", input: { issue_id: issueId, answer: "RESOLVED", close: true } },
    { say: "" },
  ]);
  expect(await sayText(page, "It works now, you can close it")).toContain("I've closed this problem.");

  await page.locator('a[href="#/household"]').click();
  await page.locator(`[data-appliance="${applianceId}"]`).click();
  const history = page.locator(".history");
  await expect(history).toContainText("staff visit completed (Technician)");
  await expect(history).toContainText("issue customer closed (Owner)");
});
