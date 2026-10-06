import clsx from "clsx";
import { ArrowRight, Box, Check, ChevronDown, CornerDownLeft, ImagePlus, KeyRound, Lock, RotateCw, Route as RouteIcon, ShieldAlert, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ROUTE_STYLE, getJSON, postJSON, shortModel, usd, vendor, type RunEvent, type Scenario } from "../api";
import { ModelChip, Panel, RouteChip } from "./bits";
import { RouteMap } from "./RouteMap";

type Step = { route: string; pass: number; cost: number; clears: boolean; chosen: boolean };
type Check_ = { check: string; fired: boolean; saw: string; bar?: number; steps?: Step[] };
type Tier = { route: string; deployment?: string; pass_rate: number };
type Precedent = { prompt: string; similarity: number; label: string; learned_as?: string; votes?: string[]; tiers: Tier[] };
type CurvePoint = { bar: number; quality: number; cost_per_request: number };
type AskConfig = { examples: string[]; default_bar: number; held_out_curve: CurvePoint[];
  held_out: Record<string, { quality: number; cost_per_request: number }>; held_out_prompts: number };
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Ev = Record<string, any> & { type: string };
type Key = { key_alias: string; models: string[]; max_budget: number; spend: number; rpm_limit: number };
type Sandbox = { ready: boolean; name: string; gateway: string; cluster?: string; key: Key | null };

/** Read an image file and shrink it to at most 1600 px on the long side, as JPEG: small enough to send anywhere. */
function toDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
      c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

const NAMES: Record<string, string> = { SIMPLE: "fast", MEDIUM: "balanced", COMPLEX: "strong", REASONING: "reasoning" };
const CHECK_LABEL: Record<string, string> = { image: "Image rule", length: "Length rule", language: "Language rule", code: "Code check", ladder: "Quality ladder" };

/** Each route, cheapest first: its chance of a good answer, against the bar. */
function Ladder({ steps, bar }: { steps: Step[]; bar: number }) {
  return (
    <div className="space-y-1.5">
      {steps.map((s) => (
        <div key={s.route} className="flex items-center gap-2 text-[11.5px]">
          <span className="w-[92px] shrink-0"><RouteChip route={s.route} /></span>
          <div className="relative h-2.5 flex-1 rounded-full bg-sand">
            <div className={clsx("h-2.5 rounded-full", s.chosen ? "bg-oracle" : s.clears ? "bg-moss/60" : "bg-ink-3/40")} style={{ width: `${s.pass * 100}%` }} />
            <div className="absolute -top-1 h-[18px] w-0.5 bg-ink" style={{ left: `${bar * 100}%` }} />
          </div>
          <span className="w-9 text-right font-mono text-ink-2">{Math.round(s.pass * 100)}%</span>
          <span className={clsx("w-[58px] text-[10.5px] font-semibold", s.chosen ? "text-oracle" : "text-ink-3")}>{s.chosen ? "chosen" : s.clears ? "clears" : "below bar"}</span>
        </div>
      ))}
    </div>
  );
}

