"use client";
// AI 문장 카드: 버튼 → "꿀벌이 생각 중…"(또는 대기열 순번) → 글자가 써지듯 → "AI가 작성했어요" 배지.
// 서버(api/moneyon_ai.py)가 4초 안에 첫 글자가 없거나 실패하면 준비된 결과를 같은 흐름으로 보내 준다.
import { useEffect, useRef, useState } from "react";
import Izani from "./Izani";

export type AiFeature = "letter" | "coach" | "parent";
export type AiStream = (feature: AiFeature, body: object, signal: AbortSignal) => Promise<Response>;
type Phase = "idle" | "queue" | "thinking" | "writing" | "done" | "error";
type Source = "ai" | "prepared" | "rule";

const STALL_MS = 20000; // 서버 이벤트가 이만큼 끊기면 멈춘 것으로 보고 안내한다

/** text/event-stream을 읽어 이벤트마다 onEvent를 부른다. */
async function readEvents(res: Response, onEvent: (event: string, data: Record<string, unknown>) => void, signal: AbortSignal) {
  const reader = res.body!.getReader();
  // apiFetch는 응답 머리까지만 취소 신호를 이어 준다. 본문 읽기는 여기서 직접 끊는다.
  signal.addEventListener("abort", () => { void reader.cancel().catch(() => {}); }, { once: true });
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message", data = "{}";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      try { onEvent(event, JSON.parse(data)); } catch { /* 깨진 줄은 건너뛴다 */ }
    }
  }
}

export default function AiCard({ feature, stream, body, title, button, again = "다시 써 줘", audience = "kid", ready = true, className = "", autoStart = false }: {
  feature: AiFeature; stream: AiStream; body?: object; title: string; button: string; again?: string;
  audience?: "kid" | "parent"; ready?: boolean; className?: string; autoStart?: boolean;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [text, setText] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [position, setPosition] = useState(0);
  const [error, setError] = useState("");
  const [fade, setFade] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const card = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (autoStart) void go(); // go()는 앞선 요청을 먼저 취소하므로 개발 모드 이중 실행에도 하나만 남는다
    return () => abort.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function go() {
    abort.current?.abort();
    const ctl = new AbortController();
    abort.current = ctl;
    setPhase("thinking"); setText(""); setSource(null); setError(""); setPosition(0);
    // 시트 아래쪽에 있어도 생각 중·글이 보이게(휴대폰 코치 시트)
    requestAnimationFrame(() => card.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
    let stall: ReturnType<typeof setTimeout> | undefined;
    const kick = () => { clearTimeout(stall); stall = setTimeout(() => ctl.abort(), STALL_MS); };
    kick();
    try {
      const res = await stream(feature, body ?? {}, ctl.signal);
      if (!res.ok) {
        let detail = "";
        try { detail = (await res.json())?.detail ?? ""; } catch { /* */ }
        throw new Error(typeof detail === "string" && detail ? detail : "지금은 꿀벌이 쉬는 중이에요. 잠시 후 다시 눌러 주세요.");
      }
      await readEvents(res, (event, data) => {
        kick();
        if (event === "queue") { setPhase("queue"); setPosition(Number(data.position) || 0); }
        else if (event === "thinking") setPhase(p => (p === "writing" ? p : "thinking"));
        else if (event === "delta") { setPhase("writing"); setText(t => t + String(data.text ?? "")); }
        else if (event === "replace") {
          setFade(true);
          setTimeout(() => { setText(String(data.text ?? "")); setSource(data.source as Source); setFade(false); }, 250);
        } else if (event === "done") { setSource(s => (data.source as Source) ?? s); setPhase("done"); }
      }, ctl.signal);
      setPhase(p => (p === "done" ? p : "done"));
    } catch (e) {
      setError(ctl.signal.aborted ? "응답이 늦어요. 다시 눌러 볼까요?" : (e as Error).message || "잠시 후 다시 눌러 주세요.");
      setPhase("error");
    } finally {
      clearTimeout(stall);
    }
  }

  const busy = phase === "thinking" || phase === "queue" || phase === "writing";
  const lines = text.split("\n");
  return (
    <section ref={card} className={`mk-ai-card mk-ai-${audience} ${className}`} aria-label={title} aria-busy={busy}>
      <div className="mk-ai-head">
        <span className="mk-ai-title">{title}</span>
        {phase === "done" && (source === "ai" || source === "prepared") && (
          <span className="mk-ai-badge" title="숫자는 앱이 계산했고, 문장은 AI가 이름 없이 숫자만 받아 썼어요. 틀릴 수 있어요.">
            ✨ AI가 작성했어요{source === "prepared" ? " · 미리 준비" : ""}
          </span>
        )}
        {phase === "done" && source === "rule" && <span className="mk-ai-badge plain">꿀벌 기본 {audience === "parent" ? "리포트" : "글"}</span>}
      </div>

      {phase === "idle" && (
        <button type="button" className="mk-button full mk-ai-go" disabled={!ready} onClick={() => void go()}>
          <span aria-hidden="true">✨</span>{button}
        </button>
      )}

      {(phase === "thinking" || phase === "queue") && (
        <div className="mk-ai-thinking" role="status">
          <Izani mood="greeting" className="mk-ai-bee" />
          <span>{phase === "queue" ? <>순서대로 쓰고 있어요{position > 0 ? ` · 앞에 ${position}명` : ""}</> : "꿀벌이 생각 중"}</span>
          <i aria-hidden="true" className="mk-ai-dots"><b /><b /><b /></i>
        </div>
      )}

      {(phase === "writing" || phase === "done") && (
        <div className={`mk-ai-text${fade ? " fading" : ""}`} aria-live="polite">
          {lines.map((line, i) => {
            // "소비 패턴: …", "이번 주 할 일: …"은 머리말만 굵게, 나머지는 보통 글씨
            const head = line.match(/^(소비 패턴|칭찬 포인트|대화 팁|이번 주 할 일):\s*(.*)$/);
            const caret = phase === "writing" && i === lines.length - 1 && <span className="mk-ai-caret" aria-hidden="true" />;
            if (head) return <p key={i} className={head[2] ? "" : "label"}><strong className="mk-ai-head-label">{head[1]}:</strong>{head[2] ? " " + head[2] : ""}{caret}</p>;
            return <p key={i} className={/^- /.test(line) ? "bullet" : ""}>{line.replace(/^- /, "")}{caret}</p>;
          })}
        </div>
      )}

      {phase === "error" && <p className="mk-ai-error" role="alert">{error}</p>}
      {(phase === "done" || phase === "error") && (
        <button type="button" className="mk-text-button mk-ai-again" onClick={() => void go()}>{phase === "error" ? "다시 눌러 보기" : again}</button>
      )}
    </section>
  );
}
