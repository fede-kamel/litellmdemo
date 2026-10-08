import { ArrowRight, GitBranch, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { ROUTES, ROUTE_STYLE, getJSON } from "../api";
import { ModelChip, Panel, RouteChip } from "./bits";

type Gateway = {
  groups: Record<string, { model: string; tags?: string[]; router: boolean }[]>;
  routers: Record<string, { classifier: string; routes: Record<string, string> }>;
  strategy: string; fallbacks: Record<string, string[]>[]; context_window_fallbacks: Record<string, string[]>[];
};

export function GatewayView({ usage }: { usage: Record<string, number> }) {
  const [g, setG] = useState<Gateway | null>(null);
  useEffect(() => { getJSON<Gateway>("/api/gateway").then(setG); }, []);
  if (!g) return null;
  const fb = Object.fromEntries(g.fallbacks.flatMap((f) => Object.entries(f)));
  const routeGroups = ROUTES.flatMap((r) => [ROUTE_STYLE[r].group, ...(fb[ROUTE_STYLE[r].group] ?? [])]);
  const models = new Set(routeGroups.flatMap((grp) => (g.groups[grp] ?? []).map((d) => d.model))).size;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_340px] gap-4">
      <Panel kicker="gateway/config.yaml" title={`Eight routes, ${models} OCI models, one endpoint`} right={<span className="font-mono text-[11px] text-ink-3">routing_strategy: {g.strategy}</span>}>
        <div className="space-y-2">
          {ROUTES.map((r) => {
            const group = ROUTE_STYLE[r].group;
            return (
              <div key={r} className="grid grid-cols-[130px_150px_minmax(0,1fr)] items-center gap-3 rounded-xl border border-line/70 px-3 py-2">
                <div><RouteChip route={r} /><div className="mt-0.5 text-[10.5px] text-ink-3">{ROUTE_STYLE[r].blurb}</div></div>
                <div className="font-mono text-[12px] text-ink-2">{group}</div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {(g.groups[group] ?? []).map((d) => <ModelChip key={d.model} deployment={d.model} lit={(usage[d.model] ?? 0) > 0} />)}
                  {fb[group] && <><ArrowRight className="size-3.5 text-ink-3" /><span className="text-[10.5px] text-ink-3">falls back to</span>
                    {fb[group].flatMap((b) => g.groups[b] ?? []).map((d) => <ModelChip key={d.model} deployment={d.model} />)}</>}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
      <div className="space-y-4">
        <Panel kicker="Auto routers" title="Who classifies">
          {Object.entries(g.routers).map(([name, r]) => (
            <div key={name} className="mb-2 rounded-lg bg-sand/60 px-3 py-2">
              <div className="font-mono text-[12px] font-semibold">{name}</div>
              <div className="text-[11.5px] text-ink-3">classifier_type: <span className="font-mono text-ink-2">{r.classifier}</span> · {Object.keys(r.routes).length} routes</div>
            </div>
          ))}
        </Panel>
        <Panel kicker="Also in the config" title="Beyond classification">
          <ul className="space-y-2 text-[12px] text-ink-2">
            <li className="flex gap-2"><GitBranch className="mt-0.5 size-3.5 shrink-0 text-oracle" /><span><b>Tags</b>: <span className="font-mono">oci-chat</span> sends <span className="font-mono">premium</span> to GPT-5.2, the rest to Gemini Flash.</span></li>
            <li className="flex gap-2"><GitBranch className="mt-0.5 size-3.5 shrink-0 text-oracle" /><span><b>Context window</b>: a prompt too long for <span className="font-mono">oci-compact</span> moves to <span className="font-mono">oci-long</span> before the call.</span></li>
            <li className="flex gap-2"><GitBranch className="mt-0.5 size-3.5 shrink-0 text-oracle" /><span><b>Fallbacks</b>: {g.fallbacks.length} chains; <span className="font-mono">oci-flaky</span> always fails, to show one live.</span></li>
            <li className="flex gap-2"><ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-oracle" /><span><b>Signing</b>: the gateway signs each OCI call with the operator's session; apps hold only a gateway key.</span></li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
