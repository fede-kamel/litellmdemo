import clsx from "clsx";
import { ChevronDown, Pause, Play, TerminalSquare, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type Line = { t: number; source: string; text: string; tone: "allow" | "deny" | "route" | "info" };

// one colour per source, the roles the rest of the screen uses: moss = the sandbox, indigo = LiteLLM, violet = the classifier
const SOURCES: { id: string; label: string; tag: string }[] = [
  { id: "openshell", label: "OpenShell sandbox", tag: "text-moss" },
  { id: "litellm", label: "LiteLLM gateway", tag: "text-indigo" },
  { id: "classifier", label: "classifier", tag: "text-violet" },
  { id: "laptop", label: "laptop gateway", tag: "text-ink-3" },
];
const TAG: Record<string, string> = Object.fromEntries(SOURCES.map((s) => [s.id, s.tag]));
const SHORT: Record<string, string> = { openshell: "openshell", litellm: "litellm  ", classifier: "classifier", laptop: "laptop   " };

/** Live lines from OpenShell, LiteLLM and the classifier, as the gateway and the sandbox log them. */
export function Console() {
  const [lines, setLines] = useState<Line[]>([]);
  const [open, setOpen] = useState(true);
  const [paused, setPaused] = useState(false);
  const [on, setOn] = useState<Record<string, boolean>>({ openshell: true, litellm: true, classifier: true, laptop: true });
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
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [lines, open]);

  const shown = lines.filter((l) => on[l.source] ?? true);
  const time = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });

  return (
    <section className="rounded-2xl border border-line bg-well text-ink-2">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2">
        <TerminalSquare className="size-4 text-moss" />
        <span className="text-[12.5px] font-semibold text-ink">Console</span>
        <span className={clsx("flex items-center gap-1 text-[11px]", live ? "text-moss" : "text-oracle")}>
          <span className={clsx("size-1.5 rounded-full", live ? "animate-pulse bg-moss" : "bg-oracle")} />{live ? "live" : "reconnecting"}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {SOURCES.map((s) => (
            <button key={s.id} onClick={() => setOn((v) => ({ ...v, [s.id]: !v[s.id] }))}
              className={clsx("rounded-md border px-2 py-0.5 font-mono text-[10.5px]", on[s.id] ? `border-line bg-panel ${s.tag}` : "border-transparent text-ink-3 line-through")}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setPaused(!paused)} className="rounded p-1 hover:bg-sand" title={paused ? "resume" : "pause"}>{paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}</button>
          <button onClick={() => setLines([])} className="rounded p-1 hover:bg-sand" title="clear"><Trash2 className="size-3.5" /></button>
          <button onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-sand" title={open ? "collapse" : "expand"}><ChevronDown className={clsx("size-4 transition", !open && "rotate-180")} /></button>
        </div>
      </div>
      {open && (
        <div ref={box} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30; }}
          className="scroll-thin h-[240px] overflow-y-auto px-4 py-2 font-mono text-[11.5px] leading-[1.55]">
          {!shown.length && <div className="text-ink-3">waiting for activity: route a request, or try to escape the sandbox</div>}
          {shown.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              <span className="text-ink-3">{time(l.t)} </span>
              <span className={TAG[l.source] ?? "text-ink-3"}>{SHORT[l.source] ?? l.source}</span>{"  "}
              <span className={clsx(l.tone === "deny" && "text-oracle", l.tone === "allow" && "text-moss", l.tone === "route" && "text-ink")}>{l.text}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
