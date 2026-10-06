import clsx from "clsx";
import { Check, CornerDownLeft, Minus, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";
import { getJSON, postJSON, shortModel, usd, type Decision, type RouteInfo, type RunEvent } from "../api";
import { Bars, ModelChip, Panel, RouteChip } from "./bits";
import { RouteMap } from "./RouteMap";

type Tier = { route: string; deployment?: string; pass_rate: number; cost?: number };
type Precedent = { prompt: string; similarity: number; label: string; learned_as?: string; votes?: string[]; source?: string; tiers: Tier[] };
type Step = { route: string; pass: number; cost: number; clears: boolean; chosen: boolean };
type Check_ = { check: string; fired: boolean; saw: string; bar?: number; steps?: Step[] };
type CurvePoint = { bar: number; quality: number; cost_per_request: number };
type AskConfig = { examples: string[]; default_bar: number; held_out_curve: CurvePoint[];
  held_out: Record<string, { quality: number; cost_per_request: number }>; held_out_prompts: number };
type AskResult = {
  prompt: string; ok: boolean; text: string; seconds: number; agrees: boolean;
  why: { decision: Decision; checks: Check_[]; precedent: Precedent[]; meaning: string; summary: string };
  group: string; candidates: string[]; strategy: string; model_why: string; route: RouteInfo;
  gateway?: string; gateway_role?: string;
};

const CHECK_LABEL: Record<string, string> = {
  image: "Image rule", length: "Length rule", language: "Language rule", code: "Code check", ladder: "Quality ladder", model: "Trained model",
};

/** The ladder: each route, cheapest first, with its chance of a good answer against the bar. */
function LadderSteps({ steps, bar }: { steps: Step[]; bar: number }) {
  return (
    <div className="mt-2 space-y-1.5">
      {steps.map((s) => (
        <div key={s.route} className="flex items-center gap-2 text-[11px]">
          <span className="w-[96px] shrink-0"><RouteChip route={s.route} /></span>
          <div className="relative h-2.5 flex-1 rounded-full bg-sand">
            <div className={clsx("h-2.5 rounded-full", s.chosen ? "bg-oracle" : s.clears ? "bg-moss/60" : "bg-ink-3/40")} style={{ width: `${s.pass * 100}%` }} />
            <div className="absolute -top-1 h-4.5 w-0.5 bg-ink" style={{ left: `${bar * 100}%` }} title={`bar ${Math.round(bar * 100)}%`} />
          </div>
          <span className="w-10 text-right font-mono text-ink-2">{Math.round(s.pass * 100)}%</span>
          <span className="w-[72px] text-right font-mono text-ink-3">{usd(s.cost)}</span>
          <span className={clsx("w-[64px] text-[10.5px] font-semibold", s.chosen ? "text-oracle" : "text-ink-3")}>{s.chosen ? "chosen" : s.clears ? "clears" : "below bar"}</span>
        </div>
      ))}
      <div className="pl-[104px] text-[10.5px] text-ink-3">bar at {Math.round(bar * 100)}% · cost is the route's typical cost per request · cheapest route first</div>
    </div>
  );
}

export function Ask() {
  const [cfg, setCfg] = useState<AskConfig | null>(null);
  const [bar, setBar] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<AskResult | null>(null);
  useEffect(() => { getJSON<AskConfig>("/api/ask/config").then((c) => { setCfg(c); setBar(c.default_bar); setPrompt(c.examples[1] ?? ""); }); }, []);
  const examples = cfg?.examples ?? [];
  const point = cfg?.held_out_curve.reduce<CurvePoint | null>((best, p) => (best === null || Math.abs(p.bar - (bar ?? 0)) < Math.abs(best.bar - (bar ?? 0)) ? p : best), null);
  const reasoning = cfg?.held_out["always REASONING"];

  const go = async () => {
    if (!prompt.trim()) return;
    setBusy(true); setError(null); setRes(null);
    try { setRes(await postJSON<AskResult>("/api/ask", { prompt, bar })); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };

  const calls: Extract<RunEvent, { type: "llm" }>[] = res ? [{
    type: "llm", t: 0, call: 1, asked: "oci-auto-trained", seconds: res.seconds, tokens: {}, tool_calls: [], text: "",
    ...res.route, fallbacks: res.route.fallbacks ?? 0, retries: res.route.retries ?? 0,
  }] : [];

  return (
    <div className="space-y-4">
      <Panel kicker="Ask anything" title="Type a request: the gateway picks the model and shows why">
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); }}
          className="w-full resize-y rounded-xl border border-line bg-paper px-4 py-3 text-[14px] leading-relaxed outline-none focus:border-oracle/60" />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={go} disabled={busy || !prompt.trim()}
            className="flex items-center gap-2 rounded-xl bg-oracle px-4 py-2 text-[13px] font-semibold text-white disabled:bg-ink-3">
            {busy ? <RotateCw className="size-4 animate-spin" /> : <CornerDownLeft className="size-4" />} Route it
          </button>
          <span className="text-[11.5px] text-ink-3">⌘↵ · try:</span>
          {examples.map((e) => (
            <button key={e} onClick={() => setPrompt(e)} className="max-w-[260px] truncate rounded-lg border border-line bg-panel px-2.5 py-1 text-[11.5px] text-ink-2 hover:border-oracle/50">{e}</button>
          ))}
        </div>
        {cfg && bar !== null && (
          <div className="mt-4 flex flex-wrap items-center gap-4 rounded-xl border border-line bg-paper px-4 py-3">
            <div className="text-[12px] font-semibold">Quality bar</div>
            <input type="range" min={0.5} max={0.95} step={0.05} value={bar} onChange={(e) => setBar(Number(e.target.value))} className="w-[240px] accent-[#c74634]" aria-label="quality bar" />
            <span className="font-mono text-[13px] font-semibold">{Math.round(bar * 100)}%</span>
            <span className="text-[11.5px] text-ink-3">{bar === cfg.default_bar ? "the bar chosen in training" : bar > cfg.default_bar ? "better answers, more spend" : "less spend"}</span>
            {point && reasoning && (
              <span className="ml-auto text-[11.5px] text-ink-2">
                on {cfg.held_out_prompts} unseen prompts at {Math.round(point.bar * 100)}%: <b>{Math.round(point.quality * 100)}%</b> good answers at {usd(point.cost_per_request)} a request
                · always reasoning: {Math.round(reasoning.quality * 100)}% at {usd(reasoning.cost_per_request)}
              </span>
            )}
          </div>
        )}
        {error && <div className="mt-3 rounded-lg bg-oracle-soft px-3 py-2 text-[12px] text-oracle">{error}</div>}
      </Panel>

      {(busy || res) && (
        <div className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-4">
          <div className="space-y-4">
            <Panel kicker="The route, live" title={res ? <span className="flex items-center gap-2"><RouteChip route={res.route.route} size="lg" /><ModelChip deployment={res.route.deployment} lit /></span> : "classifying…"}
              right={res && <span className="flex gap-3 font-mono text-[11.5px] text-ink-3"><span className={clsx(res.gateway_role === "fallback" && "text-ochre")}>via {res.gateway_role} gateway</span><span>{res.seconds}s</span><span>{usd(res.route.cost)}</span></span>}>
              <RouteMap calls={calls} classifying={busy} router="oci-auto-trained" />
            </Panel>
            {res && (
              <Panel kicker="The answer" title={`from ${shortModel(res.route.deployment)}`}>
                <p className="scroll-thin max-h-[340px] overflow-y-auto whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">{res.ok ? res.text : "the request failed"}</p>
              </Panel>
            )}
          </div>

          {res && (
            <div className="space-y-4">
              <Panel kicker="Why this route" title={<span className="flex items-center gap-2"><RouteChip route={res.why.decision.route} size="lg" /> {res.why.decision.criterion}</span>}>
                <p className="text-[14px] leading-relaxed text-ink">{res.why.summary}</p>
                {!res.agrees && (
                  <p className="mt-2 rounded-lg bg-ochre-soft px-3 py-2 text-[12px] text-ochre">
                    The gateway routed it to {res.route.route ?? "—"} ({res.route.cause ?? "no cause"}), not {res.why.decision.route}: its classifier answered differently or was unavailable.
                  </p>
                )}
                <ol className="mt-4 space-y-2">
                  {res.why.checks.map((c, i) => (
                    <li key={c.check} className="flex items-start gap-3">
                      <span className={clsx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full", c.fired ? "bg-oracle text-white" : "bg-sand text-ink-3")}>
                        {c.fired ? <Check className="size-3" /> : <Minus className="size-3" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[12.5px] font-semibold">{i + 1}. {CHECK_LABEL[c.check] ?? c.check} <span className="font-normal text-ink-3">{c.fired ? (c.check === "model" || c.check === "ladder" ? "decides" : "fires, decides") : "passes"}</span></div>
                        {c.check === "ladder" && c.steps
                          ? <LadderSteps steps={c.steps} bar={c.bar ?? 0.7} />
                          : c.check === "model" && Object.keys(res.why.decision.probabilities).length
                            ? <div className="mt-1.5"><Bars values={res.why.decision.probabilities} max={1} /></div>
                            : <div className="text-[12px] text-ink-3">{c.saw}</div>}
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="mt-4 border-t border-line/70 pt-3 text-[12.5px] leading-relaxed text-ink-2"><span className="font-semibold text-ink">What {res.why.decision.route} means: </span>{res.why.meaning}</p>
              </Panel>

              <Panel kicker="Precedent" title="The most similar requests in the training labels">
                <div className="space-y-3">
                  {res.why.precedent.map((p) => (
                    <div key={p.prompt} className="rounded-xl border border-line bg-paper px-3 py-2.5">
                      <div className="flex items-center gap-2 text-[11px] text-ink-3">
                        <RouteChip route={p.learned_as ?? p.label} /><span className="font-mono">similarity {p.similarity.toFixed(2)}</span>
                        {p.votes && <span className="font-mono">votes {p.votes.join(" · ")}</span>}
                        {p.source === "task type" && <span>labelled by task type</span>}
                      </div>
                      <p className="mt-1.5 text-[12.5px] leading-snug text-ink-2">{p.prompt}</p>
                      {p.tiers.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {p.tiers.map((t) => (
                            <span key={t.route} className={clsx("rounded-md border px-1.5 py-0.5 font-mono text-[10.5px]",
                              t.pass_rate >= 0.67 ? "border-moss/40 bg-moss-soft text-moss" : t.pass_rate > 0 ? "border-ochre/40 bg-ochre-soft text-ochre" : "border-oracle/30 bg-oracle-soft text-oracle")}>
                              {t.route} {shortModel(t.deployment)} passed {Math.round(t.pass_rate * 100)}%
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel kicker="Why this model" title={res.group || "—"}>
                <p className="text-[13px] leading-relaxed text-ink-2">{res.model_why}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {res.candidates.map((c) => <ModelChip key={c} deployment={c} lit={c === res.route.deployment} />)}
                </div>
              </Panel>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
