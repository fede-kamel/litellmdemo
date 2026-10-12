export type Scenario = {
  id: string; use_case: string; title: string; expect: string; prompt: string;
  model?: string; tags?: string[]; image?: boolean;
};

export type Decision = { route: string; criterion: string; probabilities: Record<string, number>; milliseconds: number };

export type RouteInfo = {
  gateway?: string; route?: string; cause?: string; group?: string; deployment?: string; fallbacks: number; retries: number;
  cost?: number; ms?: number; call_id?: string;
};

export type RunEvent =
  | ({ type: "classify"; t: number; call: number } & Decision)
  | ({ type: "llm"; t: number; call: number; asked: string; seconds: number; tokens: { in?: number; out?: number };
       tool_calls: string[]; text: string } & RouteInfo)
  | { type: "tool"; t: number; name: string; input: string }
  | { type: "tool_result"; t: number; output: string }
  | { type: "answer"; t: number; text: string; seconds: number; calls: number }
  | { type: "error"; t: number; message: string }
  | { type: "failover"; t: number; from: string; to: string; reason: string };

export type CompareResult = { router: string; ok: boolean; seconds: number; text: string } & RouteInfo;

export const ROUTES = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING", "CODE", "VISION", "LONG_CONTEXT", "MULTILINGUAL"] as const;

// One hue per route (the tokens in index.css): `tone` for chips, `color` for marks in the map and the bars.
export const ROUTE_STYLE: Record<string, { tone: string; color: string; group: string; blurb: string }> = {
  SIMPLE: { tone: "bg-rt-simple-soft text-rt-simple-ink border-rt-simple/40", color: "#2a78d6", group: "oci-fast", blurb: "quick facts, formatting" },
  MEDIUM: { tone: "bg-rt-medium-soft text-rt-medium-ink border-rt-medium/40", color: "#eb6834", group: "oci-balanced", blurb: "explanations, summaries" },
  COMPLEX: { tone: "bg-rt-complex-soft text-rt-complex-ink border-rt-complex/40", color: "#1baf7a", group: "oci-strong", blurb: "multi-part analysis" },
  REASONING: { tone: "bg-rt-reasoning-soft text-rt-reasoning-ink border-rt-reasoning/40", color: "#eda100", group: "oci-reasoning", blurb: "proofs, constrained planning" },
  CODE: { tone: "bg-rt-code-soft text-rt-code-ink border-rt-code/40", color: "#e87ba4", group: "oci-code", blurb: "write and debug code" },
  VISION: { tone: "bg-rt-vision-soft text-rt-vision-ink border-rt-vision/40", color: "#008300", group: "oci-vision", blurb: "images" },
  LONG_CONTEXT: { tone: "bg-rt-long-soft text-rt-long-ink border-rt-long/40", color: "#6250d6", group: "oci-long", blurb: "very long documents" },
  MULTILINGUAL: { tone: "bg-rt-multi-soft text-rt-multi-ink border-rt-multi/40", color: "#e34948", group: "oci-multilingual", blurb: "not English" },
};
export const ROUTE_COLOR: Record<string, string> = Object.fromEntries(Object.entries(ROUTE_STYLE).map(([k, v]) => [k, v.color]));
/** A darker step of each route's hue, for text beside its mark (>= 4.6:1 on white and on the tint). */
export const ROUTE_INK: Record<string, string> = {
  SIMPLE: "#2467b9", MEDIUM: "#bb4212", COMPLEX: "#137a55", REASONING: "#916300",
  CODE: "#ca2362", VISION: "#007900", LONG_CONTEXT: "#6250d6", MULTILINGUAL: "#ca201f",
};
/** The plain name of a route's model group, for a sentence. */
export const ROUTE_NAME: Record<string, string> = {
  SIMPLE: "the fast models", MEDIUM: "the balanced models", COMPLEX: "the strong models", REASONING: "the reasoning models",
  CODE: "the code models", VISION: "the vision models", LONG_CONTEXT: "the long-context models", MULTILINGUAL: "the multilingual models",
};

export function vendor(deployment?: string): string {
  const m = (deployment ?? "").replace(/^oci\//, "");
  if (m.startsWith("openai.")) return "OpenAI";
  if (m.startsWith("google.")) return "Google";
  if (m.startsWith("meta.")) return "Meta";
  if (m.startsWith("xai.")) return "xAI";
  if (m.startsWith("cohere.")) return "Cohere";
  return "";
}

export function shortModel(deployment?: string): string {
  return (deployment ?? "").replace(/^oci\//, "").replace(/^(openai|google|meta|xai|cohere)\./, "")
    .replace("-instruct", "").replace("-17b-128e", "").replace("-17b-16e", "").replace("-fp8", "");
}

export async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${(await r.json().catch(() => ({}))).detail ?? r.statusText}`);
  return r.json() as Promise<T>;
}

export const usd = (n?: number) => (n === undefined || n === null ? "–" : n < 0.01 ? `$${n.toFixed(5)}` : `$${n.toFixed(3)}`);
