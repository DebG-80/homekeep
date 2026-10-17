// FR-20 and AT-21 in the browser: the owner removes the booking helper's access, and the
// helper's very next turn is refused.

import { expect, test } from "@playwright/test";
import { sayText, signIn, stubSpeech } from "./helpers";

test("owner revokes the booking helper, whose next turn is refused", async ({ browser }) => {
  const helperContext = await browser.newContext();
  const helper = await helperContext.newPage();
  await stubSpeech(helper);
  await signIn(helper, "a_helper_booking");
  await sayText(helper, "Hello");

  const ownerContext = await browser.newContext();
  const owner = await ownerContext.newPage();
  await stubSpeech(owner);
  await signIn(owner, "a_owner");
  await owner.locator('a[href="#/household"]').click();
  const card = owner.locator('[data-member="hk-qa-a-booker"]');
  await expect(card).toContainText("active");
  owner.once("dialog", (dialog) => void dialog.accept());
  await card.locator(".revoke").click();
  await expect(owner.locator("#household-status")).toHaveText("hk-qa-a-booker no longer has access.");
  await expect(owner.locator('[data-member="hk-qa-a-booker"]')).toContainText("revoked");

  await helper.locator("#say").fill("What appliances do I have?");
  await helper.locator("#say").press("Enter");
  await expect(helper.locator("#notice")).toHaveText("You no longer have access. Please sign in again.");
  await ownerContext.close();
  await helperContext.close();
});
