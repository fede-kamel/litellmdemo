import clsx from "clsx";
import { ChevronDown, Pause, Play, TerminalSquare, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type Line = { t: number; source: string; text: string; tone: "allow" | "deny" | "route" | "info" };

const SOURCES: { id: string; label: string; tag: string }[] = [
  { id: "openshell", label: "OpenShell sandbox", tag: "text-[#9be15d]" },
  { id: "litellm", label: "LiteLLM gateway", tag: "text-[#a5a1ff]" },
  { id: "classifier", label: "classifier", tag: "text-[#d6a8ff]" },
  { id: "laptop", label: "laptop gateway", tag: "text-[#9aa1ac]" },
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
    <section className="rounded-2xl border border-[#2a2f3a] bg-[#0f1218] text-[#d7dbe2] shadow-sm">
      <div className="flex flex-wrap items-center gap-3 border-b border-[#2a2f3a] px-4 py-2">
        <TerminalSquare className="size-4 text-[#9be15d]" />
        <span className="text-[12.5px] font-semibold">Console</span>
        <span className={clsx("flex items-center gap-1 text-[11px]", live ? "text-[#9be15d]" : "text-[#e07a6b]")}>
          <span className={clsx("size-1.5 rounded-full", live ? "animate-pulse bg-[#9be15d]" : "bg-[#e07a6b]")} />{live ? "live" : "reconnecting"}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {SOURCES.map((s) => (
            <button key={s.id} onClick={() => setOn((v) => ({ ...v, [s.id]: !v[s.id] }))}
              className={clsx("rounded-md border px-2 py-0.5 font-mono text-[10.5px]", on[s.id] ? `border-[#3a4150] ${s.tag}` : "border-transparent text-[#5b6170] line-through")}>
              {s.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setPaused(!paused)} className="rounded p-1 hover:bg-[#1c212b]" title={paused ? "resume" : "pause"}>{paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}</button>
          <button onClick={() => setLines([])} className="rounded p-1 hover:bg-[#1c212b]" title="clear"><Trash2 className="size-3.5" /></button>
          <button onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-[#1c212b]" title={open ? "collapse" : "expand"}><ChevronDown className={clsx("size-4 transition", !open && "rotate-180")} /></button>
        </div>
      </div>
      {open && (
        <div ref={box} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30; }}
          className="scroll-thin h-[240px] overflow-y-auto px-4 py-2 font-mono text-[11.5px] leading-[1.55]">
          {!shown.length && <div className="text-[#5b6170]">waiting for activity: route a request above, or press "Try to escape"</div>}
          {shown.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              <span className="text-[#5b6170]">{time(l.t)} </span>
              <span className={TAG[l.source] ?? "text-[#9aa1ac]"}>{SHORT[l.source] ?? l.source}</span>{"  "}
              <span className={clsx(l.tone === "deny" && "text-[#ff8a7a]", l.tone === "allow" && "text-[#9be15d]", l.tone === "route" && "text-[#f2f4f8]")}>{l.text}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
