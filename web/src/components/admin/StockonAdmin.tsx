"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { AdminLogin } from "@/components/admin/AdminConsole";
import LifeCuration from "@/components/admin/LifeCuration";
import { Spinner, inputClass } from "@/components/golf/ui";
import { setToken } from "@/lib/access";
import { dateLabel, eok, stockAdminApi, timeLabel, type AdminStatus } from "@/lib/stock";

const TASK_LABEL: Record<string, string> = { market: "시세·지수(공공데이터)", fx: "환율(수출입은행)", news: "카테고리 뉴스", watch: "관심 종목 뉴스·공시", briefing: "AI 브리핑", why: "왜 움직였나(미리 만들기)" };
const AI_LABEL = { briefing: "AI 브리핑", why: "왜 움직였나", news_summary: "뉴스 한 줄 요약" } as const;
const KEY_LABEL: Record<string, string> = { public_data: "공공데이터 PUBLIC_DATA_API_KEY", naver_search: "뉴스 NAVER_SEARCH_CLIENT_ID/SECRET", dart: "공시 DART_API_KEY", exim_fx: "환율 KOREAEXIM_API_KEY (선택)", ai: "AI ANTHROPIC_API_KEY" };
const ERROR_HELP: Record<string, string> = {
  not_registered: "공공데이터포털에서 주식시세·지수시세 활용신청이 필요하거나 승인 반영 전이에요.",
  no_such_service: "공공데이터 주소·기능 이름이 포털과 달라요(_V2 확인).",
  not_configured: "키가 설정되지 않았어요.",
  quota_exceeded: "오늘 호출 한도를 넘었어요.",
  news_not_configured: "뉴스 검색 키가 설정되지 않았어요.",
};

