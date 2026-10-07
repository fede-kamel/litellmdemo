import clsx from "clsx";
import { Scale, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { getJSON, postJSON, usd, type CompareResult, type Decision, type Scenario } from "../api";
import { Answer, Bars, ModelChip, Panel, RouteChip } from "./bits";

const LABEL: Record<string, string> = {
  "oci-auto-trained": "Trained classifier", "oci-auto-llm": "LLM classifier", "oci-auto": "Built-in heuristic",
};

export function Compare() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [pick, setPick] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<{ scenario: Scenario | null; classifier: Decision; results: CompareResult[] } | null>(null);
  useEffect(() => { getJSON<Scenario[]>("/api/scenarios").then((s) => { const r = s.filter((x) => !x.model); setScenarios(r); setPick(r[2]?.id ?? r[0].id); }); }, []);

  const go = async () => {
    setBusy(true); setData(null);
    try { setData(await postJSON("/api/compare", { scenario: pick })); } finally { setBusy(false); }
  };
  const expect = scenarios.find((s) => s.id === pick)?.expect;

  return (
    <div className="space-y-4">
      <Panel kicker="Same request, three routers" title="Which classifier picks the right route?">
        <div className="flex flex-wrap items-center gap-2">
          <select value={pick} onChange={(e) => setPick(e.target.value)} className="min-w-[360px] rounded-lg border border-line bg-paper px-3 py-2 text-[13px]">
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.use_case}: {s.title} (should be {s.expect})</option>)}
          </select>
          <button onClick={go} disabled={busy} className="flex items-center gap-2 rounded-xl bg-oracle px-4 py-2 text-[13px] font-semibold text-white disabled:bg-ink-3">
            {busy ? <RotateCw className="size-4 animate-spin" /> : <Scale className="size-4" />} Send to all three
          </button>
          <span className="text-[12px] text-ink-3">should route to {expect && <RouteChip route={expect} />}</span>
        </div>
      </Panel>
      {data && (
        <div className="grid grid-cols-[1fr_1fr_1fr_280px] gap-4">
          {data.results.map((r) => {
            const right = r.route === expect;
            return (
              <Panel key={r.router} kicker={r.router} title={LABEL[r.router]}
                right={<span className={clsx("rounded-md px-2 py-0.5 text-[11px] font-semibold", right ? "bg-moss-soft text-moss" : "bg-oracle-soft text-oracle")}>{right ? "right route" : "different route"}</span>}>
                <div className="flex flex-wrap items-center gap-2"><RouteChip route={r.route} size="lg" /><ModelChip deployment={r.deployment} /></div>
                <div className="mt-2 flex gap-4 font-mono text-[11.5px] text-ink-3"><span>{r.seconds}s</span><span>{usd(r.cost)}</span><span>by {r.cause ?? "—"}</span></div>
                <div className="scroll-thin mt-3 max-h-[300px] overflow-y-auto">{r.ok ? <Answer text={r.text} /> : <p className="text-[12.5px] text-oracle">request failed</p>}</div>
              </Panel>
            );
          })}
          <Panel kicker="Our classifier's view" title={<span className="flex items-center gap-2"><RouteChip route={data.classifier.route} /> {data.classifier.criterion}</span>}>
            {Object.keys(data.classifier.probabilities).length ? <Bars values={data.classifier.probabilities} max={1} />
              : <div className="text-[12px] text-ink-3">decided by a rule, before the model: {data.classifier.criterion}</div>}
            <div className="mt-3 text-[11px] text-ink-3">{data.classifier.milliseconds} ms on the gateway host's CPU</div>
          </Panel>
        </div>
      )}
    </div>
  );
}
