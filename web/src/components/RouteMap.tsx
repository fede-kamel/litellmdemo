import clsx from "clsx";
import { useEffect, useState } from "react";
import { ROUTES, ROUTE_STYLE, getJSON, shortModel, vendor, type RunEvent } from "../api";

type Gateway = { groups: Record<string, { model: string }[]>; fallbacks: Record<string, string[]>[] };
type Call = Extract<RunEvent, { type: "llm" }>;

const W = 980, H = 470;
const COL = { req: 70, clf: 250, route: 470, model: 760 };
const ROUTE_COLOR: Record<string, string> = {
  SIMPLE: "#5f7d4f", MEDIUM: "#2c5967", COMPLEX: "#3d3a8f", REASONING: "#c74634",
  CODE: "#6b4fa0", VISION: "#b07d1f", LONG_CONTEXT: "#6f6964", MULTILINGUAL: "#2c7a7b",
};

/** The gateway's routing, drawn live: request → classifier → route → OCI model.
 * Each model call the agent makes lights its path as the gateway reports it. */
export function RouteMap({ calls, classifying, router }: { calls: Call[]; classifying: boolean; router: string }) {
  const [g, setG] = useState<Gateway | null>(null);
  useEffect(() => { getJSON<Gateway>("/api/gateway").then(setG); }, []);
  if (!g) return null;

  const fb = Object.fromEntries(g.fallbacks.flatMap((f) => Object.entries(f)));
  const models: { model: string; route: string; backup: boolean }[] = [];
  for (const r of ROUTES) {
    const group = ROUTE_STYLE[r].group;
    for (const d of g.groups[group] ?? []) if (!models.some((m) => m.model === d.model)) models.push({ model: d.model, route: r, backup: false });
    for (const b of fb[group] ?? []) for (const d of g.groups[b] ?? []) if (!models.some((m) => m.model === d.model)) models.push({ model: d.model, route: r, backup: true });
  }
  const routeY = (r: string) => 40 + ROUTES.indexOf(r as (typeof ROUTES)[number]) * ((H - 80) / (ROUTES.length - 1));
  const modelY = (m: string) => 18 + models.findIndex((x) => x.model === m) * ((H - 64) / Math.max(1, models.length - 1));
  const last = calls[calls.length - 1];
  const lastRoute = last?.route;
  const used = new Map<string, number>();
  calls.forEach((c) => c.deployment && used.set(c.deployment, (used.get(c.deployment) ?? 0) + 1));
  const routeHits = new Map<string, number>();
  calls.forEach((c) => c.route && routeHits.set(c.route, (routeHits.get(c.route) ?? 0) + 1));
  const curve = (x1: number, y1: number, x2: number, y2: number) => `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <defs>
          <filter id="glow"><feGaussianBlur stdDeviation="3" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        {/* static wiring */}
        {ROUTES.map((r) => <path key={r} d={curve(COL.clf + 70, H / 2, COL.route - 6, routeY(r))} stroke="#e7e2de" strokeWidth={2} fill="none" />)}
        {models.map((m) => <path key={m.model} d={curve(COL.route + 112, routeY(m.route), COL.model - 6, modelY(m.model))} stroke="#efebe7" strokeWidth={1.5} fill="none" strokeDasharray={m.backup ? "4 4" : undefined} />)}
        {/* every call so far, faint; the last call, bright */}
        {calls.map((c, i) => {
          if (!c.route || !c.deployment || modelY(c.deployment) < 0) return null;
          const color = ROUTE_COLOR[c.route] ?? "#c74634";
          const leg = c.fallbacks ? "#b07d1f" : color;   // a fallback's last leg is drawn in ochre
          const isLast = i === calls.length - 1;
          return (
            <g key={i} opacity={isLast ? 1 : 0.28}>
              <path d={curve(COL.req + 60, H / 2, COL.clf - 70, H / 2)} stroke={color} strokeWidth={isLast ? 4 : 2} fill="none" />
              <path d={curve(COL.clf + 70, H / 2, COL.route - 6, routeY(c.route))} stroke={color} strokeWidth={isLast ? 4 : 2} fill="none"
                className={isLast ? "flow" : undefined} filter={isLast ? "url(#glow)" : undefined} />
              <path d={curve(COL.route + 112, routeY(c.route), COL.model - 6, modelY(c.deployment))} stroke={leg} strokeWidth={isLast ? 4 : 2}
                fill="none" className={isLast ? "flow" : undefined} filter={isLast ? "url(#glow)" : undefined} />
            </g>
          );
        })}
        {/* request */}
        <g>
          <rect x={COL.req - 60} y={H / 2 - 36} width={120} height={72} rx={14} fill="#161513" />
          <text x={COL.req} y={H / 2 - 6} textAnchor="middle" fill="#fff" fontSize={13} fontWeight={600}>request</text>
          <text x={COL.req} y={H / 2 + 14} textAnchor="middle" fill="#bdb6b0" fontSize={10.5} fontFamily="JetBrains Mono">{router}</text>
        </g>
        {/* classifier */}
        <g>
          <rect x={COL.clf - 70} y={H / 2 - 48} width={140} height={96} rx={16} fill="#fbeae7" stroke="#c74634" strokeWidth={2}
            className={classifying ? "pulse-box" : undefined} />
          <text x={COL.clf} y={H / 2 - 18} textAnchor="middle" fill="#c74634" fontSize={13} fontWeight={700}>classifier</text>
          <text x={COL.clf} y={H / 2 + 2} textAnchor="middle" fill="#3f3a36" fontSize={11}>{router === "oci-auto-trained" ? "rules + trained model" : router === "oci-auto-llm" ? "LLM grades it" : router === "oci-auto" ? "built-in heuristic" : "fixed group"}</text>
          <text x={COL.clf} y={H / 2 + 26} textAnchor="middle" fill="#6f6964" fontSize={10.5} fontFamily="JetBrains Mono">
            {classifying ? "deciding…" : lastRoute ? `→ ${lastRoute}` : "waiting"}</text>
        </g>
        {/* routes */}
        {ROUTES.map((r) => {
          const on = r === lastRoute, hits = routeHits.get(r) ?? 0;
          return (
            <g key={r}>
              <rect x={COL.route} y={routeY(r) - 17} width={112} height={34} rx={9} fill={on ? ROUTE_COLOR[r] : "#fff"} stroke={ROUTE_COLOR[r]} strokeWidth={on ? 2.5 : 1.5} />
              <text x={COL.route + 56} y={routeY(r) + 4.5} textAnchor="middle" fontSize={11} fontWeight={700} fontFamily="JetBrains Mono" fill={on ? "#fff" : ROUTE_COLOR[r]}>{r === "LONG_CONTEXT" ? "LONG_CTX" : r === "MULTILINGUAL" ? "MULTILING" : r}</text>
              {hits > 0 && <><circle cx={COL.route + 112} cy={routeY(r) - 15} r={9} fill="#161513" /><text x={COL.route + 112} y={routeY(r) - 11.5} textAnchor="middle" fontSize={10} fill="#fff" fontWeight={700}>{hits}</text></>}
            </g>
          );
        })}
        {/* models */}
        {models.map((m) => {
          const on = m.model === last?.deployment, n = used.get(m.model) ?? 0;
          return (
            <g key={m.model}>
              <rect x={COL.model} y={modelY(m.model) - 12} width={210} height={24} rx={7} fill={on ? "#161513" : n ? "#f1efed" : "#fff"} stroke={on ? "#161513" : "#e7e2de"} />
              <text x={COL.model + 9} y={modelY(m.model) + 4} fontSize={10.5} fontWeight={700} fill={on ? "#f0cc71" : "#6f6964"}>{vendor(m.model)}</text>
              <text x={COL.model + 62} y={modelY(m.model) + 4} fontSize={10.5} fontFamily="JetBrains Mono" fill={on ? "#fff" : "#3f3a36"}>{shortModel(m.model).slice(0, 22)}</text>
              {m.backup && <text x={COL.model + 204} y={modelY(m.model) + 4} textAnchor="end" fontSize={9} fill={on ? "#bdb6b0" : "#a8a19b"}>backup</text>}
            </g>
          );
        })}
        <text x={COL.req} y={H - 6} textAnchor="middle" fontSize={10} fill="#a8a19b">app</text>
        <text x={COL.clf} y={H - 6} textAnchor="middle" fontSize={10} fill="#a8a19b">LiteLLM gateway</text>
        <text x={COL.route + 56} y={H - 6} textAnchor="middle" fontSize={10} fill="#a8a19b">8 routes</text>
        <text x={COL.model + 105} y={H - 6} textAnchor="middle" fontSize={10} fill="#a8a19b">OCI Generative AI</text>
      </svg>
      {last && (
        <div className={clsx("absolute left-2 top-2 rounded-lg bg-ink/90 px-3 py-1.5 font-mono text-[11px] text-white", last.fallbacks ? "ring-2 ring-ochre" : "")}>
          call {last.call}: {last.route ?? last.group} → {shortModel(last.deployment)} · {last.seconds}s{last.fallbacks ? ` · fallback ×${last.fallbacks}` : ""}
        </div>
      )}
    </div>
  );
}
