"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  PROVIDER_LABELS,
  streamChat,
  type ChatMessage,
  type Provider,
  type SearchMode,
  type ToolEvent,
} from "@/lib/agent";

const TOOL_CHIPS = [
  { icon: "📊", title: "DART", desc: "기업 공시" },
  { icon: "⚖️", title: "LAW", desc: "법령 검색" },
  { icon: "🔍", title: "WEB", desc: "실시간 검색" },
  { icon: "🧮", title: "TOOL", desc: "계산 · 시간" },
];

const EXAMPLES = ["삼성전자 최근 공시 알려줘", "전자금융거래법 검색해줘", "오늘 주요 경제 뉴스 요약해줘"];

function Segmented<T extends string>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-xl bg-surface-muted p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.value)}
          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition sm:text-sm ${
            value === o.value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"
          } disabled:opacity-60`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ToolSteps({ tools, running }: { tools: ToolEvent[]; running?: boolean }) {
  if (!tools.length && !running) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {tools.map((t, i) => {
        const arg = Object.values(t.input ?? {})[0];
        return (
          <span key={i} className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-accent">
            ✓ {t.label}
            {typeof arg === "string" && arg ? ` · ${arg.length > 24 ? arg.slice(0, 24) + "…" : arg}` : ""}
          </span>
        );
      })}
      {running && (
        <span className="animate-pulse rounded-full bg-surface-muted px-2.5 py-1 text-[11px] font-semibold text-muted">
          {tools.length ? "결과를 정리하는 중…" : "생각하는 중…"}
        </span>
      )}
    </div>
  );
}

export default function AgentChat() {
  const [provider, setProvider] = useState<Provider>("claude");
  const [searchMode, setSearchMode] = useState<SearchMode>("빠르게");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingTools, setPendingTools] = useState<ToolEvent[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (messages.length) bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pendingTools, loading]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || loading) return;

    const history: ChatMessage[] = [...messages, { role: "user", content }];
    setMessages(history);
    setInput("");
    setError("");
    setPendingTools([]);
    setLoading(true);

    const controller = new AbortController();
    abortRef.current = controller;
    const tools: ToolEvent[] = [];

    try {
      await streamChat(
        history,
        provider,
        searchMode,
        {
          onTool: (t) => {
            tools.push(t);
            setPendingTools([...tools]);
          },
          onAnswer: (a) => {
            setMessages((prev) => [
              ...prev,
              { role: "assistant", content: a.text, provider: a.provider, searchMode: a.search_mode, tools },
            ]);
          },
        },
        controller.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요.");
      }
    } finally {
      setLoading(false);
      setPendingTools([]);
      abortRef.current = null;
    }
  }

  function reset() {
    abortRef.current?.abort();
    setMessages([]);
    setError("");
  }

  return (
    <div className="rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          value={provider}
          onChange={setProvider}
          disabled={loading}
          options={[
            { value: "claude", label: PROVIDER_LABELS.claude },
            { value: "gpt", label: PROVIDER_LABELS.gpt },
          ]}
        />
        <Segmented
          value={searchMode}
          onChange={setSearchMode}
          disabled={loading}
          options={[
            { value: "빠르게", label: "⚡ 빠르게" },
            { value: "심층 검색", label: "🔎 심층 검색" },
          ]}
        />
        {messages.length > 0 && (
          <button type="button" onClick={reset} className="ml-auto text-xs font-semibold text-muted hover:text-fg">
            ↺ 대화 초기화
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-subtle">
        {searchMode === "심층 검색"
          ? "웹 결과 최대 8건 · 본문 확대 · 긴 답변"
          : "웹 결과 최대 5건 · 빠른 검색과 핵심 답변"}
      </p>

      <div className="mt-4 grid grid-cols-4 gap-2">
        {TOOL_CHIPS.map((c) => (
          <div key={c.title} className="flex flex-col items-center gap-1 rounded-xl border border-border px-2 py-2.5 text-center sm:flex-row sm:gap-2.5 sm:px-3 sm:text-left">
            <span className="text-base">{c.icon}</span>
            <div>
              <div className="text-[11px] font-extrabold sm:text-xs">{c.title}</div>
              <div className="hidden text-[11px] text-subtle sm:block">{c.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-5 space-y-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => send(ex)}
                className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-accent/40 hover:text-accent"
              >
                {ex}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-white">
                {m.content}
              </div>
            </div>
          ) : (
            <div key={i} className="rounded-2xl rounded-bl-md border border-border bg-surface-muted/60 px-4 py-3">
              <div className="mb-1.5 text-[11px] font-semibold text-subtle">
                {m.provider ? PROVIDER_LABELS[m.provider] : ""} · {m.searchMode}
              </div>
              <ToolSteps tools={m.tools ?? []} />
              <div className="prose-answer">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{ a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}
                >
                  {m.content}
                </ReactMarkdown>
              </div>
            </div>
          ),
        )}

        {loading && (
          <div className="rounded-2xl rounded-bl-md border border-border bg-surface-muted/60 px-4 py-3">
            <ToolSteps tools={pendingTools} running />
          </div>
        )}

        {error && <div className="rounded-xl bg-red-500/10 px-4 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <form
        className="mt-4 flex items-end gap-2 rounded-2xl border border-border bg-surface p-2 focus-within:border-accent/60"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          placeholder="예: 삼성전자 최근 공시 알려줘 / 전자금융거래법 검색해줘"
          className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-subtle"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-bold text-white transition hover:bg-accent-strong disabled:opacity-40"
        >
          보내기
        </button>
      </form>
    </div>
  );
}
