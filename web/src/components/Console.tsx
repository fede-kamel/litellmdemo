import clsx from "clsx";
import { Maximize2, Minimize2, Pause, Play, TerminalSquare, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

type Line = { t: number; source: string; text: string; tone: "allow" | "deny" | "route" | "info" };
type Filter = "sandbox" | "gateway" | "all";

// one tag per source: the sandbox's own lines, then the gateway's (LiteLLM, the classifier, the laptop gateway)
const TAG: Record<string, { label: string; cls: string }> = {
  openshell: { label: "sandbox", cls: "text-[#7ee787]" },
  litellm: { label: "litellm", cls: "text-[#79c0ff]" },
  classifier: { label: "classifier", cls: "text-[#d2a8ff]" },
  laptop: { label: "laptop", cls: "text-[#8b949e]" },
};
const FILTERS: { id: Filter; label: string }[] = [{ id: "sandbox", label: "Sandbox" }, { id: "gateway", label: "Gateway" }, { id: "all", label: "All" }];
const isSandbox = (l: Line) => l.source === "openshell";

// OpenShell's lines arrive as `NET:OPEN [INFO] ALLOWED /usr/local/bin/python3.12(0) -> 10.0.0.4:30400 [policy:_provider_litellm_agent engine:opa]`.
// Keep what a reader needs: the decision, the process and the destination; drop the bookkeeping.
function tidy(text: string): string {
  return text
    .replace(/ \[(INFO|LOW|MED|HIGH|WARN|ERROR)\]/g, "")
    .replace(/ mapping_id=[0-9a-f-]+/g, "")
    .replace(/ engine:[a-z0-9]+\]/g, "]")
    .replace(/http:\/\/([^/\s]+):443\//g, "https://$1/")
    .replace(/\/usr\/local\/bin\/(python[0-9.]+)\(\d+\)/g, "$1");
}

const TOKENS = /(ALLOWED|DENIED|REFUSED|NET:[A-Z]+|HTTP:[A-Z]+|CONFIG:[A-Z]+|\[policy:[^\]]+\]|\[reason:[^\]]+\])/;
function highlight(text: string) {
  return text.split(TOKENS).map((t, i) => {
    if (t === "ALLOWED") return <span key={i} className="rounded bg-[#1f3d29] px-1 font-semibold text-[#7ee787]">ALLOWED</span>;
    if (t === "DENIED" || t === "REFUSED") return <span key={i} className="rounded bg-[#4a1f1f] px-1 font-semibold text-[#ff7b72]">{t}</span>;
    if (/^(NET|HTTP):/.test(t)) return <span key={i} className="text-[#d2a8ff]">{t}</span>;
    if (t.startsWith("CONFIG:")) return <span key={i} className="text-[#79c0ff]">{t}</span>;
    if (t.startsWith("[policy:")) return <span key={i} className="text-[#e3b341]">{t}</span>;
    if (t.startsWith("[reason:")) return <span key={i} className="text-[#ff7b72]">{t}</span>;
    return t;
  });
}

/** Every connection the sandbox opens or is refused, next to the gateway's decision for it: live lines
 * from OpenShell, LiteLLM and the classifier, as they log them. One switch: the sandbox, the gateway, everything. */
export function Console() {
  const [lines, setLines] = useState<Line[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [paused, setPaused] = useState(false);
  const [full, setFull] = useState(false);
  const [live, setLive] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  const stick = useRef(true);
  const pausedRef = useRef(false);
  pausedRef.current = paused;

  useEffect(() => {
    let src: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const connect = () => {
      src = new EventSource("/api/console");
      src.onopen = () => setLive(true);
      src.onmessage = (m) => {
        if (pausedRef.current) return;
        const line = JSON.parse(m.data) as Line;
        setLines((v) => (v.length > 800 ? [...v.slice(-600), line] : [...v, line]));
      };
      src.onerror = () => { setLive(false); src?.close(); retry = setTimeout(connect, 3000); };   // reconnect on its own
    };
    connect();
    return () => { src?.close(); if (retry) clearTimeout(retry); };
  }, []);

  useEffect(() => {
    if (!full) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [full]);

  const shown = useMemo(() => (filter === "all" ? lines : lines.filter((l) => (filter === "sandbox") === isSandbox(l))), [lines, filter]);
  const counts = useMemo(() => ({
    allowed: lines.filter((l) => isSandbox(l) && l.tone === "allow").length,
    denied: lines.filter((l) => isSandbox(l) && l.tone === "deny").length,
    routed: lines.filter((l) => !isSandbox(l) && l.tone === "route" && l.source !== "classifier").length,
  }), [lines]);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [shown.length, full]);

  const time = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });
  const icon = "rounded-md p-1 text-[#8b949e] hover:bg-[#2a2a2a] hover:text-white";

  return (
    <section className={clsx("flex flex-col overflow-hidden border border-[#2a2a2a] bg-[#141414] text-[#c9d1d9]", full ? "fixed inset-0 z-50 rounded-none" : "rounded-2xl")}>
      <header className="flex h-10 shrink-0 items-center gap-3 border-b border-[#262626] bg-[#1d1d1d] px-3.5 font-mono text-[12px]">
        <div className="flex items-center gap-2 text-[#c9d1d9]">
          <TerminalSquare className="size-3.5 text-[#7ee787]" />
          <span className="font-semibold">Sandbox console</span>
          {live && <span className="live-dot ml-1 size-1.5 rounded-full bg-oracle" />}
        </div>
        <div className="min-w-0 truncate text-[11.5px] text-[#8b949e]">
          <span className="text-[#7ee787]">{counts.allowed} allowed</span> · <span className={counts.denied ? "text-[#ff7b72]" : undefined}>{counts.denied} denied</span> · {counts.routed} routed
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <div className="flex overflow-hidden rounded-md border border-[#30363d] text-[11px]">
            {FILTERS.map((f) => (
              <button key={f.id} onClick={() => setFilter(f.id)} className={clsx("px-2.5 py-1", filter === f.id ? "bg-[#30363d] text-white" : "text-[#8b949e] hover:text-white")}>{f.label}</button>
            ))}
          </div>
          <button onClick={() => setPaused(!paused)} className={icon} title={paused ? "resume" : "pause"}>{paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}</button>
          <button onClick={() => setLines([])} className={icon} title="clear"><Trash2 className="size-3.5" /></button>
          <button onClick={() => setFull(!full)} className={icon} title={full ? "Exit full screen (Esc)" : "Full screen"}>{full ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}</button>
        </div>
      </header>
      <div ref={box} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}
        className={clsx("scroll-term min-h-0 overflow-y-auto px-4 py-3 font-mono text-[12px] leading-[1.7]", full ? "flex-1" : "h-[300px]")}>
        {!shown.length && <div className="text-[#6e7681]">{live ? "Waiting for the sandbox: route a request, or try to escape." : "Nothing in this view yet."}</div>}
        {shown.map((l, i) => {
          const tag = TAG[l.source] ?? { label: l.source, cls: "text-[#8b949e]" };
          return (
            <div key={i} className="whitespace-pre-wrap break-all">
              <span className="text-[#6e7681]">{time(l.t)}  </span>
              <span className={clsx("whitespace-pre", tag.cls)}>{tag.label.padEnd(10)}</span>{" "}
              <span className={clsx(l.tone === "deny" && "text-[#ff7b72]", l.tone === "route" && "text-[#e6edf3]")}>{highlight(isSandbox(l) ? tidy(l.text) : l.text)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
