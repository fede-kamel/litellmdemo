import clsx from "clsx";
import { KeyRound, ShieldCheck, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { getJSON, postJSON, usd } from "../api";

type Key = { key_alias: string; models: string[]; max_budget: number; spend: number; rpm_limit: number };
type Sandbox = { ready: boolean; name: string; gateway: string; cluster?: string; key: Key | null };
type Probe = null | "running" | { tries: { target: string; result: string }[] };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-panel p-5">
      <div className="mb-3 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle">{title}</div>
      {children}
    </section>
  );
}

function Card({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-xl bg-well px-3.5 py-2.5">
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">{icon}{title}</div>
      <div className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{children}</div>
    </div>
  );
}

/** What keeps the agent in bounds, layer by layer: OpenShell, LiteLLM, OCI. Each one measured; none asks the agent to behave. */
export function Safety({ onClose }: { onClose: () => void }) {
  const [sb, setSb] = useState<Sandbox | null>(null);
  const [probe, setProbe] = useState<Probe>(null);
  useEffect(() => { getJSON<Sandbox>("/api/sandbox").then(setSb).catch(() => setSb(null)); }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const escape = async () => { setProbe("running"); setProbe(await postJSON("/api/sandbox/probe", {})); };
  const gateway = sb?.gateway.replace(/^https?:\/\//, "") ?? "the LiteLLM gateway";
  const key = sb?.key;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/20" onClick={onClose}>
      <aside className="flex h-full w-[min(860px,100vw)] flex-col border-l border-line bg-paper shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <header className="flex h-[52px] shrink-0 items-center gap-3 border-b border-line bg-panel px-5">
          <ShieldCheck className="size-4 text-moss" />
          <span className="text-[14px] font-semibold">Safety</span>
          <span className="text-[12px] text-ink-3">Three layers, each measured; none asks the agent to behave. Esc to close.</span>
          <button onClick={onClose} className="ml-auto rounded-md p-1 text-ink-3 hover:bg-sand hover:text-ink" title="close"><X className="size-4" /></button>
        </header>
        <div className="scroll-thin min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-[13.5px] leading-relaxed text-ink-2">OpenShell decides what the agent can reach, LiteLLM decides which model answers and what the key may spend, and OCI signs nothing for anyone but the gateway.</p>

          <Section title="NVIDIA OpenShell sandbox · network">
            <table className="w-full text-[13px]">
              <tbody>
                <tr className="border-b border-line/60 align-top">
                  <td className="py-2 pr-3"><span className="rounded bg-moss-soft px-1.5 py-0.5 text-[11px] font-semibold text-moss">ALLOWED</span></td>
                  <td className="py-2 pr-3"><div className="font-mono text-[12px] text-ink">{gateway}</div><div className="text-ink-3">POST /v1/chat/completions · GET /v1/models</div></td>
                  <td className="py-2 text-ink-3">placeholder key, swapped by the OpenShell proxy</td>
                </tr>
                <tr className="align-top">
                  <td className="py-2 pr-3"><span className="rounded bg-oracle-soft px-1.5 py-0.5 text-[11px] font-semibold text-oracle">REFUSED</span></td>
                  <td className="py-2" colSpan={2}><span className="text-ink-2">everything else</span> <span className="text-ink-3">· no rule, so no connection opens; only <span className="font-mono text-[12px]">/usr/local/bin/python3.12</span> may connect</span></td>
                </tr>
              </tbody>
            </table>
            <div className="mt-3 text-[12px] text-ink-3">
              Measured from inside the sandbox by <span className="font-mono">scripts/openshell.sh probe</span>: OCI Generative AI, api.openai.com and the gateway's admin API, all refused.
              {sb?.name && <> Sandbox <span className="font-mono">{sb.name}</span>; its only credential is a placeholder.</>}
            </div>
            <button onClick={escape} disabled={probe === "running" || sb?.ready === false} className="mt-3 rounded-lg border border-line px-2.5 py-1.5 text-[12px] font-semibold text-ink-2 hover:border-oracle/50 disabled:text-ink-3">
              {probe === "running" ? "trying…" : "Try to escape: call OCI or OpenAI directly"}
            </button>
            {probe && probe !== "running" && (
              <div className="mt-2 space-y-0.5 text-[12px]">
                {probe.tries.map((t) => <div key={t.target} className={t.result.startsWith("REFUSED") ? "text-oracle" : "text-ochre"}>✕ {t.target}: {t.result}</div>)}
              </div>
            )}
          </Section>

          <Section title="LiteLLM AI Gateway">
            <div className="grid grid-cols-2 gap-2">
              <Card title="Key check" icon={<KeyRound className="size-3.5 text-ink-3" />}>
                {key ? <><span className="font-mono text-[12px]">{key.key_alias}</span> may call {key.models?.length ?? "?"} model groups · {usd(key.spend)} of ${key.max_budget} · {key.rpm_limit} a minute. Anything else is a 403.</>
                  : "The agent's virtual key names its model groups, its budget and its rate limit; anything else is a 403."}
              </Card>
              <Card title="Classify">The complexity router calls our classifier (<span className="font-mono text-[12px]">classifier_type: custom</span>) on every call, before any model is called.</Card>
              <Card title="Route">The route names a model group; the fastest healthy deployment answers, with fallbacks.</Card>
              <Card title="Sign">{sb?.cluster === "oke" ? "As its OKE node (instance principal): no key or token in the cluster." : "With the operator's OCI session, kept fresh in a Kubernetes Secret."}</Card>
              <Card title="Account">Cost per call, spend per key, every decision in <span className="font-mono text-[12px]">x-litellm-*</span> headers.</Card>
              <Card title="Observe">One ROUTE line per request and one CLASSIFY line per decision, in the sandbox console.</Card>
            </div>
          </Section>

          <Section title="OCI Generative AI">
            <p className={clsx("text-[13px] leading-relaxed text-ink-2")}>Twenty models from five vendors in us-chicago-1, behind one <span className="font-mono text-[12px]">oci/</span> provider; Codex through OCI's Responses API. The sandbox never sees an OCI credential: only the gateway signs.</p>
          </Section>
        </div>
      </aside>
    </div>
  );
}