function Card({ title, desc, children, right }: { title: string; desc?: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-extrabold">{title}</h2>
          {desc && <p className="text-xs text-muted">{desc}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

/** 모의 키 만료 경고: D-7~D-1 주황, 만료 후 빨강. */
export function expiryNotice(daysLeft?: number | null): { level: "ok" | "warn" | "expired"; text: string } | null {
  if (daysLeft == null) return null;
  if (daysLeft < 0) return { level: "expired", text: `모의 키가 ${-daysLeft}일 전에 만료됐어요. 키움 포털에서 갱신하고 서버 .env.stockon을 고쳐 주세요.` };
  if (daysLeft <= 7) return { level: "warn", text: `모의 키 만료 D-${daysLeft}. 키움 포털에서 갱신하고 서버 .env.stockon의 키·만료일을 고쳐 주세요.` };
  return { level: "ok", text: `모의 키 만료까지 ${daysLeft}일` };
}

export default function StockonAdmin() {
  const { status: access, refresh: refreshAccess } = useAccess();
  const isAdmin = access?.me?.role === "admin";
  const [data, setData] = useState<AdminStatus | null>(null);
  const [error, setError] = useState("");
  const [watch, setWatch] = useState<{ code: string; name: string }[]>([]);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<{ code: string; name: string; market: string; cap: number | null }[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await stockAdminApi.status();
      setData(s);
      setWatch(s.watchlist);
      setError("");
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 401) setToken(null);
      else setError(err.message);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  useEffect(() => {
    if (!isAdmin || !q.trim()) return setHits([]);
    const t = setTimeout(() => stockAdminApi.search(q).then((r) => setHits(r.items)).catch(() => setHits([])), 250);
    return () => clearTimeout(t);
  }, [q, isAdmin]);

  if (!access) return <Spinner label="불러오는 중…" />;
  if (!isAdmin) return <AdminLogin onDone={refreshAccess} />;
  if (error) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>;
  if (!data) return <Spinner label="상태를 불러오는 중…" />;

  const dirty = JSON.stringify(watch.map((w) => w.code)) !== JSON.stringify(data.watchlist.map((w) => w.code));
  const move = (i: number, d: number) => setWatch((w) => { const n = [...w]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); return n; });
  const notice = expiryNotice(data.kiwoom.days_left);

  async function refresh(tasks: string[]) {
    setMsg("");
    try {
      const r = await stockAdminApi.refresh(tasks);
      setMsg(r.started ? "갱신을 시작했어요. 잠시 후 '상태 새로고침'을 눌러 보세요." : "이미 갱신 중이에요.");
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  async function save() {
    setBusy(true);
    try {
      await stockAdminApi.saveWatchlist(watch.map((w) => w.code));
      setMsg("팀 관심 종목을 저장했어요. 뉴스·공시를 새로 모으는 중이에요.");
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5 pb-10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-accent">ADMIN · STOCK:ON</div>
          <h1 className="text-2xl font-extrabold tracking-tight">STOCK:ON 관리</h1>
          <p className="text-xs text-muted">기준일 {dateLabel(data.as_of) || "—"} · {data.enabled ? "켜짐" : "꺼짐(STOCKON_ENABLED 없음)"}{data.refreshing ? " · 갱신 중" : ""}</p>
        </div>
        <div className="flex gap-2">
          <Link href="/admin" className="rounded-xl border border-border px-3 py-2 text-sm font-bold">관리자 설정</Link>
          <Link href="/stock" className="rounded-xl bg-[#13315C] px-3 py-2 text-sm font-bold text-white">STOCK:ON 보기</Link>
        </div>
      </div>

      {notice && notice.level !== "ok" && (
        <p role="alert" className={`rounded-2xl px-4 py-3 text-sm font-bold ${notice.level === "expired" ? "bg-red-500/15 text-red-700 dark:text-red-300" : "bg-amber-500/15 text-amber-800 dark:text-amber-300"}`}>⚠ {notice.text}</p>
      )}

      <Card title="뉴스 속 숨은 종목 · 시연 안전장치" desc="첫 화면 이슈 카드를 숨기거나 순서를 정해요. 저장한 설정은 수집기가 이슈를 다시 만들어도 남아요.">
        <LifeCuration />
      </Card>

      <Card title="수집 상태" desc="사용자 요청은 저장된 자료만 읽어요. 외부 호출은 아래 작업이 주기적으로만 해요." right={<button type="button" onClick={load} className="rounded-xl border border-border px-3 py-1.5 text-xs font-bold">상태 새로고침</button>}>
        <ul className="divide-y divide-border text-sm">
          {Object.entries(data.tasks).map(([t, s]) => (
            <li key={t} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="font-bold">{TASK_LABEL[t] ?? t}</span>
              <span className="text-xs text-muted">
                성공 {timeLabel(s.ok_ts)}
                {s.error && <span className="ml-2 font-bold text-red-600 dark:text-red-400">오류 {timeLabel(s.error_ts)} · {ERROR_HELP[s.error] ?? s.error}</span>}
              </span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => refresh(["market", "fx", "news", "watch", "briefing", "why"])} className="rounded-xl bg-accent px-3 py-2 text-xs font-extrabold text-white">전체 지금 갱신</button>
          <button type="button" onClick={() => refresh(["briefing"])} className="rounded-xl border border-border px-3 py-2 text-xs font-bold">AI 브리핑만 다시 만들기</button>
          {msg && <span className="self-center text-xs text-muted">{msg}</span>}
        </div>
        <p className="text-xs text-muted">&lsquo;왜 움직였나&rsquo; 미리 만든 설명 {data.why_today.count}건 / 최대 {data.why_today.limit}건 (기준일 {dateLabel(data.why_today.as_of) || "—"}) · 방문자 클릭은 저장된 설명만 읽어요</p>
      </Card>

      <Card title="AI 상태" desc="AI 호출이 실패하면 브리핑은 숫자로 만든 고정 문장, 뉴스는 요약 없이 제목·링크, '왜 움직였나'는 뉴스·공시 링크만 보여요.">
        <ul className="divide-y divide-border">
          {(Object.keys(AI_LABEL) as (keyof typeof AI_LABEL)[]).map((k) => {
            const s = data.ai[k];
            const failing = !!s.error_ts && (!s.ok_ts || s.error_ts > s.ok_ts);
            return (
              <li key={k} className="space-y-1 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-bold">{AI_LABEL[k]} <span className="text-xs font-normal text-subtle">{data.models[k]}</span></span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-extrabold ${failing ? "bg-red-500/15 text-red-700 dark:text-red-300" : s.ok_ts ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" : "bg-surface-muted text-muted"}`}>
                    {failing ? `실패 중 · 연속 ${s.consecutive}회` : s.ok_ts ? "정상" : "기록 없음"}
                  </span>
                </div>
                <p className="text-xs text-muted">
                  마지막 성공 {timeLabel(s.ok_ts)} · 오늘 실패 <b className={s.fails_today ? "text-red-600 dark:text-red-400" : ""}>{s.fails_today}</b>회 · 오늘 고정 문장 대체 <b>{s.fallbacks_today}</b>회 · 누적 실패 {s.fails_total}회
                </p>
                {s.last_error && (
                  <p className={`text-xs ${failing ? "font-bold text-red-600 dark:text-red-400" : "text-subtle"}`}>마지막 오류 {timeLabel(s.error_ts)} · {s.last_error}</p>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card title="연결된 키" desc="값은 표시하지 않고 설정 여부만 보여요.">
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {Object.entries(data.configured).map(([k, ok]) => (
            <li key={k} className="flex items-center gap-2"><span>{ok ? "✅" : "⬜"}</span><span className={ok ? "" : "text-muted"}>{KEY_LABEL[k] ?? k}</span></li>
          ))}
        </ul>
      </Card>

      <Card title="팀 관심 종목" desc={`최대 30개. 화면의 '팀 관심 종목'에 순서대로 보여요. (${watch.length}/30)`}>
        <div className="relative">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="종목명 또는 코드로 검색 (예: 삼성전자, 005930)" className={inputClass} aria-label="종목 검색" />
          {hits.length > 0 && (
            <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-2xl border border-border bg-surface p-1 shadow-lg">
              {hits.map((h) => {
                const added = watch.some((w) => w.code === h.code);
                return (
                  <li key={h.code}>
                    <button type="button" disabled={added || watch.length >= 30} onClick={() => { setWatch((w) => [...w, { code: h.code, name: h.name }]); setQ(""); }}
                      className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm hover:bg-surface-muted disabled:opacity-40">
                      <span><b>{h.name}</b> <span className="text-xs text-subtle">{h.code} · {h.market}</span></span>
                      <span className="text-xs text-muted">{added ? "추가됨" : `시총 ${eok(h.cap)}`}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {!data.as_of && <p className="text-xs text-amber-700 dark:text-amber-300">종목 목록은 시세를 한 번 받아 온 뒤에 검색돼요.</p>}
        {watch.length === 0 ? (
          <p className="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-muted">아직 지정한 종목이 없어요.</p>
        ) : (
          <ol className="space-y-1.5">
            {watch.map((w, i) => (
              <li key={w.code} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm">
                <span className="w-5 text-xs font-bold text-subtle">{i + 1}</span>
                <span className="flex-1 font-bold">{w.name} <span className="text-xs font-normal text-subtle">{w.code}</span></span>
                <button type="button" aria-label={`${w.name} 위로`} disabled={i === 0} onClick={() => move(i, -1)} className="px-2 text-muted disabled:opacity-30">▲</button>
                <button type="button" aria-label={`${w.name} 아래로`} disabled={i === watch.length - 1} onClick={() => move(i, 1)} className="px-2 text-muted disabled:opacity-30">▼</button>
                <button type="button" aria-label={`${w.name} 빼기`} onClick={() => setWatch((x) => x.filter((y) => y.code !== w.code))} className="px-2 text-red-600">✕</button>
              </li>
            ))}
          </ol>
        )}
        <div className="flex justify-end gap-2">
          {dirty && <button type="button" onClick={() => setWatch(data.watchlist)} className="rounded-xl px-3 py-2 text-sm font-bold text-muted">되돌리기</button>}
          <button type="button" onClick={save} disabled={!dirty || busy} className="rounded-xl bg-accent px-5 py-2.5 text-sm font-extrabold text-white disabled:opacity-40">{busy ? "저장 중…" : "관심 종목 저장"}</button>
        </div>
      </Card>

      <Card title="키움증권 연동 (2단계)" desc="키움 키는 수집기 전용 파일(.env.stockon)에만 있고 이 화면·앱에는 오지 않아요. 여기에는 날짜·상태만 보여요.">
        {data.kiwoom.connected ? (
          <ul className="space-y-1 text-sm">
            <li>모드 <b>{data.kiwoom.mode === "real" ? "실전" : "모의"}</b> · 설정 <b>{data.kiwoom.price_source === "kiwoom" ? "키움" : "공공데이터"}</b> · 지금 화면 <b>{data.kiwoom.showing === "kiwoom" ? "키움 시세" : "공공데이터(전일)"}</b>{data.kiwoom.session && ` · 장 상태 ${data.kiwoom.session}`}</li>
            {data.kiwoom.price_source === "kiwoom" && data.kiwoom.showing !== "kiwoom" && (
              <li className="text-xs font-bold text-amber-700 dark:text-amber-300">설정은 키움이지만 새 키움 스냅샷이 없어 공공데이터로 보이고 있어요(장 시간 외, 수집 실패 또는 10분 이상 갱신 없음).</li>
            )}
            {data.kiwoom.last_error && <li className="text-xs font-bold text-red-600 dark:text-red-400">마지막 오류 · {data.kiwoom.last_error}</li>}
            <li>모의 키 만료일 <b>{data.kiwoom.mock_key_expires ?? "미입력"}</b>{notice && <span className={`ml-2 text-xs font-bold ${notice.level === "ok" ? "text-muted" : notice.level === "warn" ? "text-amber-700 dark:text-amber-300" : "text-red-600"}`}>{notice.text}</span>}</li>
            <li className="text-xs text-muted">마지막 성공 {data.kiwoom.last_ok ?? "—"} · 연속 실패 {data.kiwoom.fails ?? 0}회</li>
          </ul>
        ) : (
          <p className="rounded-2xl bg-surface-muted px-4 py-4 text-sm text-muted">아직 연결 전이에요. 2단계에서 수집기를 켜면 모드·모의 키 만료일(D-7부터 경고)이 여기에 보여요.</p>
        )}
      </Card>
    </div>
  );
}
