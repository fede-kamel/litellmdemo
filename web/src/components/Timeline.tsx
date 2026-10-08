import clsx from "clsx";
import { ArrowRight, Check, ChevronDown, RotateCw, Wrench } from "lucide-react";
import { useState, type ReactNode } from "react";
import { usd } from "../api";
import { Answer, ModelChip, RouteChip } from "./bits";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Ev = Record<string, any> & { type: string };
export type Step = { route: string; pass: number; cost?: number; clears: boolean; chosen: boolean };

export const NAMES: Record<string, string> = { SIMPLE: "fast", MEDIUM: "balanced", COMPLEX: "strong", REASONING: "reasoning" };

/** Each route, cheapest first: its chance of a good answer, against the bar. */
export function Ladder({ steps, bar }: { steps: Step[]; bar: number }) {
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

/** The ladder of one call, rebuilt from the decision LiteLLM returned with it. */
export function ladderOf(d?: Ev): { steps: Step[]; bar: number } | null {
  if (!d || d.criterion !== "ladder") return null;
  const bar = d.details?.bar ?? 0.75;
  const order: string[] = d.details?.order ?? Object.keys(NAMES);
  const p: Record<string, number> = d.probabilities ?? {};
  return { bar, steps: order.filter((r) => r in p).map((r) => ({ route: r, pass: p[r], clears: p[r] >= bar, chosen: r === d.route })) };
}

/** One line on why a call got its route. */
export function reason(d?: Ev): string {
  if (!d) return "";
  if (d.criterion === "ladder") {
    const p = Math.round((d.probabilities?.[d.route] ?? 0) * 100), bar = Math.round((d.details?.bar ?? 0) * 100);
    return p >= bar ? `${p}% ≥ ${bar}% bar · cheapest that clears it` : `${p}%: none clears ${bar}% · the most likely`;
  }
  if (String(d.criterion).startsWith("rule: image")) return "the request carries an image";
  if (String(d.criterion).startsWith("rule: length")) return "too long for the other routes";
  if (String(d.criterion).startsWith("rule: language")) return `written in another language (${String(d.criterion).match(/\((\w+)\)/)?.[1] ?? "?"})`;
  if (String(d.criterion).startsWith("model: code")) return `a programming request (code check ${Math.round((d.probabilities?.CODE ?? 0) * 100)}%)`;
  return String(d.criterion ?? "");
}

type Group = { key: number | "all"; title: string; instruction?: string; image?: boolean };
type Entry = { kind: "call"; e: Ev } | { kind: "tool"; e: Ev; result?: string };

const CRITERION: Record<string, string> = { ladder: "the quality ladder", fallback: "the fallback tier" };
const criterionOf = (d?: Ev) => !d ? "" : CRITERION[d.criterion] ?? String(d.criterion).replace(/^rule: /, "the ").replace(/^model: code$/, "the code check").replace(/ \(\w+\)$/, " rule");
const n = (x?: number) => (x ?? 0).toLocaleString("en-US");

/** The calls and tools of one task, in order; each tool result joins the tool that produced it. */
function entries(items: Ev[]): Entry[] {
  const out: Entry[] = [];
  for (const e of items) {
    if (e.type === "llm") out.push({ kind: "call", e });
    else if (e.type === "tool") out.push({ kind: "tool", e });
    else if (e.type === "tool_result") {
      const t = [...out].reverse().find((x): x is Extract<Entry, { kind: "tool" }> => x.kind === "tool" && x.result === undefined);
      if (t) t.result = String(e.output ?? "");
    }
  }
  return out;
}

/** A tool's arguments as the agent sent them: pretty JSON when they parse, as written otherwise. */
function args(input: unknown): string {
  const raw = String(input ?? "");
  try { return JSON.stringify(JSON.parse(raw.replace(/'/g, '"')), null, 1).replace(/\n\s*/g, " "); } catch { return raw; }
}

function Node({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <li className="relative">
      <span className={clsx("absolute -left-[27px] top-3 size-2.5 rounded-full ring-4 ring-panel", tone)} />
      {children}
    </li>
  );
}

function Legend() {
  const item = (tone: string, title: string, text: string) => (
    <div className="flex items-start gap-2"><span className={clsx("mt-1 size-2.5 shrink-0 rounded-full", tone)} />
      <span><b className="text-ink">{title}</b> <span className="text-ink-3">{text}</span></span></div>
  );
  return (
    <div className="mb-3 grid grid-cols-3 gap-3 rounded-xl border border-line bg-deep/60 px-4 py-2.5 text-[11.5px] leading-snug">
      {item("bg-indigo", "LiteLLM", "reads each model call, decides its route and picks the model. Click a call for its ladder.")}
      {item("bg-oracle", "The model", "answers, or asks the agent to run a tool. Reasoning models think first; OCI reports how long, not what.")}
      {item("bg-moss", "A tool", "the agent runs it and hands the result back to the model, in a new call that LiteLLM classifies again.")}
    </div>
  );
}

function Call({ e, d, open, toggle, planned, planSteps, isResult }: { e: Ev; d?: Ev; open: boolean; toggle: () => void; planned: boolean; planSteps?: { title: string }[]; isResult?: boolean }) {
  const lad = ladderOf(d);
  const [full, setFull] = useState(false);
  const text = String(e.text ?? "").trim();
  const asked: string[] = e.tool_calls ?? [];
  const isPlanner = planned && e.step === 0;
  return (
    <Node tone="bg-indigo">
      <div className={clsx("rounded-xl border bg-sand/40", open ? "border-indigo/50" : "border-line")}>
        <button onClick={toggle} className="flex w-full flex-wrap items-center gap-2 px-3 pt-2.5 text-left text-[12px]">
          <span className="grid size-6 shrink-0 place-items-center rounded-full bg-indigo text-[10.5px] font-semibold text-paper">{e.call}</span>
          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-indigo">LiteLLM classified</span>
          {e.route ? <RouteChip route={e.route} /> : <span className="font-mono text-ink-2">{e.group}</span>}
          <span className="max-w-[380px] truncate text-[11.5px] text-ink-2">{d ? reason(d) : e.group && e.group !== "oci-auto-trained" ? `asked for ${e.group} directly` : ""}</span>
          <ArrowRight className="size-3 text-ink-3" />
          <ModelChip deployment={e.deployment} />
          {e.fallbacks > 0 && <span className="rounded bg-ochre-soft px-1.5 font-mono text-[10.5px] text-ochre" title="the route's deployment failed; LiteLLM answered from its fallback group">fallback ×{e.fallbacks}{e.group && e.group !== "oci-auto-trained" ? ` → ${e.group}` : ""}</span>}
          <span className="ml-auto font-mono text-[11px] text-ink-3">{e.seconds}s · {usd(e.cost)}</span>
          {lad && <ChevronDown className={clsx("size-3.5 text-ink-3 transition", open && "rotate-180")} />}
        </button>
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 px-3 pb-2 pl-[44px] pt-1 font-mono text-[10.5px] text-ink-3">
          {d && <span>decided by {criterionOf(d)}{d.milliseconds != null ? ` in ${Math.round(d.milliseconds)} ms` : ""}</span>}
          <span>{n(e.tokens?.in)} tokens in → {n(e.tokens?.out)} out</span>
          {e.tokens?.reasoning > 0 && <span className="text-oracle">thought for {n(e.tokens.reasoning)} reasoning tokens (OCI keeps the text)</span>}
          {e.retries > 0 && <span className="text-ochre">retried ×{e.retries}</span>}
        </div>
        {open && lad && (
          <div className="mx-3 mb-2 ml-[44px] rounded-lg border border-line bg-deep/70 p-3">
            <div className="mb-2 text-[11.5px] text-ink-2">Call {e.call}: each route's chance of a good answer, cheapest first, against the {Math.round(lad.bar * 100)}% bar. The cheapest route that clears the bar wins. LiteLLM read this call's user turn{planned ? ": this task's instruction" : ""}.</div>
            <Ladder steps={lad.steps} bar={lad.bar} />
          </div>
        )}
        <div className="border-t border-line/70 px-3 py-2 pl-[44px] text-[12px]">
          {isPlanner && planSteps?.length ? (
            <div><span className="font-semibold text-oracle">The planner split the request into {planSteps.length} tasks:</span>
              <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-ink-2">{planSteps.map((s, i) => <li key={i}>{s.title}</li>)}</ol></div>
          ) : asked.length ? (
            <div className="flex flex-wrap items-center gap-1.5"><span className="font-semibold text-oracle">The model asked the agent to run</span>
              {asked.map((t, i) => <span key={i} className="rounded bg-moss-soft px-1.5 font-mono text-[11px] text-moss">{t}</span>)}
              {text && <span className="w-full text-[11.5px] text-ink-3">and said: {text.slice(0, 200)}</span>}</div>
          ) : text ? (
            <div><span className="font-semibold text-oracle">The model answered</span>{isResult && <span className="ml-2 rounded bg-moss-soft px-1.5 text-[10px] font-semibold uppercase tracking-wide text-moss">the task's result · passed to the next tasks</span>}
              <div className={clsx("relative mt-1 overflow-hidden", !full && "max-h-[84px]")}><Answer text={text} />
                {!full && text.length > 280 && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-panel to-transparent" />}</div>
              {text.length > 280 && <span role="button" onClick={() => setFull(!full)} className="mt-1 inline-block cursor-pointer text-[11px] font-semibold text-indigo">{full ? "show less" : "show all of it"}</span>}</div>
          ) : <span className="text-ink-3">The model returned no text.</span>}
        </div>
      </div>
    </Node>
  );
}

function Tool({ e, result, running }: { e: Ev; result?: string; running: boolean }) {
  return (
    <Node tone="bg-moss">
      <div className="rounded-xl border border-moss/25 bg-moss-soft/30 px-3 py-2 text-[12px]">
        <div className="flex items-center gap-2"><Wrench className="size-3.5 text-moss" />
          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-moss">The agent ran a tool</span>
          <span className="font-mono font-semibold text-ink">{e.name}</span></div>
        <div className="mt-1.5 grid grid-cols-[64px_1fr] gap-x-2 gap-y-1 font-mono text-[11px]">
          <span className="text-ink-3">with</span><code className="whitespace-pre-wrap break-words text-ink-2">{args(e.input)}</code>
          <span className="text-ink-3">returned</span>
          {result !== undefined
            ? <code className="scroll-thin max-h-[120px] overflow-y-auto whitespace-pre-wrap break-words rounded-md bg-deep/70 px-2 py-1 text-moss">{result || "(nothing)"}</code>
            : <span className="text-ink-3">{running ? "running…" : "no result recorded"}</span>}
        </div>
      </div>
    </Node>
  );
}

function Result({ text }: { text: string }) {
  const [full, setFull] = useState(false);
  return (
    <div className="border-t border-line/70 px-4 py-2.5">
      <div className="text-[10.5px] font-semibold uppercase tracking-wide text-moss">Task result · passed to the next tasks</div>
      <div className={clsx("relative mt-1 overflow-hidden", !full && "max-h-[96px]")}><Answer text={text} />
        {!full && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-panel to-transparent" />}</div>
      <span role="button" onClick={() => setFull(!full)} className="mt-1 inline-block cursor-pointer text-[11px] font-semibold text-indigo">{full ? "show less" : "show the whole result"}</span>
    </div>
  );
}

/** What the agent is doing now, in one line, while its task runs. */
function now(list: Entry[]): string {
  const last = list[list.length - 1];
  if (!last) return "LiteLLM is classifying the first call…";
  if (last.kind === "tool") return last.result === undefined ? `the agent is running ${last.e.name}…` : "the model reads the tool's result; LiteLLM classifies the next call…";
  return last.e.tool_calls?.length ? "the agent is running the tool…" : "finishing the task…";
}

/** Every step of the run, in order: what the agent was told, each model call with the decision LiteLLM made for it,
 *  each tool with its arguments and result, and each task's result. Multi-step runs are grouped by task. */
export function Timeline({ events, running, planned }: { events: Ev[]; running: boolean; planned: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const plan = events.find((e) => e.type === "plan")?.steps as { step: number; title: string; instruction: string; image?: boolean }[] | undefined;
  const groups: Group[] = planned
    ? [{ key: 0, title: "Plan the work", instruction: "A planner call reads the whole request and splits it into tasks. LiteLLM routes the planner like any other call." },
       ...(plan ?? []).map((s) => ({ key: s.step, title: s.title, instruction: s.instruction, image: s.image }))]
    : [{ key: "all", title: "The agent", instruction: "One pass: the agent calls the model, runs the tools it asks for, and calls the model again until it can answer. Every call carries the same request." }];
  const decisions = new Map<number, Ev>(events.filter((e) => e.type === "classify").map((e) => [e.call, e]));
  const inGroup = (g: Group) => (e: Ev) => g.key === "all" || e.step === g.key;
  const answered = !!events.find((e) => e.type === "answer");

  return (
    <div>
      <Legend />
      <ol data-testid="timeline" className="space-y-3">
        {groups.map((g, gi) => {
          const items = events.filter((e) => ["llm", "tool", "tool_result"].includes(e.type) && inGroup(g)(e));
          const list = entries(items);
          const calls = items.filter((e) => e.type === "llm");
          const doneEv = typeof g.key === "number" && g.key > 0 ? events.find((e) => e.type === "step_done" && e.step === g.key) : undefined;
          const done = g.key === "all" ? answered : g.key === 0 ? !!plan : !!doneEv;
          const started = calls.length > 0 || events.some((e) => e.type === "step" && e.step === g.key);
          const active = running && !done && (started || (g.key === "all" || g.key === 0));
          const routes = [...new Set(calls.map((c) => c.route ?? c.group).filter(Boolean))] as string[];
          const tokens = calls.reduce((a, c) => a + (c.tokens?.in ?? 0) + (c.tokens?.out ?? 0), 0);
          // the task's result is usually its last call's answer: mark that call, rather than repeat the text below it
          const lastCall = calls[calls.length - 1];
          const resultInCall = !!doneEv && String(lastCall?.text ?? "").trim() === String(doneEv.text ?? "").trim();
          return (
            <li key={String(g.key)} className={clsx("overflow-hidden rounded-2xl border", active ? "border-indigo/60 shadow-[0_0_0_1px_rgb(143_140_240/0.25)]" : "border-line", "bg-panel")}>
              <div className="flex items-start gap-3 px-4 py-3">
                <span className={clsx("mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-[11.5px] font-semibold",
                  done ? "bg-moss text-paper" : active ? "bg-indigo text-paper" : "bg-sand text-ink-3")}>
                  {done ? <Check className="size-4" /> : active ? <RotateCw className="size-3.5 animate-spin" /> : planned ? gi : 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-[14px] font-semibold text-ink">{planned && gi > 0 ? `Task ${gi}: ` : ""}{g.title}</span>
                    {g.image && <span className="rounded bg-ochre-soft px-1.5 text-[10px] font-semibold uppercase text-ochre">carries the image</span>}
                    {routes.map((r) => <RouteChip key={r} route={r} />)}
                    {calls.length > 0 && <span className="ml-auto font-mono text-[11px] text-ink-3">{calls.length} call{calls.length > 1 ? "s" : ""} · {n(tokens)} tokens · {calls.reduce((a, c) => a + (c.seconds ?? 0), 0).toFixed(1)}s · {usd(calls.reduce((a, c) => a + (c.cost ?? 0), 0))}</span>}
                  </div>
                  {g.instruction && (
                    <div className="mt-1.5 rounded-lg border-l-2 border-oracle/60 bg-deep/50 px-3 py-1.5 text-[12px] leading-snug text-ink-2">
                      <span className="mr-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-3">{planned && gi > 0 ? "the agent was told" : "how it works"}</span>{g.instruction}
                    </div>
                  )}
                </div>
              </div>
              {(list.length > 0 || active) && (
                <ol className="relative mb-3 ml-[29px] mr-4 space-y-2.5 border-l border-line pl-6">
                  {list.map((x, i) => x.kind === "call"
                    ? <Call key={i} e={x.e} d={decisions.get(x.e.call)} open={open === x.e.call} toggle={() => setOpen(open === x.e.call ? null : x.e.call)} planned={planned} planSteps={plan} isResult={resultInCall && x.e === lastCall} />
                    : <Tool key={i} e={x.e} result={x.result} running={running} />)}
                  {active && <Node tone="bg-indigo live-dot"><div className="py-1.5 text-[12px] text-ink-3">{now(list)}</div></Node>}
                </ol>
              )}
              {doneEv?.text && !resultInCall && <Result text={String(doneEv.text)} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** How many calls, how many distinct decisions: the point of the run in one line. */
export function summary(events: Ev[], planned: boolean): { line: string; hint?: string } {
  const calls = events.filter((e) => e.type === "llm");
  if (!calls.length) return { line: "" };
  const routes = new Set(calls.map((c) => c.route ?? c.group));
  const models = new Set(calls.map((c) => c.deployment));
  const line = `${calls.length} model call${calls.length > 1 ? "s" : ""}, each classified by LiteLLM · ${routes.size} route${routes.size > 1 ? "s" : ""} · ${models.size} model${models.size > 1 ? "s" : ""} · ${usd(calls.reduce((a, c) => a + (c.cost ?? 0), 0))}`;
  const hint = !planned && calls.length > 1 && routes.size === 1
    ? "One pass: every call carries the same request, so LiteLLM gives every call the same route. Switch to Multi-step to split the job into tasks and route each one on its own."
    : planned ? "Multi-step: each task reaches LiteLLM as its own request, so each task is classified on its own words." : undefined;
  return { line, hint };
}
