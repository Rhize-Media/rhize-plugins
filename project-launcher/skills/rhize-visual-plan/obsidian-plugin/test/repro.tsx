import { JSDOM } from "jsdom";
const dom = new JSDOM("<!DOCTYPE html><div id='root'></div>", { url: "https://localhost/", pretendToBeVisual: true });
function setg(k: string, v: any) { try { Object.defineProperty(globalThis as any, k, { value: v, configurable: true, writable: true }); } catch { /* read-only global */ } }
setg("window", dom.window); setg("document", dom.window.document); setg("navigator", dom.window.navigator);
setg("HTMLElement", dom.window.HTMLElement); setg("Node", dom.window.Node); setg("Element", dom.window.Element);
setg("getComputedStyle", dom.window.getComputedStyle); setg("DOMParser", dom.window.DOMParser);
setg("requestAnimationFrame", (cb: any) => setTimeout(cb, 0)); setg("cancelAnimationFrame", (id: any) => clearTimeout(id));
const errors: string[] = [];
const realErr = console.error.bind(console);
console.error = (...a: any[]) => { errors.push(a.map((x: any) => (x && x.stack ? x.stack : String(x))).join(" ")); realErr(...a); };
dom.window.addEventListener("error", (e: any) => errors.push("window.onerror: " + (e.error?.stack || e.message)));
dom.window.addEventListener("unhandledrejection", (e: any) => errors.push("unhandledrejection: " + (e.reason?.stack || e.reason)));
import * as fs from "node:fs";
import { mountPlan } from "../src/MdxRenderer";
const raw = fs.readFileSync(process.argv[2], "utf8");
const container = (globalThis as any).document.getElementById("root");
(async () => {
  try { await mountPlan(container, raw); } catch (e: any) { errors.push("mountPlan threw: " + (e?.stack || e)); }
  await new Promise((r) => setTimeout(r, 800));
  const html = container.innerHTML as string;
  fs.writeFileSync("/tmp/rvp_repro.html", html);
  console.log("HTML_LENGTH:", html.length, "| HAS_TABLE:", html.includes("<table"), "| RVP_ERROR:", html.includes("rvp-error"), "| ERRORS:", errors.length);
  errors.slice(0, 5).forEach((e, i) => console.log(`ERR[${i}] ` + e.slice(0, 500)));
  process.exit(0);
})();
