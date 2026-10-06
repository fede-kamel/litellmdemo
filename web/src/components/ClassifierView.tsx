import { Brain, CheckCircle2, FlaskConical, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { getJSON, usd } from "../api";
import { Bars, Panel, RouteChip } from "./bits";

type Point = { quality: number; cost_per_request: number };
type Ladder = { bar: number; train_prompts: number; held_out_prompts: number; held_out: Record<string, Point>;
  held_out_curve: ({ bar: number } & Point)[]; held_out_mix: Record<string, number> };
type Info = {
  trained: boolean;
  meta: null | { examples: number; encoder: string; held_out_recall: Record<string, number>; ladder?: Ladder };
  labels?: { outcome_prompts: number; runs: number; unanimous: number; with_reasoning: number; families: number };
  data?: { prompts: number; by_route: Record<string, number>; examples: { prompt: string; route: string; family: string }[] };
};

const STEPS = [
  { icon: FlaskConical, title: "Generate", body: "The judge model writes 463 prompts across 18 task families, trivial to expert (general tasks plus support, billing, IT ops, finance and people ops), and code and seven languages." },
  { icon: Scale, title: "Label by outcome", body: "Every route answers every prompt; the judge grades each answer on correctness, completeness and instruction-following (1–5). Pass: at least 4 on all three. Three runs per route give a pass rate, not a guess." },
  { icon: Brain, title: "Train the ladder", body: "For each route, predict the chance its answer passes: a logistic model on the request's embedding and difficulty signals, averaged with the pass rates of the most similar labelled requests." },
  { icon: CheckCircle2, title: "Route in LiteLLM", body: "classifier_type: custom. Rules first (image, length, language), then code, then the cheapest route that clears the quality bar. Each request may set its own bar." },
];

const LABEL: Record<string, string> = {
  ladder: "the ladder (our router)", "always SIMPLE": "always the fast models", "always MEDIUM": "always the balanced models",
  "always COMPLEX": "always the strong models", "always REASONING": "always the reasoning models", oracle: "perfect routing (oracle)",
};

export function ClassifierView() {
  const [info, setInfo] = useState<Info | null>(null);
  useEffect(() => { getJSON<Info>("/api/classifier").then(setInfo); }, []);
  const L = info?.meta?.ladder;
  const order = ["ladder", "always SIMPLE", "always MEDIUM", "always COMPLEX", "always REASONING", "oracle"];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {STEPS.map((s, i) => (
          <div key={s.title} className="rounded-2xl border border-line bg-panel p-4">
            <div className="flex items-center gap-2"><span className="grid size-6 place-items-center rounded-full bg-oracle text-[11px] font-semibold text-white">{i + 1}</span><s.icon className="size-4 text-oracle" /><span className="text-[13.5px] font-semibold">{s.title}</span></div>
            <p className="mt-2 text-[12px] leading-snug text-ink-2">{s.body}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[1.35fr_1fr] gap-4">
        <Panel kicker="Does it pay?" title={L ? `Quality and cost on ${L.held_out_prompts} unseen prompts` : "not trained yet"}>
          {L && (
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-3">
                <th className="py-1.5">Policy</th><th>Answers good enough</th><th>Cost per request</th></tr></thead>
              <tbody>{order.filter((k) => L.held_out[k]).map((k) => (
                <tr key={k} className={k === "ladder" ? "bg-oracle-soft/40 font-semibold" : "border-b border-line/60"}>
                  <td className="py-1.5">{LABEL[k]}{k === "ladder" && <span className="ml-1 font-normal text-ink-3">· bar {Math.round(L.bar * 100)}%</span>}</td>
                  <td>{Math.round(L.held_out[k].quality * 100)}%</td><td className="font-mono">{usd(L.held_out[k].cost_per_request)}</td></tr>
              ))}</tbody>
            </table>
          )}
          {L && <p className="mt-3 text-[11.5px] leading-snug text-ink-3">The bar was chosen inside the training split ({L.train_prompts} prompts, 5-fold cross-validation): the cheapest bar at least as good as always using the reasoning models. These {L.held_out_prompts} prompts were never seen in training or in choosing it.</p>}
        </Panel>
        <Panel kicker="The dial" title="Every quality bar, on the same unseen prompts">
          {L && (
            <table className="w-full font-mono text-[12px]">
              <thead><tr className="border-b border-line text-left text-[10.5px] uppercase tracking-wide text-ink-3"><th className="py-1">bar</th><th>good answers</th><th>per request</th></tr></thead>
              <tbody>{L.held_out_curve.map((c) => (
                <tr key={c.bar} className={c.bar === L.bar ? "bg-oracle-soft/40 font-semibold" : "border-b border-line/50"}>
                  <td className="py-1">{Math.round(c.bar * 100)}%{c.bar === L.bar ? " · trained" : ""}</td><td>{Math.round(c.quality * 100)}%</td><td>{usd(c.cost_per_request)}</td></tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Panel kicker="Training data" title={info?.data ? `${info.data.prompts} labelled prompts` : "not labelled yet"}>
          {info?.data && <Bars values={info.data.by_route} />}
          <div className="mt-3 space-y-1.5">
            {info?.data?.examples.slice(0, 5).map((e) => (
              <div key={e.prompt} className="flex items-start gap-2 text-[11.5px]"><RouteChip route={e.route} /><span className="line-clamp-1 text-ink-2">{e.prompt}</span></div>
            ))}
          </div>
        </Panel>
        <Panel kicker="Why not one label?" title={info?.labels ? `${Math.round((info.labels.unanimous / info.labels.outcome_prompts) * 100)}% of prompts get the same label every time` : "—"}>
          {info?.labels && <p className="text-[12.5px] leading-relaxed text-ink-2">
            Labelled three times, only {info.labels.unanimous} of {info.labels.outcome_prompts} prompts got the same cheapest passing route in every run: whether the fast model passes is often a coin flip. So the router does not guess one label; it predicts each route's chance of a good answer and takes the cheapest one likely enough.
          </p>}
        </Panel>
        <Panel kicker="Code check" title="Programming requests go to the code models">
          {info?.meta && <Bars values={{ CODE: info.meta.held_out_recall.CODE ?? 0 }} max={1} />}
          <p className="mt-2 text-[11.5px] text-ink-3">recall on held-out code prompts · encoder <span className="font-mono">{info?.meta?.encoder.split("/").pop()}</span>, run locally</p>
        </Panel>
      </div>
    </div>
  );
}