function Stage({ n, title, sub, state, children }: { n: number; title: string; sub: string; state: "idle" | "active" | "done"; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className={clsx("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold",
        state === "done" ? "bg-oracle text-white" : state === "active" ? "bg-oracle-soft text-oracle ring-2 ring-oracle/40" : "bg-sand text-ink-3")}>
        {state === "done" ? <Check className="size-3.5" /> : state === "active" ? <RotateCw className="size-3 animate-spin" /> : n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-semibold">{title} <span className="font-normal text-ink-3">· {sub}</span></div>
        <div className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{children}</div>
      </div>
    </li>
  );
}

export function Ask() {
  const [cfg, setCfg] = useState<AskConfig | null>(null);
  const [sb, setSb] = useState<Sandbox | null>(null);
  const [bar, setBar] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const attach = async (f?: File | null) => { if (f && f.type.startsWith("image/")) setImage(await toDataUrl(f)); };
  const [events, setEvents] = useState<Ev[]>([]);
  const [running, setRunning] = useState(false);
  const [details, setDetails] = useState(false);
  const [probe, setProbe] = useState<null | "running" | { tries: { target: string; result: string }[] }>(null);
  const es = useRef<EventSource | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [picked, setPicked] = useState<Scenario | null>(null);

  useEffect(() => {
    getJSON<AskConfig>("/api/ask/config").then((c) => { setCfg(c); setBar(c.default_bar); setPrompt(c.examples[1] ?? ""); });
    getJSON<Sandbox>("/api/sandbox").then(setSb).catch(() => setSb(null));
    getJSON<Scenario[]>("/api/scenarios").then(setScenarios).catch(() => undefined);
  }, []);
  const groups = scenarios.reduce<Record<string, Scenario[]>>((g, x) => ((g[x.use_case] ??= []).push(x), g), {});
  const pick = async (x: Scenario) => {
    setPicked(x); setPrompt(x.prompt);
    if (x.image) { const b = await (await fetch("/api/sample-image")).blob(); setImage(await toDataUrl(new File([b], "invoice.png", { type: b.type }))); }
    else setImage(null);
  };

  const go = async () => {
    if ((!prompt.trim() && !image) || running) return;
    es.current?.close();
    setEvents([]); setRunning(true); setDetails(false);
    // A use case runs exactly as defined (its model group, tags, image); anything typed runs as typed.
    const body = picked && prompt === picked.prompt ? { scenario: picked.id, bar, runtime: "openshell" }
      : { prompt, bar, runtime: "openshell", image: image ?? undefined };
    const { id } = await postJSON<{ id: string }>("/api/runs", body);
    const src = new EventSource(`/api/runs/${id}/stream`);
    es.current = src;
    src.onmessage = (m) => { const e = JSON.parse(m.data) as Ev; if (e.type) setEvents((v) => [...v, e]); };
    src.addEventListener("end", () => { src.close(); setRunning(false); getJSON<Sandbox>("/api/sandbox").then(setSb).catch(() => undefined); });
    src.onerror = () => { src.close(); setRunning(false); };
  };
  const escape = async () => { setProbe("running"); setProbe(await postJSON("/api/sandbox/probe", {})); };

  const runtimeEv = events.find((e) => e.type === "runtime" && e.runtime === "host") ?? events.find((e) => e.type === "runtime");
  const calls = events.filter((e) => e.type === "llm");
  const first = calls[0];
  const decision = events.find((e) => e.type === "classify");
  const why = events.find((e) => e.type === "explain" && !e.error);
  const answer = events.find((e) => e.type === "answer");
  const error = events.find((e) => e.type === "error");
  const net = events.find((e) => e.type === "sandbox_net")?.events as { verdict: string; destination: string }[] | undefined;
  const key = (events.find((e) => e.type === "key") as Key | undefined) ?? sb?.key ?? undefined;
  const failover = events.find((e) => e.type === "failover");
  const replay = events.find((e) => e.type === "replay");
  const spend = calls.reduce((a, c) => a + (c.cost ?? 0), 0);
  const plan = events.find((e) => e.type === "plan")?.steps as { step: number; title: string; instruction: string }[] | undefined;
  const planned = plan || events.some((e) => e.type === "llm" && e.step === 0);
  const ladder = (why?.checks as Check_[] | undefined)?.find((c) => c.check === "ladder");
  const st = (done: boolean, active: boolean) => (done ? "done" : running && active ? "active" : "idle") as "idle" | "active" | "done";
  const point = cfg?.held_out_curve.reduce<CurvePoint | null>((b, p) => (b === null || Math.abs(p.bar - (bar ?? 0)) < Math.abs(b.bar - (bar ?? 0)) ? p : b), null);
  const reasoning = cfg?.held_out["always REASONING"];

  return (
    <div className="space-y-4">
      <Panel kicker="Ask anything" title="Type a request. The agent runs in an OpenShell sandbox; LiteLLM picks the model and says why.">
        <div className="flex gap-3" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); attach(e.dataTransfer.files?.[0]); }}>
          <textarea value={prompt} onChange={(e) => { setPrompt(e.target.value); if (picked && e.target.value !== picked.prompt) setPicked(null); }} rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); }}
            onPaste={(e) => { const f = [...e.clipboardData.files].find((x) => x.type.startsWith("image/")); if (f) { e.preventDefault(); attach(f); } }}
            placeholder="Type a request; paste, drop or attach an image for a multimodal one"
            className="w-full resize-y rounded-xl border border-line bg-paper px-4 py-3 text-[14px] leading-relaxed outline-none focus:border-oracle/60" />
          {image && (
            <div className="relative shrink-0">
              <img src={image} alt="attached" className="h-[86px] w-auto rounded-xl border border-line object-cover" />
              <button onClick={() => setImage(null)} className="absolute -right-2 -top-2 grid size-5 place-items-center rounded-full bg-ink text-white" title="remove the image"><X className="size-3" /></button>
            </div>
          )}
        </div>
        <input ref={fileInput} type="file" accept="image/*" className="hidden" onChange={(e) => { attach(e.target.files?.[0]); e.target.value = ""; }} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button onClick={go} disabled={running || (!prompt.trim() && !image)} className="flex items-center gap-2 rounded-xl bg-oracle px-4 py-2 text-[13px] font-semibold text-white disabled:bg-ink-3">
            {running ? <RotateCw className="size-4 animate-spin" /> : <CornerDownLeft className="size-4" />} Route it
          </button>
          <button onClick={() => fileInput.current?.click()} className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-2 text-[12.5px] font-semibold text-ink-2 hover:border-oracle/50">
            <ImagePlus className="size-4" /> Image
          </button>
          <button onClick={async () => { const r = await fetch("/api/sample-image"); const b = await r.blob(); attach(new File([b], "invoice.png", { type: b.type })); setPrompt("Read this invoice: what is the total due and when is it due?"); }}
            className="rounded-lg border border-line bg-panel px-2.5 py-1 text-[11.5px] text-ink-2 hover:border-oracle/50">sample: an invoice photo</button>
          <span className="text-[11.5px] text-ink-3">try:</span>
          {cfg?.examples.map((e) => <button key={e} onClick={() => setPrompt(e)} className="max-w-[230px] truncate rounded-lg border border-line bg-panel px-2.5 py-1 text-[11.5px] text-ink-2 hover:border-oracle/50">{e}</button>)}
        </div>
        {scenarios.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="text-[11.5px] font-semibold text-ink-2">Use cases:</span>
            {Object.entries(groups).map(([uc, list]) => (
              <span key={uc} className="flex items-center gap-1">
                <span className="text-[10.5px] uppercase tracking-wide text-ink-3">{uc}</span>
                {list.map((x) => (
                  <button key={x.id} onClick={() => pick(x)} title={x.prompt.slice(0, 300)}
                    className={clsx("rounded-lg border px-2 py-0.5 text-[11.5px]", picked?.id === x.id ? "border-oracle bg-oracle-soft text-oracle" : "border-line bg-panel text-ink-2 hover:border-oracle/50")}>
                    {x.title}
                  </button>
                ))}
              </span>
            ))}
          </div>
        )}
        {cfg && bar !== null && (
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[12px]">
            <span className="font-semibold">Quality bar</span>
            <input type="range" min={0.5} max={0.95} step={0.05} value={bar} onChange={(e) => setBar(Number(e.target.value))} className="w-[200px] accent-[#c74634]" aria-label="quality bar" />
            <span className="font-mono font-semibold">{Math.round(bar * 100)}%</span>
            <span className="text-ink-3">{bar === cfg.default_bar ? "(chosen in training)" : bar > cfg.default_bar ? "better answers, more spend" : "less spend"}</span>
            {point && reasoning && <span className="ml-auto text-ink-3">on {cfg.held_out_prompts} unseen prompts: <b className="text-ink">{Math.round(point.quality * 100)}%</b> good answers at {usd(point.cost_per_request)} a request · always reasoning {Math.round(reasoning.quality * 100)}% at {usd(reasoning.cost_per_request)}</span>}
          </div>
        )}
      </Panel>

      {/* the path of one request, left to right */}
      <div className="grid grid-cols-[1fr_auto_1.35fr_auto_0.8fr] items-stretch gap-3">
        <section className="rounded-2xl border-2 border-[#76b900]/50 bg-panel p-4">
          <div className="flex items-center gap-2"><Box className="size-4 text-[#5f8f00]" /><span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#5f8f00]">1 · OpenShell sandbox</span></div>
          <div className="mt-1 text-[14px] font-semibold">The agent runs here</div>
          <div className="text-[11.5px] text-ink-3">langchain-oci agent · sandbox <span className="font-mono">{sb?.name ?? "litellmdemo-agent"}</span>{sb ? (sb.ready ? " · ready" : " · not running") : ""}</div>
          <ul className="mt-3 space-y-1.5 text-[12.5px]">
            <li className="flex gap-2"><Lock className="mt-0.5 size-3.5 shrink-0 text-ink-3" /><span><b>No OCI credential, no model key.</b> Its LiteLLM key is a placeholder; OpenShell swaps in the real one on the way to the gateway.</span></li>
            <li className="flex gap-2"><ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-ink-3" /><span><b>Can reach one place:</b> the LiteLLM gateway, <span className="font-mono">POST /v1/chat/completions</span>.</span></li>
          </ul>
          <div className="mt-3 rounded-lg bg-sand/60 p-2 font-mono text-[10.5px] leading-relaxed">
            {runtimeEv?.runtime === "host" && <div className="text-ochre">ran on the host: the sandbox was unavailable</div>}
            {!net && running && <div className="text-ink-3">running in the sandbox…</div>}
            {!net && !running && <div className="text-ink-3">the sandbox's network decisions appear here</div>}
            {net?.slice(-5).map((n, i) => <div key={i} className={n.verdict === "DENIED" ? "text-oracle" : "text-moss"}>{n.verdict === "DENIED" ? "✕ DENIED " : "✓ ALLOWED"} {n.destination.replace("http://", "")}</div>)}
          </div>
          <button onClick={escape} disabled={probe === "running"} className="mt-2 w-full rounded-lg border border-line px-2 py-1 text-[11.5px] font-semibold text-ink-2 hover:border-oracle/50">
            {probe === "running" ? "trying…" : "Try to escape: call OCI or OpenAI directly"}
          </button>
          {probe && probe !== "running" && (
            <div className="mt-2 space-y-0.5 text-[11px]">
              {probe.tries.map((t) => <div key={t.target} className={t.result.startsWith("REFUSED") ? "text-oracle" : "text-ochre"}>✕ {t.target}: {t.result}</div>)}
            </div>
          )}
        </section>
        <div className="grid place-items-center text-ink-3"><ArrowRight className="size-6" /></div>

        <section className="rounded-2xl border-2 border-indigo/40 bg-[#f3f2fb] p-4">
          <div className="flex items-center gap-2"><RouteIcon className="size-4 text-indigo" /><span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-indigo">2 · LiteLLM AI Gateway</span></div>
          <div className="mt-1 text-[14px] font-semibold">Decides, routes and signs every call</div>
          <div className="text-[11.5px] text-ink-3">LiteLLM 1.104 on {sb?.cluster === "oke" ? "OKE" : "Kubernetes on this laptop (Rancher Desktop)"} · complexity router with our classifier plugin</div>
          <ol className="mt-3 space-y-3">
            <Stage n={1} title="Key check" sub="virtual key" state={st(!!first, true)}>
              {key ? <><KeyRound className="mr-1 inline size-3.5 text-ink-3" /><span className="font-mono">{key.key_alias}</span>: may call {key.models?.length ?? "?"} model groups only · {usd(key.spend)} of ${key.max_budget} spent · {key.rpm_limit} requests a minute</> : "LiteLLM checks the agent's key: which models, what budget, what rate."}
            </Stage>
            <Stage n={2} title="Classify" sub="complexity router → classifier_type: custom" state={st(!!decision, !decision)}>
              {decision ? <span className="flex flex-wrap items-center gap-1.5"><RouteChip route={decision.route} />
                {decision.criterion === "ladder"
                  ? <>the {NAMES[decision.route] ?? decision.route} models are {Math.round((decision.probabilities?.[decision.route] ?? 0) * 100)}% likely to give a good answer (bar {Math.round((decision.details?.bar ?? 0) * 100)}%) · {Math.round(decision.milliseconds ?? 0)} ms</>
                  : <>{decision.criterion}</>}
              </span> : "Our trained classifier, called by LiteLLM, picks the route."}
            </Stage>
            <Stage n={3} title="Route" sub="model group → deployment" state={st(!!first, !!decision && !first)}>
              {first ? <><span className="font-mono">{first.group === "oci-auto-trained" ? `${first.route}` : first.group}</span> → <span className="font-mono">{shortModel(first.deployment)}</span>{first.fallbacks ? <span className="text-ochre"> · after {first.fallbacks} fallback(s)</span> : " · the fastest healthy deployment"}{calls.length > 1 ? ` · ${calls.length} calls in this run` : ""}</> : "The route names a model group; LiteLLM picks its fastest healthy deployment, with fallbacks."}
            </Stage>
            <Stage n={4} title="Sign" sub="OCI request signing" state={st(!!first, !!decision && !first)}>
              {sb?.cluster === "oke"
                ? "The gateway signs as its OKE node (instance principal). No OCI key exists in the cluster, or in the sandbox."
                : "The gateway signs with the operator's OCI session, a one-hour token kept fresh in a Kubernetes Secret. The sandbox holds no OCI credential."}
            </Stage>
            <Stage n={5} title="Account" sub="cost and spend" state={st(!!answer, !!first && !answer)}>
              {first ? <>this run {usd(spend)}, charged to the agent's key · every decision returned in <span className="font-mono">x-litellm-*</span> headers</> : "Cost per call, spend per key."}
            </Stage>
          </ol>
        </section>
        <div className="grid place-items-center text-ink-3"><ArrowRight className="size-6" /></div>

        <section className="rounded-2xl border-2 border-oracle/40 bg-[#fdf4f2] p-4">
          <div className="flex items-center gap-2"><Sparkles className="size-4 text-oracle" /><span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle">3 · OCI Generative AI</span></div>
          <div className="mt-1 text-[14px] font-semibold">The model that answered</div>
          <div className="text-[11.5px] text-ink-3">us-chicago-1 · 20 models, 5 vendors</div>
          <div className="mt-4 space-y-3">
            {calls.length ? [...new Set(calls.map((c) => c.deployment as string))].map((d) => (
              <div key={d}><ModelChip deployment={d} lit /><div className="mt-1 text-[11px] text-ink-3">{vendor(d)} · {calls.filter((c) => c.deployment === d).length} call(s)</div></div>
            )) : <div className="text-[12px] text-ink-3">{running ? "waiting for the route…" : "—"}</div>}
          </div>
        </section>
      </div>

      {planned && (
        <Panel kicker="The plan" title={plan ? `${plan.length} tasks, each routed by LiteLLM on its own` : "planning…"}
          right={plan ? <span className="font-mono text-[11.5px] text-ink-3">{new Set(calls.map((c) => c.deployment)).size} models · {usd(spend)}</span> : null}>
          <ol data-testid="plan" className="space-y-2">
            {[{ step: 0, title: "Plan the work", instruction: "Split the request into tasks." }, ...(plan ?? [])].map((st) => {
              const sc = calls.filter((c) => c.step === st.step);
              const done = st.step === 0 ? !!plan : events.some((e) => e.type === "step_done" && e.step === st.step);
              const active = !done && (sc.length > 0 || events.some((e) => e.type === "step" && e.step === st.step));
              return (
                <li key={st.step} className={clsx("grid grid-cols-[28px_1fr_auto] items-start gap-3 rounded-lg border px-3 py-2",
                  active ? "border-indigo/50 bg-indigo/5" : "border-line bg-paper")}>
                  <span className={clsx("grid size-6 place-items-center rounded-full text-[11px] font-semibold",
                    done ? "bg-moss text-white" : active ? "bg-indigo text-white" : "bg-sand text-ink-3")}>{done ? <Check className="size-3.5" /> : st.step}</span>
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-ink">{st.title}</div>
                    <div className="truncate text-[11.5px] text-ink-3" title={st.instruction}>{st.instruction}</div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-1.5">
                    {[...new Set(sc.map((c) => c.route ?? c.group))].map((r) => <RouteChip key={r} route={r} />)}
                    {[...new Set(sc.map((c) => c.deployment as string))].map((d) => <ModelChip key={d} deployment={d} />)}
                    {sc.length > 0 && <span className="font-mono text-[11px] text-ink-3">{sc.length} call{sc.length > 1 ? "s" : ""} · {usd(sc.reduce((a, c) => a + (c.cost ?? 0), 0))}</span>}
                    {!sc.length && <span className="text-[11px] text-ink-3">{active ? "routing…" : "waiting"}</span>}
                  </div>
                </li>
              );
            })}
          </ol>
        </Panel>
      )}

      {(calls.length > 0 || running) && (
        <Panel kicker="This run" title={calls.length ? `${calls.length} model call${calls.length > 1 ? "s" : ""}, each routed by LiteLLM` : "routing…"}
          right={calls.length ? <span className="font-mono text-[11.5px] text-ink-3">{usd(spend)}</span> : null}>
          <RouteMap router={picked?.model ?? "oci-auto-trained"} classifying={running && !answer}
            calls={calls.map((c) => ({ ...c, route: c.route ?? Object.entries(ROUTE_STYLE).find(([, v]) => v.group === c.group)?.[0] })) as Extract<RunEvent, { type: "llm" }>[]} />
          <ol className="mx-auto mt-4 grid max-w-[1100px] grid-cols-2 gap-x-6 gap-y-1.5">
            {events.filter((e) => e.type === "llm" || e.type === "tool").map((e, i) => e.type === "llm" ? (
              <li key={i} className="flex flex-wrap items-center gap-1.5 text-[12px]">
                <span className="grid size-5 place-items-center rounded-full bg-ink text-[10px] font-semibold text-white">{e.call}</span>
                {planned && e.step !== undefined && <span className="font-mono text-[10.5px] text-ink-3">{e.step === 0 ? "plan" : `task ${e.step}`}</span>}
                {e.route ? <RouteChip route={e.route} /> : <span className="font-mono">{e.group}</span>}
                <ArrowRight className="size-3 text-ink-3" /><ModelChip deployment={e.deployment} />
                <span className="font-mono text-[11px] text-ink-3">{e.seconds}s · {usd(e.cost)}{e.fallbacks ? ` · fallback ×${e.fallbacks}` : ""}</span>
              </li>
            ) : (
              <li key={i} className="pl-7 font-mono text-[11px] text-ink-3">tool {e.name} {String(e.input).slice(0, 80)}</li>
            ))}
          </ol>
        </Panel>
      )}

      {replay && <div className="rounded-xl border-2 border-ochre/60 bg-ochre-soft px-4 py-2 text-[13px] font-semibold text-ochre">REPLAY · a recorded run of this request ({replay.recorded_at}). The live path did not answer: check the network or run scripts/preflight.sh.</div>}
      {failover && <div className="rounded-xl border border-ochre/40 bg-ochre-soft px-4 py-2 text-[12.5px] text-ochre">{failover.from} did not answer; the run moved to {failover.to}.</div>}
      {error && <div className="rounded-xl border border-oracle/40 bg-oracle-soft px-4 py-2 text-[12.5px] text-oracle">{error.message}</div>}

      {(answer || why) && (
        <div className="grid grid-cols-[1.2fr_1fr] gap-4">
          <Panel kicker="The answer" title={first ? `from ${shortModel(calls[calls.length - 1]?.deployment)}` : ""} right={answer && <span className="font-mono text-[11.5px] text-ink-3">{answer.seconds}s · {usd(spend)}</span>}>
            <p className="scroll-thin max-h-[360px] overflow-y-auto whitespace-pre-wrap text-[13px] leading-relaxed text-ink-2">{answer?.text}</p>
          </Panel>
          <Panel kicker={planned ? "Why the planner's model" : "Why this model"} title={decision ? <span className="flex items-center gap-2"><RouteChip route={decision.route} size="lg" /> decided inside LiteLLM</span> : ""}>
            {why && <p className="text-[14px] leading-relaxed text-ink">{why.summary}</p>}
            {ladder?.steps && <div className="mt-3"><Ladder steps={ladder.steps} bar={ladder.bar ?? 0.7} /></div>}
            <button onClick={() => setDetails(!details)} className="mt-3 flex items-center gap-1 text-[12px] font-semibold text-indigo">
              <ChevronDown className={clsx("size-4 transition", details && "rotate-180")} /> {details ? "Hide" : "Show"} the details: every check, precedent, each call
            </button>
            {details && why && (
              <div className="mt-3 space-y-4 border-t border-line/70 pt-3">
                <ol className="space-y-1">
                  {(why.checks as Check_[]).filter((c) => c.check !== "ladder").map((c, i) => (
                    <li key={c.check} className="text-[12px]"><b>{i + 1}. {CHECK_LABEL[c.check] ?? c.check}</b> <span className="text-ink-3">{c.fired ? "decides" : "passes"} · {c.saw}</span></li>
                  ))}
                </ol>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Most similar requests in the training labels</div>
                  {(why.precedent as Precedent[]).map((p) => (
                    <div key={p.prompt} className="mt-2 rounded-lg border border-line bg-paper px-3 py-2 text-[12px]">
                      <div className="flex items-center gap-2 text-[10.5px] text-ink-3"><RouteChip route={p.learned_as ?? p.label} /> similarity {p.similarity.toFixed(2)}</div>
                      <div className="mt-1 text-ink-2">{p.prompt}</div>
                      <div className="mt-1 flex flex-wrap gap-1">{p.tiers.map((t) => <span key={t.route} className={clsx("rounded px-1 font-mono text-[10px]", t.pass_rate >= 0.67 ? "bg-moss-soft text-moss" : t.pass_rate > 0 ? "bg-ochre-soft text-ochre" : "bg-oracle-soft text-oracle")}>{NAMES[t.route] ?? t.route} passed {Math.round(t.pass_rate * 100)}%</span>)}</div>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">Every model call in this run</div>
                  {calls.map((c) => <div key={c.call} className="mt-1 font-mono text-[11px] text-ink-2">call {c.call}: {c.route ?? c.group} → {shortModel(c.deployment)} · {usd(c.cost)}{c.tool_calls?.length ? ` · asked for ${c.tool_calls.join(", ")}` : ""}</div>)}
                </div>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
