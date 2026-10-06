import { Brain, CheckCircle2, Database, FlaskConical, Scale } from "lucide-react";
import { useEffect, useState } from "react";
import { getJSON, usd } from "../api";
import { Bars, Panel, RouteChip } from "./bits";

type Policy = { policy: string; quality: number; cost_usd: number; classifier_cost_usd: number; route_match: number; task_type_accuracy: number | null };
type Info = {
  trained: boolean;
  meta: null | { examples: number; train: number; held_out: number; held_out_accuracy: number; cv_balanced_accuracy: number;
    held_out_recall: Record<string, number>; confusion_matrix: { labels: string[]; rows_true_cols_predicted: number[][] };
    encoder: string; C: number; train_seconds: number; trained_at: string };
  eval: null | { held_out_difficulty: number; held_out_task_type: number; policies: Policy[] };
  data?: { prompts: number; by_route: Record<string, number>; examples: { prompt: string; route: string; family: string }[] };
};

const STEPS = [
  { icon: FlaskConical, title: "Generate", body: "The judge model writes 312 prompts: 13 task families from trivial to expert, code tasks, and requests in 7 languages." },
  { icon: Scale, title: "Label by outcome", body: "SIMPLE, MEDIUM and COMPLEX each answer; the judge grades correctness, completeness and instruction-following (1–5). Label: the cheapest route scoring ≥4 on all three." },
  { icon: Brain, title: "Mini-train", body: "A multilingual MiniLM encoder (local) and a logistic-regression head, regularisation chosen by 5-fold cross-validation. Seconds on a laptop CPU." },
  { icon: CheckCircle2, title: "Plug into LiteLLM", body: "classifier_type: custom: the gateway calls our classify() per request. Rules first (image → VISION, very long → LONG_CONTEXT), then the model." },
];

export function ClassifierView() {
  const [info, setInfo] = useState<Info | null>(null);
  useEffect(() => { getJSON<Info>("/api/classifier").then(setInfo); }, []);
  const m = info?.meta;
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
      <div className="grid grid-cols-3 gap-4">
        <Panel kicker="Training data" title={info?.data ? `${info.data.prompts} labelled prompts` : "not labelled yet"}>
          {info?.data && <Bars values={info.data.by_route} />}
          <div className="mt-3 space-y-1.5">
            {info?.data?.examples.slice(0, 6).map((e) => (
              <div key={e.prompt} className="flex items-start gap-2 text-[11.5px]"><RouteChip route={e.route} /><span className="line-clamp-1 text-ink-2">{e.prompt}</span></div>
            ))}
          </div>
        </Panel>
        <Panel kicker="Held-out accuracy" title={m ? `${Math.round(m.held_out_accuracy * 100)}% on ${m.held_out} unseen prompts` : "not trained yet"}>
          {m && <>
            <Bars values={m.held_out_recall} max={1} />
            <div className="mt-3 text-[11px] text-ink-3">recall per route · cross-validated balanced accuracy {Math.round(m.cv_balanced_accuracy * 100)}% · trained in {m.train_seconds}s · <span className="font-mono">{m.encoder.split("/").pop()}</span></div>
          </>}
        </Panel>
        <Panel kicker="Confusion matrix" title="rows: the right route · columns: predicted">
          {m && (
            <table className="w-full text-center font-mono text-[10.5px]">
              <thead><tr><th />{m.confusion_matrix.labels.map((l) => <th key={l} className="px-0.5 font-medium text-ink-3">{l.slice(0, 4)}</th>)}</tr></thead>
              <tbody>{m.confusion_matrix.rows_true_cols_predicted.map((row, i) => (
                <tr key={i}><td className="pr-1 text-left text-ink-3">{m.confusion_matrix.labels[i].slice(0, 6)}</td>
                  {row.map((v, j) => <td key={j} className={i === j ? "bg-moss-soft font-semibold text-moss" : v ? "bg-oracle-soft text-oracle" : "text-ink-3/40"}>{v}</td>)}</tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
      </div>
      <Panel kicker="Does it pay?" title={info?.eval ? `Routing policies on ${info.eval.held_out_difficulty} held-out prompts, priced by real OCI calls` : "run classifier/evaluate.py"}
        right={<Database className="size-4 text-ink-3" />}>
        {info?.eval && (
          <table className="w-full text-[12.5px]">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-3">
              <th className="py-1.5">Policy</th><th>Answers good enough</th><th>Cost of answers</th><th>Classifier cost</th><th>Picked the labelled route</th><th>Code / language routes</th></tr></thead>
            <tbody>{info.eval.policies.map((p) => (
              <tr key={p.policy} className={p.policy === "trained" ? "bg-oracle-soft/40 font-semibold" : "border-b border-line/60"}>
                <td className="py-1.5 font-mono">{p.policy}</td><td>{Math.round(p.quality * 100)}%</td><td className="font-mono">{usd(p.cost_usd)}</td>
                <td className="font-mono">{usd(p.classifier_cost_usd)}</td><td>{Math.round(p.route_match * 100)}%</td>
                <td>{p.task_type_accuracy === null ? "—" : `${Math.round(p.task_type_accuracy * 100)}%`}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
