// A tiny element builder: no framework (TDD §8). Text is always set as text, never as HTML.

type Child = Node | string | null | undefined | false;
type Props = Record<string, string | boolean | ((event: Event) => void)>;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Props = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (typeof value === "function") {
      element.addEventListener(name.replace(/^on/, "").toLowerCase(), value);
    } else if (typeof value === "boolean") {
      if (value) element.setAttribute(name, "");
    } else {
      element.setAttribute(name, value);
    }
  }
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    element.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return element;
}

export const DEMO_BADGE_TEXT = "DEMO — simulated service desk";

export function demoBadge(): HTMLElement {
  // A quiet tag in the menu bar (Deb, 23 Oct): still on every view, still says what it means.
  return h(
    "span",
    { class: "demo-tag", role: "note", title: DEMO_BADGE_TEXT },
    "Demo",
    h("span", { class: "visually-hidden" }, " — simulated service desk"),
  );
}

export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
}
