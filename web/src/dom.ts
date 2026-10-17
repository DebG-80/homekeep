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
  return h("p", { class: "demo-badge", role: "note" }, DEMO_BADGE_TEXT);
}

export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
}
