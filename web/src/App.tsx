import clsx from "clsx";
import { Activity, Brain, MessageSquareText, Network, Route, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getJSON, usd } from "./api";
import { Ask } from "./components/Ask";
import { Console } from "./components/Console";
import { ClassifierView } from "./components/ClassifierView";
import { Compare } from "./components/Compare";
import { GatewayView } from "./components/GatewayView";

type Tab = "demo" | "hood";
type Hood = "compare" | "classifier" | "gateway";
type Stats = { calls: number; spend_usd: number; by_route: Record<string, number>; by_deployment: Record<string, number>; fallbacks: number };

const TABS: { id: Tab; label: string; icon: typeof Route }[] = [
  { id: "demo", label: "Demo", icon: MessageSquareText },
  { id: "hood", label: "Under the hood", icon: Network },
];
const HOOD: { id: Hood; label: string; icon: typeof Route; note: string }[] = [
  { id: "compare", label: "Compare routers", icon: Scale, note: "the same request through LiteLLM's heuristic, its LLM classifier and our ladder" },
  { id: "classifier", label: "The classifier", icon: Brain, note: "how it was labelled and trained, and what it delivers on unseen prompts" },
  { id: "gateway", label: "The gateway", icon: Network, note: "every route, model group and fallback in LiteLLM's config" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("demo");
  const [stats, setStats] = useState<Stats | null>(null);
  const [hood, setHood] = useState<Hood>("compare");
  const [gw, setGw] = useState<{ active: string; role: string } | null>(null);
  const [sess, setSess] = useState<{ minutes_left: number; refresher: string } | null>(null);
  const refresh = useCallback(() => { getJSON<Stats>("/api/stats").then(setStats).catch(() => undefined); }, []);
  useEffect(() => {
    const poll = () => {
      getJSON<{ active: string; role: string }>("/api/gateways").then(setGw).catch(() => setGw(null));
      getJSON<{ minutes_left: number; refresher: string }>("/api/session").then(setSess).catch(() => setSess(null));
      refresh();
    };
    poll(); const id = setInterval(poll, 5000); return () => clearInterval(id);
  }, [refresh]);

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-line bg-panel/95 px-6 py-3 backdrop-blur">
        <div className="grid size-8 place-items-center rounded-lg bg-oracle text-white"><Route className="size-4" /></div>
        <div>
          <div className="text-[14px] font-semibold leading-tight">LiteLLM routing control room</div>
          <div className="whitespace-nowrap text-[11px] text-ink-3">langchain-oci · LiteLLM · OCI Generative AI</div>
        </div>
        <nav className="ml-6 flex gap-1 rounded-xl bg-sand p-1">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={clsx("flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-[12.5px] font-medium", tab === t.id ? "bg-panel text-ink shadow-sm" : "text-ink-3 hover:text-ink")}>
              <t.icon className="size-3.5" />{t.label}
            </button>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-[11.5px]">
          {sess && <span title={`session refresher: ${sess.refresher}`} className={clsx("whitespace-nowrap rounded-full px-2.5 py-1 font-semibold",
            sess.minutes_left > 15 ? "bg-moss-soft text-moss" : sess.minutes_left > 0 ? "bg-ochre-soft text-ochre" : "bg-oracle-soft text-oracle")}>
            OCI session {sess.minutes_left > 0 ? `${sess.minutes_left} min` : "expired"}{sess.refresher === "needs-login" ? " · log in again" : ""}</span>}
          {gw && <span title={gw.active} className={clsx("whitespace-nowrap rounded-full px-2.5 py-1 font-semibold", gw.role === "primary" ? "bg-indigo-soft text-indigo" : "bg-ochre-soft text-ochre")}>
            gateway: {gw.role === "primary" ? "primary" : "fallback"} · {gw.active.replace("http://127.0.0.1:", ":")}</span>}
          <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-moss-soft px-2.5 py-1 font-semibold text-moss"><Activity className="size-3.5" />{stats?.calls ?? 0} routed calls</span>
          <span className="whitespace-nowrap rounded-full bg-teal-soft px-2.5 py-1 font-semibold text-teal">spend {usd(stats?.spend_usd)}</span>
          {stats && stats.fallbacks > 0 && <span className="rounded-full bg-ochre-soft px-2.5 py-1 font-semibold text-ochre">{stats.fallbacks} fallbacks</span>}
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-5">
        {tab === "demo" && <Ask />}
        {tab === "hood" && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {HOOD.map((h) => (
                <button key={h.id} onClick={() => setHood(h.id)}
                  className={clsx("flex max-w-[360px] items-start gap-2 rounded-xl border px-3 py-2 text-left", hood === h.id ? "border-oracle bg-oracle-soft/50" : "border-line bg-panel hover:border-oracle/40")}>
                  <h.icon className="mt-0.5 size-4 shrink-0 text-oracle" />
                  <span><span className="block text-[13px] font-semibold">{h.label}</span><span className="block text-[11.5px] text-ink-3">{h.note}</span></span>
                </button>
              ))}
            </div>
            {hood === "compare" && <Compare />}
            {hood === "classifier" && <ClassifierView />}
            {hood === "gateway" && <GatewayView usage={stats?.by_deployment ?? {}} />}
          </div>
        )}
        <div className="mt-4"><Console /></div>
      </main>
    </div>
  );
}
