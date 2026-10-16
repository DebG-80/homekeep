// Placeholder page (Slice 0). The elder, household, staff and Ops views arrive in Slice 4.
// Every view carries the persistent demo badge (TDD §8.6).

const DEMO_BADGE_TEXT = "DEMO — simulated service desk";

function render(root: HTMLElement): void {
  const badge = document.createElement("p");
  badge.className = "demo-badge";
  badge.textContent = DEMO_BADGE_TEXT;

  const main = document.createElement("main");
  const heading = document.createElement("h1");
  heading.textContent = "HomeKeep";
  const status = document.createElement("p");
  status.textContent = "HomeKeep is not ready yet. Please check back soon.";
  const disclosure = document.createElement("p");
  disclosure.textContent = "This is a demonstration. No real technician will visit.";
  main.append(heading, status, disclosure);

  root.replaceChildren(badge, main);
}

const style = document.createElement("style");
style.textContent = `
  body { margin: 0; font: 1.25rem/1.5 system-ui, sans-serif; color: #111; background: #fff; }
  main { max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }
  .demo-badge { margin: 0; padding: 0.5rem 1rem; background: #7a2e00; color: #fff; font-weight: 700; }
`;
document.head.append(style);

const root = document.getElementById("app");
if (root) {
  render(root);
}
