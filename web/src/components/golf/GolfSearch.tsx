"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  DEFAULT_PARAMS,
  golfApi,
  loadState,
  saveState,
  type ConditionParams,
  type GolfOptions,
  type LastSearch,
  type ResultCard,
  type SearchMode,
  type SearchResult,
  type Sort,
} from "@/lib/golf";
import { ChoiceChips, Field, Segmented, Spinner, Tag, inputClass } from "./ui";

const MODES = [
  { value: "condition" as const, label: "조건 검색" },
  { value: "text" as const, label: "✨ AI 문장검색" },
  { value: "name" as const, label: "직접 찾기" },
];
type Filter = "전체" | "조건확인" | "확인필요";

function Card({ card, highlight }: { card: ResultCard; highlight?: boolean }) {
  return (
    <Link
      href={`/golf/${encodeURIComponent(card.id)}`}
      className={`group block rounded-2xl border bg-surface p-4 transition hover:-translate-y-0.5 hover:shadow-md ${
        highlight ? "border-golf/30" : "border-border"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={`text-[11px] font-bold ${card.status === "confirmed" ? "text-golf" : "text-amber-600 dark:text-amber-400"}`}>
            {card.badge}
          </div>
          <div className="mt-0.5 truncate text-base font-extrabold tracking-tight">{card.name}</div>
          <div className="text-xs text-muted">{card.location}</div>
        </div>
        <span className="mt-1 shrink-0 text-sm font-bold text-golf transition group-hover:translate-x-0.5">상세 →</span>
      </div>
      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {card.facts.map((f) => (
          <Tag key={f}>{f}</Tag>
        ))}
        {card.badges.map((b) => (
          <Tag key={b} tone="golf">
            {b}
          </Tag>
        ))}
      </div>
      {card.reasons.length > 0 && (
        <div className="mt-2.5 rounded-lg bg-surface-muted px-3 py-2 text-xs text-muted">
          <b className="text-fg">추천 근거</b> · {card.reasons.join(" · ")}
        </div>
      )}
      <div className="mt-2 text-[11px] text-subtle">{card.evidence}</div>
    </Link>
  );
}

export default function GolfSearch() {
  const [options, setOptions] = useState<GolfOptions | null>(null);
  const [mode, setMode] = useState<SearchMode>("condition");
  const [params, setParams] = useState<ConditionParams>(DEFAULT_PARAMS);
  const [text, setText] = useState("");
  const [nameQuery, setNameQuery] = useState("");
  const [nameResults, setNameResults] = useState<{ id: string; name: string; region: string; city: string }[] | null>(null);
  const [sort, setSort] = useState<Sort>("추천순");
  const [filter, setFilter] = useState<Filter>("전체");
  const [visible, setVisible] = useState(6);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [last, setLast] = useState<LastSearch | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const restored = useRef(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  // 최초 진입: 옵션 로드 + 이전 검색 상태 복원
  useEffect(() => {
    if (restored.current) return; // StrictMode 재실행 시 방금 저장된 초기값으로 덮어쓰지 않도록
    golfApi.options().then(setOptions).catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    const s = loadState();
    if (s) {
      setMode(s.mode);
      setParams(s.params);
      setText(s.text);
      setNameQuery(s.nameQuery);
      setSort(s.sort);
      setFilter(s.filter);
      setVisible(s.visible);
      setResult(s.result);
      setLast(s.last);
    }
    restored.current = true;
  }, []);

  useEffect(() => {
    if (restored.current) saveState({ mode, params, text, nameQuery, sort, filter, visible, result, last });
  }, [mode, params, text, nameQuery, sort, filter, visible, result, last]);

  // 직접 찾기: 입력 멈춘 뒤 검색
  useEffect(() => {
    if (mode !== "name") return;
    const q = nameQuery.trim();
    if (!q) {
      setNameResults(null);
      return;
    }
    const t = setTimeout(() => {
      golfApi.find(q).then((r) => setNameResults(r.items)).catch(() => setNameResults([]));
    }, 250);
    return () => clearTimeout(t);
  }, [nameQuery, mode]);

  function changeMode(m: SearchMode) {
    if (m === mode) return;
    setMode(m);
    setResult(null);
    setLast(null);
    setError("");
  }

  async function run(search: LastSearch, nextSort: Sort, scroll = true) {
    setLoading(true);
    setError("");
    try {
      const r =
        search.mode === "text"
          ? await golfApi.searchText(search.text, nextSort, search.includeUnknown)
          : await golfApi.search(search.params, nextSort);
      setResult(r);
      setLast(search);
      setSort(nextSort);
      if (scroll) {
        setFilter("전체");
        setVisible(6);
        requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
      }
    } catch (e) {
      setError((e as Error).message || "검색 중 오류가 발생했어요.");
    } finally {
      setLoading(false);
    }
  }

  // 예산·캐디·3인·야간 조건에서 정보가 없는 골프장을 포함/제외 전환
  function toggleUnknown(include: boolean) {
    if (!last) return;
    if (last.mode === "text") {
      run({ ...last, includeUnknown: include }, sort, false);
    } else {
      const nextParams = { ...last.params, include_unknown: include };
      setParams((p) => ({ ...p, include_unknown: include }));
      run({ mode: "condition", params: nextParams }, sort, false);
    }
  }

  const set = <K extends keyof ConditionParams>(k: K, v: ConditionParams[K]) => setParams((p) => ({ ...p, [k]: v }));
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const singleArea = params.areas.length === 1 ? params.areas[0] : null;

  const items = result?.items ?? [];
  const top = (result?.top_ids ?? []).map((id) => items.find((x) => x.id === id)).filter(Boolean) as ResultCard[];
  const filtered = filter === "조건확인" ? items.filter((x) => x.status === "confirmed") : filter === "확인필요" ? items.filter((x) => x.status !== "confirmed") : items;
  const shown = filtered.slice(0, Math.max(6, visible));
  const trace = result?.trace;

  return (
    <div className="space-y-5">
      <div className="rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
        <Segmented value={mode} options={MODES} onChange={changeMode} full ariaLabel="찾는 방법" />

        {options && !options.runtime_ok && (
          <p className="mt-3 rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            Master 검증정보 일부를 읽지 못해 catalog 기준으로 표시합니다.
          </p>
        )}

        {mode === "condition" && (
          <form
            className="mt-5 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              run({ mode: "condition", params }, "추천순");
            }}
          >
            <p className="text-xs text-subtle">필수는 시간대 하나만 · 선택조건은 전체로 두어도 검색됩니다.</p>
            <Field label="지역" hint="복수 선택 · 미선택 시 전체 권역">
              <ChoiceChips
                options={options?.areas ?? []}
                labels={options?.counts.by_area}
                selected={params.areas}
                onToggle={(v) => setParams((p) => ({ ...p, areas: toggle(p.areas, v), subregions: [] }))}
              />
            </Field>
            {singleArea && (
              <Field label="세부지역" hint="선택">
                <ChoiceChips
                  options={options?.subregions[singleArea] ?? []}
                  selected={params.subregions}
                  onToggle={(v) => set("subregions", toggle(params.subregions, v))}
                />
              </Field>
            )}
            <Field label="출발지" hint="선택 · 주소 또는 역·건물명">
              <input
                className={inputClass}
                value={params.departure}
                onChange={(e) => set("departure", e.target.value)}
                placeholder="예: 잠실역, 강동구청, 서울 송파구 올림픽로 240"
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="라운드 요일">
                <Segmented value={params.day} options={["주중", "주말"] as const} onChange={(v) => set("day", v)} full />
              </Field>
              <Field label="희망 시간대" hint="필수">
                <Segmented value={params.session} options={["1부", "2부", "3부"] as const} onChange={(v) => set("session", v)} full />
              </Field>
              <Field label="그린피" hint="선택">
                <select className={inputClass} value={params.budget} onChange={(e) => set("budget", e.target.value)}>
                  {(options?.budgets ?? ["전체"]).map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </select>
              </Field>
              <Field label="캐디" hint="선택">
                <Segmented value={params.caddie} options={["전체", "캐디", "노캐디"] as const} onChange={(v) => set("caddie", v)} full />
              </Field>
            </div>

            <details open={showDetail} onToggle={(e) => setShowDetail((e.target as HTMLDetailsElement).open)} className="group rounded-2xl border border-border px-4 py-3">
              <summary className="cursor-pointer list-none text-sm font-bold text-muted">
                <span className="inline-block transition group-open:rotate-45">＋</span> 상세조건 · 인원 / 야간 / 난이도
              </summary>
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="인원" hint="선택">
                    <Segmented value={params.players} options={["전체", "3인", "4인"] as const} onChange={(v) => set("players", v)} full />
                  </Field>
                  <Field
                    label="야간 라운드"
                    hint={options && options.data_coverage.night === 0 ? "데이터 준비 중" : options ? `확인 ${options.data_coverage.night}곳` : undefined}
                  >
                    <label
                      className={`flex h-[42px] items-center gap-2.5 text-sm ${
                        options && options.data_coverage.night === 0 ? "cursor-not-allowed opacity-50" : "cursor-pointer"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--golf)]"
                        checked={params.night}
                        disabled={!!options && options.data_coverage.night === 0}
                        onChange={(e) => set("night", e.target.checked)}
                      />
                      야간 라운드만 보기
                    </label>
                  </Field>
                  <Field label="내 평균타수" hint="선택">
                    <select className={inputClass} value={params.avg_score_label} onChange={(e) => set("avg_score_label", e.target.value)}>
                      {(options?.avg_scores ?? ["미선택"]).map((s) => (
                        <option key={s}>{s}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="난이도" hint="선택">
                    <Segmented value={params.challenge} options={["편하게", "적당히", "도전"] as const} onChange={(v) => set("challenge", v)} full />
                  </Field>
                </div>
              </div>
            </details>

            <button type="submit" disabled={loading} className="w-full rounded-xl bg-golf py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-50">
              🔎 골프장 찾기
            </button>
          </form>
        )}

        {mode === "text" && (
          <form
            className="mt-5 space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) run({ mode: "text", text: text.trim() }, "추천순");
            }}
          >
            <textarea
              className={`${inputClass} min-h-24 resize-y`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="예: 여주에서 주말 4인, 1인 30만원 이하 골프장 찾아줘"
            />
            <p className="text-xs text-subtle">
              문장에서 지역 · 주중/주말 · 인원 · 예산을 읽습니다. 미확인 3인·요금 정보는 제외하지 않고 결과에서 확인 필요로 구분합니다.
            </p>
            <button type="submit" disabled={loading || !text.trim()} className="w-full rounded-xl bg-golf py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40">
              문장으로 검색
            </button>
            {result?.parsed && (
              <div className="flex flex-wrap items-center gap-1.5 rounded-xl bg-golf-soft px-3 py-2.5 text-xs">
                <b className="text-golf">AI 해석 조건</b>
                {[
                  result.parsed.area,
                  result.parsed.city,
                  result.parsed.day,
                  result.parsed.session,
                  result.parsed.players,
                  result.parsed.budget,
                  result.parsed.caddie,
                  result.parsed.night,
                ]
                  .filter(Boolean)
                  .map((x, i) => (
                  <Tag key={i}>{x}</Tag>
                ))}
              </div>
            )}
          </form>
        )}

        {mode === "name" && (
          <div className="mt-5 space-y-3">
            <input
              className={inputClass}
              value={nameQuery}
              onChange={(e) => setNameQuery(e.target.value)}
              placeholder="골프장 이름이나 지역 · 예: 레이크사이드, 용인, 제주"
              autoFocus
            />
            {nameResults && nameResults.length === 0 && <p className="text-sm text-muted">현재 Pool에서 일치하는 골프장을 찾지 못했습니다.</p>}
            {nameResults && nameResults.length > 0 && (
              <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
                {nameResults.map((c) => (
                  <li key={c.id}>
                    <Link href={`/golf/${encodeURIComponent(c.id)}`} className="flex items-center justify-between gap-3 px-4 py-3 transition hover:bg-surface-muted">
                      <span className="font-bold">{c.name}</span>
                      <span className="shrink-0 text-xs text-muted">
                        {[c.region, c.city].filter(Boolean).join(" ")}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {error && <p className="mt-4 rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}
      </div>

      <div ref={resultsRef} className="scroll-mt-4" />
      {loading && !result && <Spinner label="조건에 맞는 골프장을 찾고 있어요…" />}

      {result && mode !== "name" && (
        <section className={`space-y-5 transition ${loading ? "opacity-50" : ""}`} aria-busy={loading}>
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-bold text-golf">검색 적용</span>
              {result.applied.map((c, i) => (
                <Tag key={i} tone="golf">
                  {c}
                </Tag>
              ))}
            </div>
            {result.departure_status && <p className="text-xs text-muted">{result.departure_status}</p>}
          </div>

          {!!trace?.unknown_excluded && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm">
              <span className="text-amber-800 dark:text-amber-300">
                정보 미확인으로 {trace.unknown_excluded}곳 제외
                {trace.unknown_reasons &&
                  ` (${Object.entries(trace.unknown_reasons)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(" · ")})`}
              </span>
              <button type="button" onClick={() => toggleUnknown(true)} className="rounded-lg bg-surface px-3 py-1.5 text-xs font-bold text-fg shadow-sm">
                미확인 포함해서 보기
              </button>
            </div>
          )}
          {!!trace?.unknown_included && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-surface-muted px-4 py-3 text-sm">
              <span className="text-muted">정보 미확인 {trace.unknown_included}곳을 ‘확인 필요’로 포함해서 보여주고 있어요.</span>
              <button type="button" onClick={() => toggleUnknown(false)} className="rounded-lg bg-surface px-3 py-1.5 text-xs font-bold text-fg shadow-sm">
                확인된 곳만 보기
              </button>
            </div>
          )}

          {items.length === 0 ? (
            <p className="rounded-2xl bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
              선택한 조건이 확인된 골프장이 없습니다.
              {trace?.unknown_excluded ? " 위의 ‘미확인 포함해서 보기’로 정보가 아직 없는 곳까지 볼 수 있어요." : " 지역이나 예산 조건을 넓혀 다시 검색해 보세요."}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <h2 className="text-lg font-extrabold tracking-tight">검색 결과</h2>
                  {trace && (
                    <details className="text-xs text-muted">
                      <summary className="cursor-pointer">
                        검색결과 {trace.final ?? 0}개
                        {"confirmed" in trace && ` · 조건확인 ${trace.confirmed}개 · 확인필요 ${trace.pending}개`}
                      </summary>
                      <p className="mt-1">
                        전체 Pool {trace.total}개 → 권역 {trace.area}개 → 세부지역 {trace.subregion}개 → 검색결과 {trace.final}개
                      </p>
                      {"confirmed" in trace && (
                        <p>
                          조건 확인 {trace.confirmed}개 · 정보 확인 필요 {trace.pending}개 (조건부 {trace.conditional}개) · 불일치 제외 {trace.excluded}개
                        </p>
                      )}
                      <p>명확한 불가만 제외하고 미확인 정보는 ‘확인 필요’로 남깁니다.</p>
                    </details>
                  )}
                </div>
                <Segmented
                  value={sort}
                  options={["추천순", "가까운순", "가격순"] as const}
                  onChange={(s) => last && run(last, s, false)}
                  ariaLabel="정렬"
                />
              </div>
              {result.notice && <p className="text-xs text-muted">{result.notice}</p>}

              {top.length > 0 && (
                <div className="space-y-2.5">
                  <h3 className="text-sm font-extrabold">🏆 조건에 잘 맞는 추천 TOP</h3>
                  <div className="grid gap-3 md:grid-cols-2">
                    {top.map((c) => (
                      <Card key={c.id} card={c} highlight />
                    ))}
                  </div>
                </div>
              )}

              <div className="space-y-2.5 border-t border-border pt-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-extrabold">전체 검색결과 {items.length}개</h3>
                  <Segmented
                    value={filter}
                    options={["전체", "조건확인", "확인필요"] as const}
                    onChange={(f) => {
                      setFilter(f);
                      setVisible(6);
                    }}
                    ariaLabel="결과 보기"
                  />
                </div>
                <p className="text-xs text-subtle">
                  {filter} {filtered.length}개 중 {shown.length}개 표시 · 미확인 정보는 숨기지 않고 표시합니다.
                  {result.has_departure && " 가까운순은 차량 경로 거리·시간을 우선 표시하고, 미조회 결과는 직선거리로 보조 표시합니다."}
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  {shown.map((c) => (
                    <Card key={c.id} card={c} />
                  ))}
                </div>
                {shown.length < filtered.length && (
                  <button
                    type="button"
                    onClick={() => setVisible(shown.length + 6)}
                    className="w-full rounded-xl border border-border bg-surface py-2.5 text-sm font-bold text-muted transition hover:text-fg"
                  >
                    6개 더보기 · 남은 {filtered.length - shown.length}개
                  </button>
                )}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
