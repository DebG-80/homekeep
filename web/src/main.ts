// HomeKeep web client (TDD §8): sign in, then the elder's Talk view, the household and history
// view, or the staff console. Every view carries the persistent demo badge (TDD §8.6).

import "./styles.css";
import { Api } from "./api";
import { SignInError, signIn, type Identity } from "./auth";
import { loadConfig } from "./config";
import { demoBadge, h } from "./dom";
import { householdView } from "./views/household";
import { staffView } from "./views/staff";
import { talkView, type View } from "./views/talk";

const STAFF_GROUPS = ["coordinator", "technician", "catalog_reviewer", "admin"];

function shell(identity: Identity, api: Api, outlet: HTMLElement): HTMLElement {
  const staff = identity.groups.some((g) => STAFF_GROUPS.includes(g));
  const links: Array<[string, string]> = staff
    ? [["#/staff", "Service desk"]]
    : [
        ["#/talk", "Talk"],
        ["#/household", "Household and history"],
      ];
  const nav = h("nav", { "aria-label": "Main" });
  for (const [href, label] of links) nav.append(h("a", { href }, label));
  nav.append(
    h("span", { class: "who" }, `Signed in: ${identity.name}`),
    h("button", { type: "button", class: "sign-out", onclick: () => void identity.signOut() }, "Sign out"),
  );

  let current: View | null = null;
  const show = (view: View): void => {
    current?.dispose?.(); // the old view lets go of the microphone and its listeners
    current = view;
    outlet.replaceChildren(view);
  };
  const route = (): void => {
    const hash = location.hash || (staff ? "#/staff" : "#/talk");
    for (const link of nav.querySelectorAll("a")) {
      if (link.getAttribute("href") === hash) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (staff) show(staffView(api, identity.groups));
    else if (hash === "#/household") {
      show(householdView(api, () => sessionStorage.removeItem("hk.session")));
    } else show(talkView(api));
    document.title = `HomeKeep — ${staff ? "Service desk" : hash === "#/household" ? "Household" : "Talk"}`;
  };
  window.addEventListener("hashchange", route);
  route();
  return h(
    "div",
    { class: "app" },
    h("a", { href: "#main", class: "skip" }, "Skip to content"),
    demoBadge(),
    h("header", {}, h("p", { class: "brand" }, "HomeKeep"), nav),
    outlet,
  );
}

async function start(root: HTMLElement): Promise<void> {
  try {
    const config = await loadConfig();
    const identity = await signIn(config, root);
    const outlet = h("main", { id: "main", tabindex: "-1" });
    root.replaceChildren(shell(identity, new Api(identity.token), outlet));
  } catch (error) {
    const message =
      error instanceof SignInError ? error.message : "HomeKeep could not start. Please reload the page.";
    root.replaceChildren(demoBadge(), h("main", { id: "main" }, h("h1", {}, "HomeKeep"), h("p", {}, message)));
  }
}

const root = document.getElementById("app");
if (root) void start(root);
