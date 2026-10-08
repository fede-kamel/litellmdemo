import clsx from "clsx";
import { ArrowRight, Box, ChevronDown, CornerDownLeft, ImagePlus, KeyRound, ListTree, Lock, Map as MapIcon, RotateCw, Route as RouteIcon, Sparkles, Split, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ROUTE_STYLE, getJSON, postJSON, usd, type RunEvent, type Scenario } from "../api";
import { Answer, ModelChip, Panel, RouteChip } from "./bits";
import { RouteMap } from "./RouteMap";
import { Ladder, NAMES, Timeline, summary, type Ev, type Step } from "./Timeline";

type Check_ = { check: string; fired: boolean; saw: string; bar?: number; steps?: Step[] };
type Tier = { route: string; deployment?: string; pass_rate: number };
type Precedent = { prompt: string; similarity: number; label: string; learned_as?: string; votes?: string[]; tiers: Tier[] };
type CurvePoint = { bar: number; quality: number; cost_per_request: number };
type AskConfig = { examples: string[]; default_bar: number; held_out_curve: CurvePoint[];
  held_out: Record<string, { quality: number; cost_per_request: number }>; held_out_prompts: number };
type Key = { key_alias: string; models: string[]; max_budget: number; spend: number; rpm_limit: number };
type Sandbox = { ready: boolean; name: string; gateway: string; cluster?: string; key: Key | null };
type Mode = "single" | "plan";
type UseCase = Scenario & { shows?: string; mode?: Mode };

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

const CHECK_LABEL: Record<string, string> = { image: "Image rule", length: "Length rule", language: "Language rule", code: "Code check", ladder: "Quality ladder" };

