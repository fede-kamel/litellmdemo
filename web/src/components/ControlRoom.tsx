import clsx from "clsx";
import { ArrowRight, Calculator, CircleAlert, Cpu, FileSearch, Play, RotateCw, Sparkles, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ROUTE_STYLE, getJSON, postJSON, usd, type RunEvent, type Scenario } from "../api";
import { ModelChip, Panel, RouteChip } from "./bits";

const ROUTERS = [
  { id: "oci-auto-trained", label: "Trained classifier", note: "ours: rules + mini-trained model, 8 routes" },
  { id: "oci-auto-llm", label: "LLM classifier", note: "GPT-5 nano grades the request, 4 tiers" },
  { id: "oci-auto", label: "Built-in heuristic", note: "LiteLLM's local scorer, 4 tiers" },
];

type Call = Extract<RunEvent, { type: "llm" }> & { classify?: Extract<RunEvent, { type: "classify" }> };

export function ControlRoom({ onCall }: { onCall: () => void }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [prompt, setPrompt] = useState("");
  const [router, setRouter] = useState("oci-auto-trained");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [running, setRunning] = useState(false);
  const source = useRef<EventSource | null>(null);

  useEffect(() => { getJSON<Scenario[]>("/api/scenarios").then((s) => { setScenarios(s); setSelected(s[0]); setPrompt(s[0].prompt); }); }, []);
  const groups = useMemo(() => {
    const g: Record<string, Scenario[]> = {};
    scenarios.forEach((s) => (g[s.use_case] ??= []).push(s));
    return g;
  }, [scenarios]);

  const run = async () => {
    source.current?.close();
    setEvents([]);
    setRunning(true);
    const custom = !selected || prompt !== selected.prompt;
    try {
      const { id } = await postJSON<{ id: string }>("/api/runs", custom ? { prompt, router } : { scenario: selected!.id, router });
      const es = new EventSource(`/api/runs/${id}/stream`);
      source.current = es;
      es.onmessage = (m) => { const e = JSON.parse(m.data) as RunEvent; setEvents((v) => [...v, e]); if (e.type === "llm") onCall(); };
      es.addEventListener("end", () => { es.close(); setRunning(false); });
      es.onerror = () => { es.close(); setRunning(false); };
    } catch (err) {
      setEvents([{ type: "error", t: Date.now() / 1000, message: String(err) }]);
      setRunning(false);
    }
  };

  const calls: Call[] = [];
  let pending: Extract<RunEvent, { type: "classify" }> | undefined;
  for (const e of events) {
    if (e.type === "classify") pending = e;
    if (e.type === "llm") { calls.push({ ...e, classify: pending }); pending = undefined; }
  }
  const answer = events.find((e) => e.type === "answer") as Extract<RunEvent, { type: "answer" }> | undefined;
  const error = events.find((e) => e.type === "error") as Extract<RunEvent, { type: "error" }> | undefined;
  const spend = calls.reduce((s, c) => s + (c.cost ?? 0), 0);
  const fixedModel = selected?.model && prompt === selected.prompt;

  return (
    <div className="grid grid-cols-[320px_minmax(0,1fr)] gap-5">
      <aside className="space-y-4">
        <Panel kicker="Use cases" title="Pick a request">
          <div className="scroll-thin -mx-1 max-h-[560px] space-y-3 overflow-y-auto px-1">
            {Object.entries(groups).map(([use, list]) => (
              <div key={use}>
                <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-3">{use}</div>
                <div className="space-y-1">
                  {list.map((s) => (
                    <button key={s.id} onClick={() => { setSelected(s); setPrompt(s.prompt); }}
                      className={clsx("flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[12.5px] transition",
                        selected?.id === s.id ? "border-oracle/50 bg-oracle-soft/50" : "border-transparent hover:bg-sand")}>
                      <span className="flex-1">{s.title}</span>
                      {ROUTE_STYLE[s.expect] ? <RouteChip route={s.expect} /> : <span className="text-[10.5px] text-ink-3">{s.expect}</span>}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </aside>

      <div className="min-w-0 space-y-4">
        <Panel kicker="Request" title={selected ? `${selected.use_case}: ${selected.title}` : "Your request"}
          right={selected?.image ? <span className="rounded-md bg-ochre-soft px-2 py-0.5 text-[11px] font-semibold text-ochre">+ invoice image</span> : null}>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!running) run(); } }}
            className="w-full resize-y rounded-xl border border-line bg-paper px-3.5 py-2.5 text-[13.5px] leading-relaxed outline-none focus:ring-4 focus:ring-sand" />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {fixedModel ? (
              <span className="rounded-lg border border-line bg-sand px-3 py-1.5 text-[12px] text-ink-2">
                asks <span className="font-mono font-semibold">{selected?.model}</span>{selected?.tags ? <> with tag <span className="font-mono font-semibold">{selected.tags.join(",")}</span></> : null}
              </span>
            ) : ROUTERS.map((r) => (
              <button key={r.id} onClick={() => setRouter(r.id)} title={r.note}
                className={clsx("rounded-lg border px-3 py-1.5 text-[12px] font-medium", router === r.id ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}>
                {r.label} <span className="font-mono text-[10.5px] opacity-70">{r.id}</span>
              </button>
            ))}
            <button onClick={run} disabled={running || !prompt.trim()}
              className={clsx("ml-auto flex items-center gap-2 rounded-xl px-5 py-2 text-[13px] font-semibold text-white", running ? "bg-ink-3" : "bg-oracle hover:bg-[#b23d2d]")}>
              {running ? <RotateCw className="size-4 animate-spin" /> : <Play className="size-4" />}{running ? "Routing…" : "Run through the gateway"}
            </button>
          </div>
          <div className="mt-2 text-[11px] text-ink-3">The agent (langchain-oci <span className="font-mono">create_oci_agent</span>) asks the gateway for a model group, never a vendor model. Enter runs; Shift+Enter for a new line.</div>
        </Panel>

        <Panel kicker="Route trace" title={calls.length ? `${calls.length} model call${calls.length > 1 ? "s" : ""}, each routed by the gateway` : "Every model call, as the gateway routed it"}
          right={calls.length ? <span className="font-mono text-[12px] text-ink-2">spend {usd(spend)}</span> : null}>
          {!calls.length && !running && !error && <div className="rounded-xl border border-dashed border-line p-8 text-center text-[13px] text-ink-3">Run a request: each step the agent takes appears here with the route, the criterion that decided it, the OCI model that answered, and what it cost.</div>}
          {running && !calls.length && <div className="flex items-center gap-2 text-[13px] text-ink-3"><Sparkles className="size-4 animate-pulse text-oracle" /> classifying and routing…</div>}
          <div className="space-y-3">
            {events.map((e, i) => {
              if (e.type === "llm") {
                const c = calls.find((x) => x.call === e.call)!;
                return <CallCard key={i} c={c} />;
              }
              if (e.type === "tool") return (
                <div key={i} className="ml-6 flex items-center gap-2 text-[12px] text-ink-2">
                  {e.name === "calculate" ? <Calculator className="size-3.5 text-ink-3" /> : e.name === "lookup_policy" ? <FileSearch className="size-3.5 text-ink-3" /> : <Wrench className="size-3.5 text-ink-3" />}
                  tool <span className="font-mono font-semibold">{e.name}</span> <span className="font-mono text-ink-3">{e.input}</span>
                </div>
              );
              if (e.type === "tool_result") return <div key={i} className="ml-12 line-clamp-2 font-mono text-[11px] text-ink-3">→ {e.output}</div>;
              return null;
            })}
          </div>
          {error && <div className="mt-3 flex items-center gap-2 rounded-lg border border-oracle/40 bg-oracle-soft px-3 py-2 text-[12.5px] text-oracle"><CircleAlert className="size-4" /> {error.message}</div>}
          {answer && (
            <div className="mt-4 rounded-xl border border-moss/30 bg-moss-soft/40 p-4">
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-moss">Answer · {answer.seconds}s · {answer.calls} routed calls</div>
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">{answer.text}</p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function CallCard({ c }: { c: Call }) {
  const route = c.route ?? c.classify?.route;
  const probs = c.classify?.probabilities ?? {};
  const top = Object.entries(probs).slice(0, 3);
  return (
    <div className="rounded-xl border border-line bg-paper/60 p-3.5">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className="grid size-6 place-items-center rounded-full bg-ink text-[11px] font-semibold text-white">{c.call}</span>
        <span className="font-mono text-ink-3">asked</span><span className="font-mono font-semibold">{c.asked}</span>
        <ArrowRight className="size-3.5 text-ink-3" />
        {route ? <RouteChip route={route} size="lg" /> : <span className="font-mono font-semibold">{c.group}</span>}
        <ArrowRight className="size-3.5 text-ink-3" />
        <ModelChip deployment={c.deployment} lit />
        {c.fallbacks > 0 && <span className="rounded-md bg-ochre-soft px-1.5 py-0.5 text-[10.5px] font-semibold text-ochre">fallback ×{c.fallbacks}</span>}
        {c.retries > 0 && <span className="rounded-md bg-ochre-soft px-1.5 py-0.5 text-[10.5px] font-semibold text-ochre">retry ×{c.retries}</span>}
        <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-ink-3">
          <span><Cpu className="mr-1 inline size-3" />{c.seconds}s</span><span>{usd(c.cost)}</span>
          <span>{c.tokens?.in ?? "–"}→{c.tokens?.out ?? "–"} tok</span>
        </span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-ink-3">
        <span>decided by <span className="font-semibold text-ink-2">{c.classify ? c.classify.criterion : c.cause ?? "the gateway"}</span>
          {c.classify ? <> in {c.classify.milliseconds} ms</> : null}</span>
        {top.length > 0 && <span className="font-mono">{top.map(([k, v]) => `${k} ${Math.round(v * 100)}%`).join(" · ")}</span>}
        {c.group && c.group !== c.asked && <span>group <span className="font-mono text-ink-2">{c.group}</span></span>}
        {c.tool_calls.length > 0 && <span>→ calls <span className="font-mono text-ink-2">{c.tool_calls.join(", ")}</span></span>}
      </div>
    </div>
  );
}
