export type Scenario = {
  id: string; use_case: string; title: string; expect: string; prompt: string;
  model?: string; tags?: string[]; image?: boolean;
};

export type Decision = { route: string; criterion: string; probabilities: Record<string, number>; milliseconds: number };

export type RouteInfo = {
  route?: string; cause?: string; group?: string; deployment?: string; fallbacks: number; retries: number;
  cost?: number; ms?: number; call_id?: string;
};

export type RunEvent =
  | ({ type: "classify"; t: number; call: number } & Decision)
  | ({ type: "llm"; t: number; call: number; asked: string; seconds: number; tokens: { in?: number; out?: number };
       tool_calls: string[]; text: string } & RouteInfo)
  | { type: "tool"; t: number; name: string; input: string }
  | { type: "tool_result"; t: number; output: string }
  | { type: "answer"; t: number; text: string; seconds: number; calls: number }
  | { type: "error"; t: number; message: string };

export type CompareResult = { router: string; ok: boolean; seconds: number; text: string } & RouteInfo;

export const ROUTES = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING", "CODE", "VISION", "LONG_CONTEXT", "MULTILINGUAL"] as const;

export const ROUTE_STYLE: Record<string, { tone: string; group: string; blurb: string }> = {
  SIMPLE: { tone: "bg-moss-soft text-moss border-moss/30", group: "oci-fast", blurb: "quick facts, formatting" },
  MEDIUM: { tone: "bg-teal-soft text-teal border-teal/30", group: "oci-balanced", blurb: "explanations, summaries" },
  COMPLEX: { tone: "bg-indigo-soft text-indigo border-indigo/30", group: "oci-strong", blurb: "multi-part analysis" },
  REASONING: { tone: "bg-oracle-soft text-oracle border-oracle/30", group: "oci-reasoning", blurb: "proofs, constrained planning" },
  CODE: { tone: "bg-violet-soft text-violet border-violet/30", group: "oci-code", blurb: "write and debug code" },
  VISION: { tone: "bg-ochre-soft text-ochre border-ochre/30", group: "oci-vision", blurb: "images" },
  LONG_CONTEXT: { tone: "bg-sand text-ink-2 border-line", group: "oci-long", blurb: "very long documents" },
  MULTILINGUAL: { tone: "bg-teal-soft text-teal border-teal/30", group: "oci-multilingual", blurb: "not English" },
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