/** The three places a request passes through, as one compact strip; details on click. */
function PathStrip({ sb, net, vkey: key, events, running, probe, escape }: {
  sb: Sandbox | null; net?: { verdict: string; destination: string }[]; vkey?: Key; events: Ev[]; running: boolean;
  probe: null | "running" | { tries: { target: string; result: string }[] }; escape: () => void;
}) {
  const [open, setOpen] = useState(false);
  const calls = events.filter((e) => e.type === "llm");
  const host = events.find((e) => e.type === "runtime" && e.runtime === "host");
  const models = [...new Set(calls.map((c) => c.deployment as string))];
  const allowed = net?.filter((n) => n.verdict !== "DENIED").length ?? 0, denied = net?.filter((n) => n.verdict === "DENIED").length ?? 0;
  const card = "rounded-xl border-2 bg-panel px-3.5 py-2.5";
  return (
    <section className="rounded-2xl border border-line bg-panel p-3">
      <div className="grid grid-cols-[1fr_auto_1.15fr_auto_1fr] items-stretch gap-2">
        <div className={clsx(card, "border-[#76b900]/50")}>
          <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-[#9be15d]"><Box className="size-3.5" />OpenShell sandbox</div>
          <div className="mt-0.5 text-[12.5px] font-semibold">The agent runs here, with no key</div>
          <div className="text-[11.5px] text-ink-3">{host ? <span className="text-ochre">this run: on the host (sandbox unavailable)</span>
            : net ? `${allowed} allowed${denied ? ` · ${denied} refused` : ""} · only the gateway is reachable`
            : running ? "running in the sandbox…" : `sandbox ${sb?.name ?? "litellmdemo-agent"}${sb ? (sb.ready ? " · ready" : " · not running") : ""}`}</div>
        </div>
        <div className="grid place-items-center text-ink-3"><ArrowRight className="size-5" /></div>
        <div className={clsx(card, "border-indigo/40 bg-indigo-soft/40")}>
          <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-indigo"><RouteIcon className="size-3.5" />LiteLLM AI Gateway</div>
          <div className="mt-0.5 text-[12.5px] font-semibold">Checks the key, classifies, routes, signs, accounts</div>
          <div className="text-[11.5px] text-ink-3">{calls.length ? `${calls.length} call${calls.length > 1 ? "s" : ""} classified · ${usd(calls.reduce((a, c) => a + (c.cost ?? 0), 0))} charged to ` : "agent key "}
            <span className="font-mono">{key?.key_alias ?? "openshell-agent"}</span></div>
        </div>
        <div className="grid place-items-center text-ink-3"><ArrowRight className="size-5" /></div>
        <div className={clsx(card, "border-oracle/40 bg-oracle-soft/40")}>
          <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle"><Sparkles className="size-3.5" />OCI Generative AI</div>
          <div className="mt-1 flex flex-wrap gap-1">{models.length ? models.map((d) => <ModelChip key={d} deployment={d} lit />)
            : <span className="text-[11.5px] text-ink-3">{running ? "waiting for the route…" : "20 models, 5 vendors"}</span>}</div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 px-1">
        <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-[11.5px] font-semibold text-indigo">
          <ChevronDown className={clsx("size-3.5 transition", open && "rotate-180")} /> {open ? "Hide" : "Show"} what each one did
        </button>
        <button onClick={escape} disabled={probe === "running"} className="ml-auto rounded-lg border border-line px-2.5 py-1 text-[11.5px] font-semibold text-ink-2 hover:border-oracle/50">
          {probe === "running" ? "trying…" : "Try to escape the sandbox: call OCI or OpenAI directly"}
        </button>
      </div>
      {probe && probe !== "running" && (
        <div className="mt-1.5 flex flex-wrap gap-x-4 px-1 text-[11.5px]">
          {probe.tries.map((t) => <span key={t.target} className={t.result.startsWith("REFUSED") ? "text-oracle" : "text-ochre"}>✕ {t.target}: {t.result}</span>)}
        </div>
      )}
      {open && (
        <div className="mt-2 grid grid-cols-3 gap-3 border-t border-line/70 px-1 pt-2 text-[11.5px] leading-snug text-ink-2">
          <div>
            <div className="flex gap-1.5"><Lock className="mt-0.5 size-3 shrink-0 text-ink-3" /><span>No OCI credential and no model key. Its LiteLLM key is a placeholder; OpenShell swaps in the real one on the way to the gateway, and the policy allows one endpoint: <span className="font-mono">POST /v1/chat/completions</span>.</span></div>
            <div className="mt-1.5 rounded-lg bg-sand/60 p-1.5 font-mono text-[10.5px]">
              {net?.length ? net.slice(-4).map((n, i) => <div key={i} className={n.verdict === "DENIED" ? "text-oracle" : "text-moss"}>{n.verdict === "DENIED" ? "✕ DENIED " : "✓ ALLOWED"} {n.destination.replace("http://", "")}</div>)
                : <span className="text-ink-3">the sandbox's network decisions appear after a run</span>}
            </div>
          </div>
          <ol className="list-decimal space-y-0.5 pl-4">
            <li><b>Key check:</b> {key ? <><KeyRound className="mr-0.5 inline size-3" /><span className="font-mono">{key.key_alias}</span> may call {key.models?.length ?? "?"} model groups · {usd(key.spend)} of ${key.max_budget} · {key.rpm_limit} a minute</> : "which models, what budget, what rate"}</li>
            <li><b>Classify:</b> the complexity router calls our classifier (classifier_type: custom) on every call</li>
            <li><b>Route:</b> the route names a model group; LiteLLM picks its fastest healthy deployment, with fallbacks</li>
            <li><b>Sign:</b> {sb?.cluster === "oke" ? "as its OKE node (instance principal)" : "with the operator's OCI session, kept fresh in a Kubernetes Secret"}</li>
            <li><b>Account:</b> cost per call, spend per key, every decision in <span className="font-mono">x-litellm-*</span> headers</li>
          </ol>
          <div>{models.length ? `${models.length} model${models.length > 1 ? "s" : ""} answered this run, in us-chicago-1.` : "The models that answer appear here."} LiteLLM's OCI provider covers every vendor; Codex goes through OCI's Responses API.</div>
        </div>
      )}
    </section>
  );
}

export function Ask() {
  const [cfg, setCfg] = useState<AskConfig | null>(null);
  const [sb, setSb] = useState<Sandbox | null>(null);
  const [bar, setBar] = useState<number | null>(null);
  const [prompt, setPrompt] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("single");
  const fileInput = useRef<HTMLInputElement | null>(null);
  const attach = async (f?: File | null) => { if (f && f.type.startsWith("image/")) setImage(await toDataUrl(f)); };
  const [events, setEvents] = useState<Ev[]>([]);
  const [running, setRunning] = useState(false);
  const [details, setDetails] = useState(false);
  const [view, setView] = useState<"timeline" | "map">("timeline");
  const [probe, setProbe] = useState<null | "running" | { tries: { target: string; result: string }[] }>(null);
  const es = useRef<EventSource | null>(null);
  const [scenarios, setScenarios] = useState<UseCase[]>([]);
  const [picked, setPicked] = useState<UseCase | null>(null);

  useEffect(() => {
    getJSON<AskConfig>("/api/ask/config").then((c) => { setCfg(c); setBar(c.default_bar); setPrompt(c.examples[1] ?? ""); });
    getJSON<Sandbox>("/api/sandbox").then(setSb).catch(() => setSb(null));
    getJSON<UseCase[]>("/api/scenarios").then(setScenarios).catch(() => undefined);
  }, []);
  const groups = scenarios.reduce<Record<string, UseCase[]>>((g, x) => ((g[x.use_case] ??= []).push(x), g), {});
  const pick = async (x: UseCase) => {
    setPicked(x); setPrompt(x.prompt); setMode(x.mode ?? "single");
    if (x.image) { const b = await (await fetch("/api/sample-image")).blob(); setImage(await toDataUrl(new File([b], "invoice.png", { type: b.type }))); }
    else setImage(null);
  };
  const own = (text: string) => { setPicked(null); setPrompt(text); setImage(null); };

  const go = async () => {
    if ((!prompt.trim() && !image) || running) return;
    es.current?.close();
    setEvents([]); setRunning(true); setDetails(false);
    // A use case runs exactly as defined (its model group, tags, image); anything typed runs as typed.
    const body = picked && prompt === picked.prompt ? { scenario: picked.id, bar, runtime: "openshell", mode }
      : { prompt, bar, runtime: "openshell", image: image ?? undefined, mode };
    const { id } = await postJSON<{ id: string }>("/api/runs", body);
    const src = new EventSource(`/api/runs/${id}/stream`);
    es.current = src;
    src.onmessage = (m) => { const e = JSON.parse(m.data) as Ev; if (e.type) setEvents((v) => [...v, e]); };
    src.addEventListener("end", () => { src.close(); setRunning(false); getJSON<Sandbox>("/api/sandbox").then(setSb).catch(() => undefined); });
    src.onerror = () => { src.close(); setRunning(false); };
  };
  const escape = async () => { setProbe("running"); setProbe(await postJSON("/api/sandbox/probe", {})); };

  const failover = events.find((e) => e.type === "failover");
  const replay = events.find((e) => e.type === "replay");
  // After a failover or a replay, the screen shows the attempt that answered; the banner says what happened.
  const cut = events.reduce((at, e, i) => (e.type === "failover" || e.type === "replay" ? i : at), -1);
  const run = cut < 0 ? events : events.slice(cut + 1);
  const dropped = cut < 0 ? 0 : events.slice(0, cut).filter((e) => e.type === "llm").length;
  const calls = run.filter((e) => e.type === "llm");
  const first = calls[0];
  const decision = run.find((e) => e.type === "classify");
  const why = run.find((e) => e.type === "explain" && !e.error);
  const answer = run.find((e) => e.type === "answer");
  const error = events.find((e) => e.type === "error");
  const net = run.find((e) => e.type === "sandbox_net")?.events as { verdict: string; destination: string }[] | undefined;
  const key = (run.find((e) => e.type === "key") as Key | undefined) ?? sb?.key ?? undefined;
  const spend = calls.reduce((a, c) => a + (c.cost ?? 0), 0);
  const plan = run.find((e) => e.type === "plan")?.steps as { step: number }[] | undefined;
  const planned = !!plan || run.some((e) => e.type === "llm" && e.step === 0) || (running && mode === "plan");
  const ladder = (why?.checks as Check_[] | undefined)?.find((c) => c.check === "ladder");
  const point = cfg?.held_out_curve.reduce<CurvePoint | null>((b, p) => (b === null || Math.abs(p.bar - (bar ?? 0)) < Math.abs(b.bar - (bar ?? 0)) ? p : b), null);
  const sum = summary(run, planned);
  const sbErr = events.find((e) => e.type === "sandbox_error")?.message as string | undefined;
  const sandboxWhy = sbErr ? (/429|rate limit/i.test(sbErr) ? "LiteLLM rate-limited the agent's key" : sbErr.split(":")[0]) : "";
  const started = events.length > 0 || running;

  return (
    <div className="grid grid-cols-[272px_1fr] gap-5">
      {/* the use cases, in the order of the talk */}
      <aside className="scroll-thin sticky top-[76px] max-h-[calc(100vh-96px)] space-y-3 overflow-y-auto pr-1">
        <div>
          <div className="px-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle">Use cases</div>
          <div className="px-1 text-[11.5px] text-ink-3">Pick one, then Route it. Each shows one thing LiteLLM does.</div>
        </div>
        {Object.entries(groups).map(([uc, list]) => (
          <div key={uc}>
            <div className="px-1 pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-ink-3">{uc}</div>
            <div className="space-y-1">
              {list.map((x) => (
                <button key={x.id} onClick={() => pick(x)}
                  className={clsx("block w-full rounded-lg border px-2.5 py-1.5 text-left", picked?.id === x.id ? "border-oracle bg-oracle-soft/60" : "border-line bg-panel hover:border-oracle/50")}>
                  <span className="flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">{x.title}{x.mode === "plan" && <span className="rounded bg-indigo-soft px-1 text-[9.5px] font-semibold uppercase text-indigo">multi-step</span>}</span>
                  {x.shows && <span className="block text-[11px] leading-snug text-ink-3">{x.shows}</span>}
                </button>
              ))}
            </div>
          </div>
        ))}
        {cfg && (
          <div>
            <div className="px-1 pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-ink-3">Or type your own; for example</div>
            <div className="space-y-1">{cfg.examples.map((e) => (
              <button key={e} onClick={() => own(e)} className="block w-full truncate rounded-lg border border-dashed border-line px-2.5 py-1 text-left text-[11.5px] text-ink-2 hover:border-oracle/50">{e}</button>
            ))}</div>
          </div>
        )}
      </aside>

      <div className="min-w-0 space-y-4">
        {/* the request */}
        <section className="rounded-2xl border border-line bg-panel p-4" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); attach(e.dataTransfer.files?.[0]); }}>
          <div className="flex items-baseline gap-2">
            <span className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle">The request</span>
            <span className="text-[12px] text-ink-3">{picked ? `${picked.use_case} · ${picked.title}` : "your own"} · the agent sends it from the OpenShell sandbox; LiteLLM picks a model for every call</span>
          </div>
          <div className="mt-2 flex gap-3">
            <textarea value={prompt} onChange={(e) => { setPrompt(e.target.value); if (picked && e.target.value !== picked.prompt) setPicked(null); }} rows={3}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) go(); }}
              onPaste={(e) => { const f = [...e.clipboardData.files].find((x) => x.type.startsWith("image/")); if (f) { e.preventDefault(); attach(f); } }}
              placeholder="Type a request; paste, drop or attach an image for a multimodal one"
              className="w-full resize-y rounded-xl border border-line bg-paper px-4 py-3 text-[14px] leading-relaxed outline-none focus:border-oracle/60" />
            {image && (
              <div className="relative shrink-0">
                <img src={image} alt="attached" className="h-[92px] w-auto rounded-xl border border-line object-cover" />
                <button onClick={() => setImage(null)} className="absolute -right-2 -top-2 grid size-5 place-items-center rounded-full bg-ink text-paper" title="remove the image"><X className="size-3" /></button>
              </div>
            )}
          </div>
          <input ref={fileInput} type="file" accept="image/*" className="hidden" onChange={(e) => { attach(e.target.files?.[0]); e.target.value = ""; }} />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button onClick={go} disabled={running || (!prompt.trim() && !image)} className="flex items-center gap-2 rounded-xl bg-oracle px-5 py-2 text-[13.5px] font-semibold text-white disabled:bg-ink-3">
              {running ? <RotateCw className="size-4 animate-spin" /> : <CornerDownLeft className="size-4" />} Route it
            </button>
            <div className="flex rounded-xl bg-sand p-0.5" role="radiogroup" aria-label="agent mode">
              {([["single", "One pass", ListTree], ["plan", "Multi-step", Split]] as const).map(([m, label, Icon]) => (
                <button key={m} role="radio" aria-checked={mode === m} onClick={() => setMode(m)}
                  title={m === "single" ? "the agent answers the whole request in one loop" : "a planner splits the request into tasks; each task is routed on its own"}
                  className={clsx("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-semibold", mode === m ? "bg-panel text-ink shadow-sm" : "text-ink-3 hover:text-ink")}>
                  <Icon className="size-3.5" />{label}
                </button>
              ))}
            </div>
            <button onClick={() => fileInput.current?.click()} className="flex items-center gap-1.5 rounded-xl border border-line px-3 py-1.5 text-[12px] font-semibold text-ink-2 hover:border-oracle/50">
              <ImagePlus className="size-3.5" /> Image
            </button>
            <button onClick={async () => { const r = await fetch("/api/sample-image"); const b = await r.blob(); attach(new File([b], "invoice.png", { type: b.type })); setPicked(null); setPrompt("Read this invoice: what is the total due and when is it due?"); }}
              className="rounded-lg px-1 text-[11.5px] text-ink-3 underline decoration-dotted hover:text-ink">sample: an invoice photo</button>
            {cfg && bar !== null && (
              <div className="ml-auto flex items-center gap-2 text-[12px]" title={point ? `on ${cfg.held_out_prompts} unseen prompts at this bar: ${Math.round(point.quality * 100)}% good answers at ${usd(point.cost_per_request)} a request` : ""}>
                <span className="font-semibold">Quality bar</span>
                <input type="range" min={0.5} max={0.95} step={0.05} value={bar} onChange={(e) => setBar(Number(e.target.value))} className="w-[150px] accent-[#e5604d]" aria-label="quality bar" />
                <span className="w-9 font-mono font-semibold">{Math.round(bar * 100)}%</span>
                <span className="text-[11.5px] text-ink-3">{bar === cfg.default_bar ? "trained" : bar > cfg.default_bar ? "better, costlier" : "cheaper"}</span>
              </div>
            )}
          </div>
          <div className="mt-2 text-[11.5px] text-ink-3">
            {mode === "plan" ? "Multi-step: a planner splits the request into tasks, and each task reaches LiteLLM as its own request, so each can get a different model."
              : "One pass: the agent works the whole request in one loop; LiteLLM classifies every model call it makes."}
            {point && <> At a {Math.round((bar ?? 0) * 100)}% bar, on {cfg?.held_out_prompts} unseen prompts: <b className="text-ink-2">{Math.round(point.quality * 100)}%</b> good answers at {usd(point.cost_per_request)} a request.</>}
          </div>
        </section>

        <PathStrip sb={sb} net={net} vkey={key} events={run} running={running} probe={probe} escape={escape} />

        {replay && <div className="rounded-xl border-2 border-ochre/60 bg-ochre-soft px-4 py-2 text-[13px] font-semibold text-ochre">REPLAY · a recorded run of this request ({replay.recorded_at}). The live path did not answer: check the network or run scripts/preflight.sh.</div>}
        {failover && <div className="rounded-xl border border-ochre/40 bg-ochre-soft px-4 py-2 text-[12.5px] text-ochre">{failover.from} did not answer{sandboxWhy ? ` (${sandboxWhy})` : ""}; the run started again on {failover.to}{dropped ? `, and the ${dropped} call${dropped > 1 ? "s" : ""} before it are not shown` : ""}.</div>}
        {error && <div className="rounded-xl border border-oracle/40 bg-oracle-soft px-4 py-2 text-[12.5px] text-oracle">{error.message}</div>}

        {/* every call, with the decision LiteLLM made for it */}
        {started && (
          <Panel kicker={planned ? "What happened · multi-step" : "What happened"} title={sum.line || (planned ? "planning…" : "routing…")}
            right={
              <div className="flex rounded-lg bg-sand p-0.5">
                {([["timeline", "Every call", ListTree], ["map", "Route map", MapIcon]] as const).map(([v, label, Icon]) => (
                  <button key={v} onClick={() => setView(v)} className={clsx("flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] font-semibold", view === v ? "bg-panel text-ink shadow-sm" : "text-ink-3")}>
                    <Icon className="size-3.5" />{label}
                  </button>
                ))}
              </div>
            }>
            {sum.hint && <div className={clsx("mb-3 rounded-lg px-3 py-2 text-[12px]", planned ? "bg-indigo-soft/60 text-indigo" : "bg-sand text-ink-2")}>{sum.hint}</div>}
            {view === "timeline"
              ? <Timeline events={run} running={running} planned={planned} />
              : <RouteMap router={picked?.model ?? "oci-auto-trained"} classifying={running && !answer}
                  calls={calls.map((c) => ({ ...c, route: c.route ?? Object.entries(ROUTE_STYLE).find(([, v]) => v.group === c.group)?.[0] })) as Extract<RunEvent, { type: "llm" }>[]} />}
          </Panel>
        )}

        {(answer || why) && (
          <div className="grid grid-cols-[1.25fr_1fr] gap-4">
            <Panel kicker="The answer" title={!first ? "" : plan ? `${plan.length} tasks, put together from ${new Set(calls.map((c) => c.deployment)).size} models` : `from ${new Set(calls.map((c) => c.deployment)).size > 1 ? `${new Set(calls.map((c) => c.deployment)).size} models` : (calls[calls.length - 1]?.deployment ?? "").replace(/^oci(-responses)?\//, "")}`}
              right={answer && <span className="font-mono text-[11.5px] text-ink-3">{answer.seconds}s · {usd(spend)}</span>}>
              <div className="scroll-thin max-h-[520px] overflow-y-auto"><Answer text={answer?.text} /></div>
            </Panel>
            <Panel kicker={planned ? "Why the first call got its route (the planner)" : "Why the first call got its route"} title={decision ? <span className="flex items-center gap-2"><RouteChip route={decision.route} size="lg" /> decided inside LiteLLM</span> : ""}>
              {why && <p className="text-[14px] leading-relaxed text-ink">{why.summary}</p>}
              {ladder?.steps && <div className="mt-3"><Ladder steps={ladder.steps} bar={ladder.bar ?? 0.7} /></div>}
              <div className="mt-2 text-[11.5px] text-ink-3">Every other call's decision is in "What happened": click a call to see its ladder.</div>
              <button onClick={() => setDetails(!details)} className="mt-3 flex items-center gap-1 text-[12px] font-semibold text-indigo">
                <ChevronDown className={clsx("size-4 transition", details && "rotate-180")} /> {details ? "Hide" : "Show"} the details: every check and the closest training requests
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
                </div>
              )}
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}
