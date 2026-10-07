import clsx from "clsx";
import { ArrowRight, Check, ChevronDown, RotateCw, Wrench } from "lucide-react";
import { useState } from "react";
import { usd } from "../api";
import { ModelChip, RouteChip } from "./bits";

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

/** Every model call of the run, in order, with the decision LiteLLM made for it. Multi-step runs are grouped by task. */
export function Timeline({ events, running, planned }: { events: Ev[]; running: boolean; planned: boolean }) {
  const [open, setOpen] = useState<number | null>(null);
  const plan = events.find((e) => e.type === "plan")?.steps as { step: number; title: string; instruction: string; image?: boolean }[] | undefined;
  const groups: Group[] = planned
    ? [{ key: 0, title: "Plan the work", instruction: "A planner call splits the request into tasks." }, ...(plan ?? []).map((s) => ({ key: s.step, title: s.title, instruction: s.instruction, image: s.image }))]
    : [{ key: "all", title: "The agent", instruction: "One pass: the agent calls the model, runs the tools it asks for, and calls the model again until it can answer." }];
  const decisions = new Map<number, Ev>(events.filter((e) => e.type === "classify").map((e) => [e.call, e]));
  const inGroup = (g: Group) => (e: Ev) => g.key === "all" || e.step === g.key;
  const answered = !!events.find((e) => e.type === "answer");

  return (
    <ol data-testid="timeline" className="space-y-3">
      {groups.map((g, gi) => {
        const items = events.filter((e) => (e.type === "llm" || e.type === "tool") && inGroup(g)(e));
        const calls = items.filter((e) => e.type === "llm");
        const done = g.key === "all" ? answered : g.key === 0 ? !!plan : events.some((e) => e.type === "step_done" && e.step === g.key);
        const started = calls.length > 0 || events.some((e) => e.type === "step" && e.step === g.key);
        const active = running && !done && (started || (g.key === "all" || g.key === 0));
        return (
          <li key={String(g.key)} className={clsx("rounded-xl border", active ? "border-indigo/50 bg-indigo/[0.04]" : "border-line bg-paper")}>
            <div className="flex items-start gap-3 px-3.5 py-2.5">
              <span className={clsx("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold",
                done ? "bg-moss text-white" : active ? "bg-indigo text-white" : "bg-sand text-ink-3")}>
                {done ? <Check className="size-3.5" /> : active ? <RotateCw className="size-3 animate-spin" /> : planned ? gi : 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-[13.5px] font-semibold text-ink">{planned && gi > 0 ? `Task ${gi}: ` : ""}{g.title}</span>
                  {g.image && <span className="rounded bg-ochre-soft px-1.5 text-[10px] font-semibold uppercase text-ochre">carries the image</span>}
                  {calls.length > 0 && <span className="font-mono text-[11px] text-ink-3">{calls.length} call{calls.length > 1 ? "s" : ""} · {usd(calls.reduce((a, c) => a + (c.cost ?? 0), 0))}</span>}
                </div>
                {g.instruction && <div className="text-[11.5px] leading-snug text-ink-3">{g.instruction}</div>}
              </div>
            </div>
            {items.length > 0 && (
              <ul className="space-y-1 border-t border-line/70 px-3.5 py-2">
                {items.map((e, i) => {
                  if (e.type === "tool") return (
                    <li key={i} className="flex items-center gap-1.5 pl-9 font-mono text-[11px] text-ink-3"><Wrench className="size-3" /> tool {e.name} {String(e.input).slice(0, 90)}</li>
                  );
                  const d = decisions.get(e.call);
                  const lad = ladderOf(d);
                  const isOpen = open === e.call;
                  return (
                    <li key={i}>
                      <button onClick={() => setOpen(isOpen ? null : e.call)} className="flex w-full flex-wrap items-center gap-2 rounded-lg px-1 py-1 text-left text-[12px] hover:bg-sand/60">
                        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-ink text-[10.5px] font-semibold text-white">{e.call}</span>
                        <span className="text-[10.5px] font-semibold uppercase tracking-wide text-indigo">LiteLLM classified</span>
                        {e.route ? <RouteChip route={e.route} /> : <span className="font-mono">{e.group}</span>}
                        <span className="max-w-[360px] truncate text-[11.5px] text-ink-2">{d ? reason(d) : e.group && e.group !== "oci-auto-trained" ? `asked for ${e.group} directly` : ""}</span>
                        <ArrowRight className="size-3 text-ink-3" />
                        <ModelChip deployment={e.deployment} />
                        {e.fallbacks > 0 && <span className="rounded bg-ochre-soft px-1.5 font-mono text-[10.5px] text-ochre">fallback ×{e.fallbacks}</span>}
                        {e.tool_calls?.length > 0 && <span className="text-[11px] text-ink-3">asks for {e.tool_calls.join(", ")}</span>}
                        <span className="ml-auto font-mono text-[11px] text-ink-3">{e.seconds}s · {usd(e.cost)}</span>
                        {lad && <ChevronDown className={clsx("size-3.5 text-ink-3 transition", isOpen && "rotate-180")} />}
                      </button>
                      {isOpen && lad && (
                        <div className="mb-2 ml-9 mt-1 rounded-lg border border-line bg-panel p-3">
                          <div className="mb-2 text-[11.5px] text-ink-2">Call {e.call}: each route's chance of a good answer, cheapest first, against the {Math.round(lad.bar * 100)}% bar. LiteLLM read this call's user turn{planned ? ": this task's instruction" : ""}.</div>
                          <Ladder steps={lad.steps} bar={lad.bar} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
            {!items.length && active && <div className="border-t border-line/70 px-3.5 py-2 pl-[50px] text-[11.5px] text-ink-3">LiteLLM is classifying…</div>}
          </li>
        );
      })}
    </ol>
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
