import clsx from "clsx";
import { Activity, Brain, MessageSquareText, Network, Route, Scale } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getJSON, usd } from "./api";
import { Ask } from "./components/Ask";
import { ClassifierView } from "./components/ClassifierView";
import { Compare } from "./components/Compare";
import { ControlRoom } from "./components/ControlRoom";
import { GatewayView } from "./components/GatewayView";

type Tab = "ask" | "room" | "compare" | "classifier" | "gateway";
type Stats = { calls: number; spend_usd: number; by_route: Record<string, number>; by_deployment: Record<string, number>; fallbacks: number };

const TABS: { id: Tab; label: string; icon: typeof Route }[] = [
  { id: "ask", label: "Ask and explain", icon: MessageSquareText },
  { id: "room", label: "Control room", icon: Route },
  { id: "compare", label: "Compare routers", icon: Scale },
  { id: "classifier", label: "Classifier", icon: Brain },
  { id: "gateway", label: "Gateway", icon: Network },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [stats, setStats] = useState<Stats | null>(null);
  const [gw, setGw] = useState<{ active: string; role: string } | null>(null);
  useEffect(() => {
    const poll = () => getJSON<{ active: string; role: string }>("/api/gateways").then(setGw).catch(() => setGw(null));
    poll(); const id = setInterval(poll, 10000); return () => clearInterval(id);
  }, []);
  const refresh = useCallback(() => { getJSON<Stats>("/api/stats").then(setStats).catch(() => undefined); }, []);
  useEffect(refresh, [refresh]);

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
          {gw && <span title={gw.active} className={clsx("whitespace-nowrap rounded-full px-2.5 py-1 font-semibold", gw.role === "primary" ? "bg-indigo-soft text-indigo" : "bg-ochre-soft text-ochre")}>
            gateway: {gw.role === "primary" ? "primary" : "fallback"} · {gw.active.replace("http://127.0.0.1:", ":")}</span>}
          <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-moss-soft px-2.5 py-1 font-semibold text-moss"><Activity className="size-3.5" />{stats?.calls ?? 0} routed calls</span>
          <span className="whitespace-nowrap rounded-full bg-teal-soft px-2.5 py-1 font-semibold text-teal">spend {usd(stats?.spend_usd)}</span>
          {stats && stats.fallbacks > 0 && <span className="rounded-full bg-ochre-soft px-2.5 py-1 font-semibold text-ochre">{stats.fallbacks} fallbacks</span>}
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-5">
        {tab === "ask" && <Ask />}
        {tab === "room" && <ControlRoom onCall={refresh} />}
        {tab === "compare" && <Compare />}
        {tab === "classifier" && <ClassifierView />}
        {tab === "gateway" && <GatewayView usage={stats?.by_deployment ?? {}} />}
      </main>
    </div>
  );
}
