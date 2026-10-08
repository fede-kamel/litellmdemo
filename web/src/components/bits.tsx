import clsx from "clsx";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ROUTE_STYLE, shortModel, vendor } from "../api";

export function RouteChip({ route, size = "sm" }: { route?: string; size?: "sm" | "lg" }) {
  const s = ROUTE_STYLE[route ?? ""] ?? { tone: "bg-sand text-ink-3 border-line" };
  return (
    <span className={clsx("inline-flex items-center rounded-md border font-mono font-semibold tracking-wide", s.tone,
      size === "lg" ? "px-2.5 py-1 text-[12px]" : "px-1.5 py-0.5 text-[10.5px]")}>{route ?? "—"}</span>
  );
}

const VENDOR_TONE: Record<string, string> = {
  OpenAI: "bg-[#10a37f]/20 text-[#4fd6a8]", Google: "bg-[#4285f4]/20 text-[#8db4ff]", Meta: "bg-[#0866ff]/20 text-[#7aa7ff]",
  xAI: "bg-ink/10 text-ink", Cohere: "bg-[#ff7759]/20 text-[#ff9f88]",
};

export function ModelChip({ deployment, lit }: { deployment?: string; lit?: boolean }) {
  const v = vendor(deployment);
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-0.5 text-[11.5px]", lit && "lit border-oracle/50")}>
      {v && <span className={clsx("rounded px-1 text-[9.5px] font-semibold uppercase tracking-wide", VENDOR_TONE[v])}>{v}</span>}
      <span className="font-mono text-ink-2">{shortModel(deployment)}</span>
    </span>
  );
}

export function Panel({ title, kicker, children, right, className }: { title?: ReactNode; kicker?: string; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={clsx("rounded-2xl border border-line bg-panel", className)}>
      {(title || kicker) && (
        <div className="flex items-center gap-3 border-b border-line/70 px-5 py-3">
          <div>
            {kicker && <div className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-oracle">{kicker}</div>}
            {title && <div className="text-[14px] font-semibold">{title}</div>}
          </div>
          <div className="ml-auto">{right}</div>
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Bars({ values, max }: { values: Record<string, number>; max?: number }) {
  const top = max ?? Math.max(0.0001, ...Object.values(values));
  return (
    <div className="space-y-1">
      {Object.entries(values).map(([k, v]) => (
        <div key={k} className="flex items-center gap-2 text-[11px]">
          <span className="w-[96px] shrink-0 font-mono text-ink-3">{k}</span>
          <div className="h-2 flex-1 rounded-full bg-sand"><div className="h-2 rounded-full bg-oracle/80" style={{ width: `${(v / top) * 100}%` }} /></div>
          <span className="w-10 text-right font-mono text-ink-2">{v < 1 ? `${Math.round(v * 100)}%` : v}</span>
        </div>
      ))}
    </div>
  );
}

/** A model's answer: markdown (headings, lists, tables, code), styled for the panel. */
export function Answer({ text }: { text?: string }) {
  return (
    <div className="answer text-[13px] leading-relaxed text-ink-2">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text ?? ""}</ReactMarkdown>
    </div>
  );
}
