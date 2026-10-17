// AT-33: a fridge or TV symptom, or an AC error code on an unverified model, gets the labelled
// scope limit and a service offer, never a guessed diagnosis or a cited step.

import { expect, test } from "@playwright/test";
import { apiGet, sayText, script, signIn, stubSpeech } from "./helpers";

test("fridge and unknown AC code get the scope limit and a service draft", async ({ page, request }) => {
  await stubSpeech(page);
  await signIn(page, "a_owner");

  await script(request, [
    {
      call: "report_issue",
      input: {
        appliance_id: "qa-a-fridge",
        symptom_text: "Ice is building up on the back wall",
        symptom_category: "OTHER",
        confirmed_distinct: true,
      },
    },
    { say: "I've noted that." },
  ]);
  await sayText(page, "My fridge has ice on the back wall");
  const issues = (await apiGet<{ open_issues: { issue_id: string; appliance_id: string }[] }>(
    request,
    "a_owner",
    "/api/household",
  )).open_issues;
  const fridgeIssue = issues.find((i) => i.appliance_id === "qa-a-fridge")!.issue_id;
  await script(request, [{ call: "get_guidance", input: { issue_id: fridgeIssue } }, { say: "Try defrosting it." }]);
  const fridge = await sayText(page, "What can I check?");
  expect(fridge).toContain("I can't give checks for fridges yet.");
  expect(fridge).toContain("demo technician visit");
  expect(fridge).not.toContain("defrost"); // the model's guess is never spoken

  await script(request, [
    { call: "draft_service_request", input: { issue_id: fridgeIssue } },
    { say: "I've started a request for a demo visit." },
  ]);
  await sayText(page, "Yes, please arrange a visit");
  const requests = (await apiGet<{ service_requests: { issue_id: string; state: string }[] }>(
    request,
    "a_owner",
    "/api/household",
  )).service_requests;
  expect(requests.find((r) => r.issue_id === fridgeIssue)?.state).toBe("DRAFT");

  await script(request, [
    {
      call: "report_issue",
      input: {
        appliance_id: "qa-a-ac-hall",
        symptom_text: "It shows E7 and stops",
        symptom_category: "ERROR_CODE",
        confirmed_distinct: true,
      },
    },
    { say: "I've noted the code." },
  ]);
  await sayText(page, "The hall AC shows E7");
  const hallIssue = (await apiGet<{ open_issues: { issue_id: string; appliance_id: string }[] }>(
    request,
    "a_owner",
    "/api/household",
  )).open_issues.find((i) => i.appliance_id === "qa-a-ac-hall")!.issue_id;
  await script(request, [{ call: "get_guidance", input: { issue_id: hallIssue } }, { say: "E7 means low gas." }]);
  const code = await sayText(page, "What does E7 mean?");
  expect(code).toContain("demo technician visit");
  expect(code).not.toContain("low gas");
});
