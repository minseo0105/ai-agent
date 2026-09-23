"use client";

import { useEffect, useRef, useState } from "react";
import { Field, Segmented, Spinner } from "@/components/golf/ui";
import { reportApi, type ReportChart, type ReportOptions, type ReportResult, type ToolStep } from "@/lib/report";

const KEY = "report-builder-v1";
const PLACEHOLDER =
  "예) 신규 고객 서비스 출시를 검토하고 있어. 최근 고객 문의가 증가하고 있고 기존 처리 방식으로는 대응 시간이 길어지는 문제가 있어. " +
  "서비스 도입 필요성, 기대효과, 예상 리스크, 추진 우선순위와 향후 실행계획이 드러나도록 경영진 보고용으로 정리해줘.\n\n" +
  "메모처럼 간단히 적어도 됩니다 — 신규 사업 검토 / 경쟁사 동향 / 비용 증가 원인 / 규제 변경 영향 / 프로젝트 추진현황";

type Saved = { topic: string; style: string; depth: string; mode: string; result: ReportResult | null };

function load(): Saved | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Saved) : null;
  } catch {
    return null;
  }
}

function DisclosureChart({ chart }: { chart: NonNullable<ReportChart> }) {
  const max = Math.max(...chart.values, 1);
  const h = 140;
  const barW = Math.min(44, Math.max(16, 520 / chart.values.length - 10));
  const w = chart.values.length * (barW + 12) + 12;
  return (
    <figure className="rounded-2xl border border-border bg-surface p-4">
      <figcaption className="mb-2">
        <div className="text-sm font-extrabold">{chart.company} 공시 흐름</div>
        <div className="text-[11px] text-subtle">조회된 DART 공시 건수를 월별로 집계했어요.</div>
      </figcaption>
      <div className="overflow-x-auto">
        <svg width={w} height={h + 34} role="img" aria-label={`${chart.company} 월별 공시 건수`}>
          {chart.values.map((v, i) => {
            const bh = (v / max) * h;
            const x = 12 + i * (barW + 12);
            return (
              <g key={chart.labels[i]}>
                <rect x={x} y={h - bh + 14} width={barW} height={bh} rx={4} className="fill-accent/80" />
                <text x={x + barW / 2} y={h - bh + 8} textAnchor="middle" className="fill-fg text-[11px] font-bold">
                  {v}
                </text>
                <text x={x + barW / 2} y={h + 30} textAnchor="middle" className="fill-muted text-[10px]">
                  {chart.labels[i].slice(2)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </figure>
  );
}

/** 섹션 제목 판별: '[섹션]' 또는 짧고 문장으로 끝나지 않는 줄(예: '핵심 메시지', '① 현황 변화'). services/report.py와 같은 규칙. */
export function headingLevel(line: string): 0 | 1 | 2 {
  const t = line.trim();
  if (/^\[.+\]$/.test(t)) return 1;
  if (t.length > 26 || /[.:!?。]$|다$|요$/.test(t) || /^[-•·*]|^\d+[.)]\s/.test(t)) return 0;
  return /^[①-⑩]/.test(t) ? 2 : 1;
}

function ReportBody({ text }: { text: string }) {
  // AI 출력은 HTML로 해석하지 않고 텍스트로만 렌더링한다.
  const lines = text.split("\n");
  const titleIndex = lines.findIndex((l) => l.trim());
  return (
    <div className="space-y-1.5 text-[15px] leading-relaxed">
      {lines.map((line, i) => {
        const t = line.trim();
        if (!t) return <div key={i} className="h-2" />;
        if (i === titleIndex) {
          return (
            <h2 key={i} className="pb-2 text-xl font-extrabold leading-snug tracking-tight">
              {t.replace(/^\[|\]$/g, "")}
            </h2>
          );
        }
        const level = headingLevel(t);
        if (level === 1) {
          return (
            <h3 key={i} className="pt-4 text-sm font-extrabold tracking-tight text-accent">
              {t.replace(/^\[|\]$/g, "")}
            </h3>
          );
        }
        if (level === 2) {
          return (
            <h4 key={i} className="pt-2 text-[15px] font-bold">
              {t}
            </h4>
          );
        }
        return (
          <p key={i} className="whitespace-pre-wrap">
            {line}
          </p>
        );
      })}
    </div>
  );
}

export default function ReportBuilder() {
  const [options, setOptions] = useState<ReportOptions | null>(null);
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState("CEO/임원 보고");
  const [depth, setDepth] = useState("표준");
  const [mode, setMode] = useState("빠른 작성");
  const [result, setResult] = useState<ReportResult | null>(null);
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [pdfBusy, setPdfBusy] = useState(false);
  const restored = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    reportApi.options().then(setOptions).catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    const s = load();
    if (s) {
      setTopic(s.topic);
      setStyle(s.style);
      setDepth(s.depth);
      setMode(s.mode);
      setResult(s.result);
    }
  }, []);

  useEffect(() => {
    if (!restored.current) return;
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ topic, style, depth, mode, result } satisfies Saved));
    } catch {}
  }, [topic, style, depth, mode, result]);

  useEffect(() => {
    if (!loading) return;
    const start = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(t);
  }, [loading]);

  async function generate() {
    if (!topic.trim()) return setError("보고할 내용을 입력해주세요.");
    setLoading(true);
    setError("");
    setSteps([]);
    setElapsed(0);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const r = await reportApi.generate({ topic, style, depth, mode }, (t) => setSteps((s) => [...s, t]), controller.signal);
      setResult(r);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message || "보고서 생성 중 오류가 발생했어요.");
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  async function downloadPdf() {
    if (!result) return;
    setPdfBusy(true);
    try {
      const blob = await reportApi.pdf(result.text, result.chart);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "executive_report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPdfBusy(false);
    }
  }

  async function copy() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }

  function reset() {
    abortRef.current?.abort();
    setTopic("");
    setResult(null);
    setSteps([]);
    setError("");
  }

  const styles = options?.styles ?? ["CEO/임원 보고"];

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
        <div className="text-[11px] font-bold tracking-[0.12em] text-accent">REPORT REQUEST</div>
        <h2 className="mt-1 text-lg font-extrabold tracking-tight">어떤 보고가 필요하신가요?</h2>
        <p className="mb-4 text-xs text-muted">메모 수준으로 적어도 됩니다. AI가 핵심 메시지와 논리구조를 다시 설계합니다.</p>

        <div className="space-y-4">
          <Field label="보고서 유형" hint={options?.style_help[style]}>
            <div className="flex flex-wrap gap-2">
              {styles.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStyle(s)}
                  aria-pressed={style === s}
                  className={`rounded-xl border px-3 py-2 text-sm font-bold transition ${
                    style === s ? "border-accent bg-accent text-white" : "border-border text-muted hover:border-accent/40 hover:text-fg"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="보고 깊이" hint={options?.depth_help[depth]}>
              <Segmented value={depth} options={options?.depths ?? ["핵심 중심", "표준", "상세"]} onChange={setDepth} full />
            </Field>
            <Field label="생성 모드" hint={mode === "빠른 작성" ? "외부 검색 없이 입력 내용 중심" : "필요할 때만 DART·법령·웹검색"}>
              <Segmented value={mode} options={options?.modes ?? ["빠른 작성", "최신자료 포함"]} onChange={setMode} full />
            </Field>
          </div>
          <Field label="보고할 내용">
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder={PLACEHOLDER}
              rows={7}
              className="w-full resize-y rounded-2xl border border-border bg-surface px-4 py-3 text-sm leading-relaxed outline-none placeholder:text-subtle focus:border-accent/60"
            />
          </Field>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={generate}
              disabled={loading || !topic.trim()}
              className="flex-1 rounded-xl bg-gradient-to-r from-accent to-violet-600 py-3 text-sm font-extrabold text-white shadow-sm transition hover:brightness-110 disabled:opacity-40"
            >
              ✨ 경영진 보고서 생성
            </button>
            <button type="button" onClick={reset} className="rounded-xl border border-border px-4 text-sm font-bold text-muted hover:text-fg">
              초기화
            </button>
          </div>
          {loading && (
            <div className="space-y-2 rounded-2xl bg-surface-muted px-4 py-3">
              <Spinner label={`${mode === "빠른 작성" ? "핵심 논리를 설계하고" : "자료를 확인하며 분석하고"} 있어요… ${elapsed}초`} />
              {steps.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {steps.map((s, i) => {
                    const arg = Object.values(s.input ?? {})[0];
                    return (
                      <span key={i} className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-accent">
                        ✓ {s.label}
                        {typeof arg === "string" && arg ? ` · ${arg.slice(0, 24)}` : ""}
                      </span>
                    );
                  })}
                </div>
              )}
              <p className="text-[11px] text-subtle">보고서 생성에는 보통 30초~1분 30초가 걸려요.</p>
            </div>
          )}
          {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}
        </div>
      </section>

      <div ref={resultRef} className="scroll-mt-4" />
      {result && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <div className="text-[11px] font-bold tracking-[0.12em] text-accent">GENERATED REPORT</div>
              <h2 className="text-lg font-extrabold tracking-tight">생성된 보고서</h2>
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={copy} className="rounded-xl border border-border px-3 py-2 text-sm font-bold hover:bg-surface-muted">
                {copied ? "복사됨 ✓" : "📋 복사"}
              </button>
              <button type="button" onClick={downloadPdf} disabled={pdfBusy} className="rounded-xl bg-accent px-3 py-2 text-sm font-bold text-white hover:brightness-110 disabled:opacity-50">
                {pdfBusy ? "PDF 만드는 중…" : "📥 PDF 다운로드"}
              </button>
            </div>
          </div>
          {result.chart && <DisclosureChart chart={result.chart} />}
          <article className="rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-8">
            <span className="inline-block rounded-full bg-accent-soft px-2.5 py-1 text-[10px] font-extrabold tracking-widest text-accent">EXECUTIVE REPORT</span>
            <div className="mt-4">
              <ReportBody text={result.text} />
            </div>
          </article>
        </section>
      )}
    </div>
  );
}
