import clsx from "clsx";
import { Brain, MessageSquareText, Network, Route, Scale } from "lucide-react";
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
type Gateway = { active: string; role: string; cluster: string };
// "session": the operator's OCI session signs the calls and runs out; "instance_principal": the OKE node signs, nothing expires
type Session = { mode: "session" | "instance_principal"; minutes_left: number | null; refresher: string };

const TABS: { id: Tab; label: string; icon: typeof Route }[] = [
  { id: "demo", label: "Run the demo", icon: MessageSquareText },
  { id: "hood", label: "How the router decides", icon: Network },
];
const HOOD: { id: Hood; label: string; icon: typeof Route; note: string }[] = [
  { id: "compare", label: "Compare routers", icon: Scale, note: "the same request through LiteLLM's heuristic, its LLM classifier and our ladder" },
  { id: "classifier", label: "The classifier", icon: Brain, note: "how it was labelled and trained, and what it delivers on unseen prompts" },
  { id: "gateway", label: "The gateway", icon: Network, note: "every route, model group and fallback in LiteLLM's config" },
];
const pill = "flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11.5px] font-semibold";

export default function App() {
  const [tab, setTab] = useState<Tab>("demo");
  const [stats, setStats] = useState<Stats | null>(null);
  const [hood, setHood] = useState<Hood>("compare");
  const [gw, setGw] = useState<Gateway | null>(null);
  const [sess, setSess] = useState<Session | null>(null);
  const refresh = useCallback(() => { getJSON<Stats>("/api/stats").then(setStats).catch(() => undefined); }, []);
  useEffect(() => {
    const poll = () => {
      getJSON<Gateway>("/api/gateways").then(setGw).catch(() => setGw(null));
      getJSON<Session>("/api/session").then(setSess).catch(() => setSess(null));
      refresh();
    };
    poll(); const id = setInterval(poll, 5000); return () => clearInterval(id);
  }, [refresh]);
  const left = sess?.minutes_left ?? -1;

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-panel/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1500px] items-center gap-4 px-6 py-2.5">
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
          {/* three facts: what was routed and what it cost; which gateway and how it signs; fallbacks only when there were any */}
          <div className="ml-auto flex items-center gap-2">
            <span className={clsx(pill, "bg-teal-soft text-teal")}>{stats?.calls ?? 0} routed calls{stats?.calls ? ` · ${usd(stats.spend_usd)}` : ""}</span>
            {gw && (
              <span title={gw.active} className={clsx(pill, gw.role === "primary" ? "bg-indigo-soft text-indigo" : "bg-ochre-soft text-ochre")}>
                gateway: {gw.role === "primary" ? "primary" : "fallback"} · {gw.cluster === "oke" ? "OKE" : gw.active.replace("http://127.0.0.1:", ":")}
                {sess?.mode === "instance_principal" && " · signed as the OKE node"}
              </span>
            )}
            {sess?.mode === "session" && (
              <span title={`session refresher: ${sess.refresher}`} className={clsx(pill, left > 15 ? "bg-moss-soft text-moss" : left > 0 ? "bg-ochre-soft text-ochre" : "bg-oracle-soft text-oracle")}>
                OCI session {left > 0 ? `${left} min` : "expired"}{sess.refresher === "needs-login" ? " · log in again" : ""}
              </span>
            )}
            {stats && stats.fallbacks > 0 && <span className={clsx(pill, "bg-ochre-soft text-ochre")}>{stats.fallbacks} fallbacks</span>}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-6 py-5">
        {/* both screens stay mounted: a run survives a look at the router and back */}
        <div className={clsx(tab !== "demo" && "hidden")}><Ask /></div>
        <div className={clsx("space-y-4", tab !== "hood" && "hidden")}>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex rounded-xl bg-sand p-1">
                {HOOD.map((h) => (
                  <button key={h.id} onClick={() => setHood(h.id)}
                    className={clsx("flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] font-semibold", hood === h.id ? "bg-panel text-ink shadow-sm" : "text-ink-3 hover:text-ink")}>
                    <h.icon className="size-3.5" />{h.label}
                  </button>
                ))}
              </div>
              <span className="text-[12px] text-ink-3">{HOOD.find((h) => h.id === hood)?.note}</span>
            </div>
            {hood === "compare" && <Compare />}
            {hood === "classifier" && <ClassifierView />}
            {hood === "gateway" && <GatewayView usage={stats?.by_deployment ?? {}} cluster={gw?.cluster ?? "local"} />}
            <Console />
        </div>
      </main>
    </div>
  );
}
