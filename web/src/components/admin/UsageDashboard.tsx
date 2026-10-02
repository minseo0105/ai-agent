"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { AdminLogin } from "./AdminConsole";
import { setToken } from "@/lib/access";
import { getUsageSummary, type UsageDay, type UsagePeriod, type UsageService, type UsageSummary } from "@/lib/usageDashboard";

const number = (value: number) => value.toLocaleString("ko-KR");
const time = (value: string) => new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
}).format(new Date(value));
const button = "min-h-11 rounded-xl px-4 py-2 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";
const panel = "rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6";
const rateDefinition = "기능 사용률 = 해당 서비스를 방문한 세션 중 핵심 기능을 1회 이상 실행한 세션 비율";

function Value({ value, unit = "회" }: { value: number | null; unit?: string }) {
  return value === null ? <span className="text-xs font-medium text-muted">집계 준비 중</span> : <span className="tabular-nums">{number(value)}<span className="ml-1 text-xs font-medium text-muted">{unit}</span></span>;
}

function Metrics({ service }: { service: UsageService }) {
  const rows: [string, number | null, string?][] = [
    ["방문 세션", service.visits, "세션"], ["페이지 조회", service.page_views],
    [service.feature_label, service.features],
    ...(service.service === "realestate" ? [["지도에서 사업 확인", service.map_clicks], ["개발사업 상세 확인", service.project_clicks], ["네이버부동산 이동", service.naver]] as [string, number | null][] : []),
    ["오류", service.errors],
  ];
  return <dl className="grid grid-cols-2 gap-x-5 gap-y-3 text-sm">{rows.map(([label, value, unit]) =>
    <div key={label} className="min-w-0"><dt className="text-xs text-muted">{label}</dt><dd className="mt-0.5 font-extrabold"><Value value={value} unit={unit} /></dd></div>,
  )}</dl>;
}

function Flow({ service }: { service: UsageService }) {
  const zipon = service.service === "realestate";
  const steps: [string, number | null, string][] = [
    [`${zipon ? "ZIP:ON" : "Golf"} 진입`, service.visits, "세션"],
    [service.feature_label, service.features, "회"],
    ...(zipon ? [["지도에서 개발사업 확인", service.map_clicks, "회"], ["개발사업 상세 확인", service.project_clicks, "회"], ["네이버부동산 이동", service.naver, "회"]] as [string, number | null, string][] : []),
  ];
  const labels = zipon ? ["진입 세션", "검색한 세션", "사업을 본 세션", "네이버부동산 이동 세션"] : ["진입 세션", "검색한 세션"];
  return <section className={panel} aria-label={`${zipon ? "ZIP:ON" : "Golf"} 이용 흐름`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-lg font-extrabold">{zipon ? "ZIP:ON" : "Golf"} 이용 흐름</h2>
      <span className={`rounded-full px-3 py-1 text-xs font-bold ${zipon ? "bg-estate-soft text-estate" : "bg-golf-soft text-golf"}`}>기능 사용률 {service.feature_rate === null ? "—" : `${service.feature_rate}%`}</span>
    </div>
    <p className="mt-2 text-sm text-muted">방문 {number(service.visits)}세션 중 <b className="text-fg">{number(service.used_sessions ?? 0)}세션</b>이 {service.feature_label}을 실행했어요.</p>
    <p className="mt-1 text-[11px] leading-relaxed text-muted">{rateDefinition}</p>
    <h3 className="mb-3 mt-6 text-xs font-bold text-muted">이용 흐름별 실행 횟수</h3>
    <ol className="space-y-2">{steps.map(([label, count, unit], index) => <li key={label}>
      {index > 0 && <div className="mb-2 pl-4 text-subtle" aria-hidden>↓</div>}
      <div className="flex min-h-14 items-center justify-between gap-3 rounded-2xl bg-surface-muted px-4 py-3">
        <span className="text-sm font-semibold">{label}</span><strong className="shrink-0 text-lg"><Value value={count} unit={unit} /></strong>
      </div>
    </li>)}</ol>
    <p className="mt-3 text-xs leading-relaxed text-muted">진입은 방문 세션, 나머지는 각각의 실행 횟수예요. 같은 세션의 반복 실행을 포함하므로 아래 단계에서 숫자가 늘어날 수 있어요.</p>
    <p className="mt-2 text-xs leading-relaxed text-muted">{zipon ? "부동산 검색은 사업명·주소 필터 적용과 실거래·청약 조회 기준입니다. 지역 선택만 바꾸는 동작은 별도 집계하지 않아요. 개발사업 상세 확인은 사업카드 선택 기준입니다." : "정렬 변경으로 다시 실행한 검색도 포함합니다. 출발지와 정렬 방식별 사용 정보는 수집하지 않습니다."}</p>
    <details className="mt-5 border-t border-border pt-4">
      <summary className="min-h-11 cursor-pointer text-sm font-bold">세션별 진행 단계 보기</summary>
      <p className="mb-4 text-xs leading-relaxed text-muted">선택 기간 안에서 진입 → 검색{zipon ? " → 지도 또는 사업 상세 → 네이버부동산 이동" : ""} 순서로 기록된 세션이에요. 단계마다 같은 세션은 한 번만 셉니다. 기록이 누락되면 적게 집계될 수 있어요.</p>
      <ol className="space-y-3">{(service.session_funnel ?? []).map((count, index) => <li key={labels[index]}>
        <div className="mb-1 flex justify-between gap-2 text-xs"><span>{labels[index]}</span><b>{number(count)} 세션</b></div>
        <div className="h-2 overflow-hidden rounded-full bg-surface-muted"><div className={`h-full rounded-full ${zipon ? "bg-estate" : "bg-golf"}`} style={{ width: `${service.visits ? count / service.visits * 100 : 0}%` }} /></div>
      </li>)}</ol>
    </details>
  </section>;
}

function Trend({ days }: { days: UsageDay[] }) {
  const [service, setService] = useState("all");
  const rows = days.filter((row) => row.service === service);
  const series = [{ key: "visits", label: "방문 세션", color: "#2563eb" }, { key: "page_views", label: "페이지 조회", color: "#7c3aed" }, { key: "features", label: "기능 실행", color: "#059669" }] as const;
  const max = Math.max(1, ...rows.flatMap((row) => series.map((s) => row[s.key])));
  const x = (i: number) => 35 + i / Math.max(1, rows.length - 1) * 520;
  return <section className={panel} aria-label="일별 이용 추이">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-extrabold">일별 이용 추이</h2>
      <div className="flex rounded-xl bg-surface-muted p-1" aria-label="추이 서비스 선택">{[["all", "전체"], ["realestate", "ZIP:ON"], ["golf", "Golf"]].map(([id, label]) =>
        <button key={id} type="button" className={`${button} px-3 ${service === id ? "bg-surface text-fg shadow-sm" : "text-muted"}`} aria-pressed={service === id} onClick={() => setService(id)}>{label}</button>)}</div>
    </div>
    <ul className="mt-5 flex flex-wrap gap-4 text-xs text-muted">{series.map((s) => <li key={s.key} className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: s.color }} />{s.label}</li>)}</ul>
    <svg viewBox="0 0 580 215" className="mt-3 w-full" role="img" aria-label="날짜별 방문 세션, 페이지 조회, 기능 실행. 정확한 수치는 아래 일별 수치에서 확인하세요.">
      {[0, 0.5, 1].map((v) => <g key={v}><line x1="35" x2="555" y1={175 - v * 145} y2={175 - v * 145} stroke="var(--border)" /><text x="28" y={179 - v * 145} textAnchor="end" fontSize="10" fill="var(--text-muted)">{Math.ceil(v * max)}</text></g>)}
      {series.map((s) => <polyline key={s.key} points={rows.map((row, i) => `${x(i)},${175 - row[s.key] / max * 145}`).join(" ")} fill="none" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />)}
      {[0, Math.floor((rows.length - 1) / 2), rows.length - 1].map((i) => <text key={i} x={x(i)} y="202" textAnchor="middle" fontSize="11" fill="var(--text-muted)">{rows[i]?.day.slice(5).replace("-", "/")}</text>)}
    </svg>
    <p className="text-xs leading-relaxed text-muted">한국 시간 기준입니다. 같은 세션이 여러 날짜에 방문하면 일별로 각각 집계되므로 기간 방문 세션은 일별 합계와 다를 수 있어요.</p>
    <details className="mt-4"><summary className="min-h-11 cursor-pointer text-sm font-bold">일별 수치 보기</summary><table className="w-full table-fixed text-right text-xs"><caption className="sr-only">선택 서비스의 일별 이용현황</caption><thead><tr className="border-b border-border text-muted"><th className="py-2 text-left">날짜</th><th>방문 세션</th><th>페이지 조회</th><th>기능 실행</th></tr></thead><tbody>{rows.map((row) => <tr key={row.day} className="border-b border-border"><th className="py-2 text-left font-medium">{row.day.slice(5)}</th><td>{number(row.visits)}</td><td>{number(row.page_views)}</td><td>{number(row.features)}</td></tr>)}</tbody></table></details>
  </section>;
}

export default function UsageDashboard() {
  const { status, refresh } = useAccess();
  const isAdmin = status?.me?.role === "admin";
  const [period, setPeriod] = useState<UsagePeriod>("today");
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!isAdmin) { setData(null); return; }
    const controller = new AbortController();
    setBusy(true); setError(""); setData(null);
    getUsageSummary(period, controller.signal).then((result) => {
      if (!controller.signal.aborted) setData(result);
    }).catch((failure: Error & { status?: number }) => {
      if (controller.signal.aborted) return;
      if (failure.status === 401) setToken(null);
      setError(failure.name === "ConnectionError" ? "운영현황 서버에 연결하지 못했어요. 잠시 후 다시 확인해 주세요." : failure.message);
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, [isAdmin, period, revision]);

  if (!status) return <div className={panel} role="status">관리자 권한을 확인하고 있어요.<button type="button" className={`${button} ml-2 text-accent`} onClick={refresh}>다시 확인</button></div>;
  if (!isAdmin) return <AdminLogin onDone={refresh} />;
  const kpis = [["방문 세션", "visits", "세션"], ["페이지 조회", "page_views", "회"], ["기능 실행", "features", "회"], ["외부 이동", "external", "회"], ["오류", "errors", "건"]] as const;
  return <div className="space-y-5 pb-8">
    <header>
      <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-[11px] font-extrabold tracking-[0.16em] text-accent">AI LAB · ADMIN</p><h1 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">AI LAB 운영현황</h1></div><Link href="/admin" className={`${button} border border-border text-muted`}>관리자 설정</Link></div>
      <p className="mt-2 text-sm text-muted">어디에 방문하고, 어떤 기능을 이용했는지 살펴보세요.</p>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3"><div className="inline-flex rounded-2xl border border-border bg-surface p-1" aria-label="조회 기간">{([["today", "오늘"], ["7d", "7일"], ["30d", "30일"]] as const).map(([id, label]) => <button key={id} type="button" aria-pressed={period === id} onClick={() => setPeriod(id)} className={`${button} ${period === id ? "bg-fg text-bg" : "text-muted hover:bg-surface-muted"}`}>{label}</button>)}</div><button type="button" className={`${button} text-accent disabled:opacity-40`} disabled={busy} onClick={() => setRevision((v) => v + 1)}>새로고침</button></div>
      <p className="mt-2 text-xs text-muted">Asia/Seoul · 오늘을 포함한 기간{data ? ` · 집계 ${time(data.end_at)}` : ""} · 최대 30초 간격 갱신</p>
    </header>
    {busy && <div className={`${panel} animate-pulse text-sm text-muted`} role="status">운영현황을 불러오고 있어요…</div>}
    {error && <div className={`${panel} border-amber-500/30`} role="alert"><p className="font-bold">{error}</p><p className="mt-2 text-sm text-muted">집계 오류를 0건으로 표시하지 않습니다. 서비스 이용에는 영향을 주지 않아요.</p></div>}
    {data && <>
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-5" aria-label="기간 요약">{kpis.map(([label, key, unit]) => <div key={key} className="rounded-2xl border border-border bg-surface p-4"><div className="text-xs font-bold text-muted">{label}</div><div className={`mt-2 text-2xl font-extrabold ${key === "errors" && data.totals.errors ? "text-estate" : "text-fg"}`}><Value value={data.totals[key]} unit={unit} /></div></div>)}</section>
      <p className="text-xs leading-relaxed text-muted">방문 세션은 페이지에 진입한 익명 브라우저 세션입니다. 사람 수와 다릅니다. 기능 실행은 현재 수집 중인 ZIP:ON·Golf의 검색 실행만, 외부 이동은 ZIP:ON의 네이버부동산·공식 자료 링크만 집계합니다.</p>
      {Object.values(data.totals).every((count) => count === 0) && <p className="rounded-2xl bg-accent-soft p-4 text-sm text-accent" role="status">선택한 기간에 수집된 활동이 없습니다.</p>}
      <section className={panel} aria-label="어떤 서비스를 이용했나요?">
        <h2 className="text-lg font-extrabold">어떤 서비스를 이용했나요?</h2><p className="mt-1 text-xs text-muted">서비스별 이용현황 · 페이지를 누르면 상세 지표가 펼쳐집니다.</p>
        <div className="mt-5 grid grid-cols-[minmax(0,1fr)_3.5rem_3.5rem_3.5rem] gap-1 border-b border-border pb-2 text-right text-[10px] font-bold text-muted sm:grid-cols-[minmax(0,1fr)_5rem_5rem_5rem]"><span className="text-left">서비스 / 페이지</span><span>방문 세션</span><span>페이지 조회</span><span>기능 실행</span></div>
        {data.pages.map((page) => <details key={page.route} className="border-b border-border last:border-0">
          <summary className="grid min-h-16 cursor-pointer list-none grid-cols-[minmax(0,1fr)_3.5rem_3.5rem_3.5rem] items-center gap-1 py-3 text-right text-sm marker:hidden sm:grid-cols-[minmax(0,1fr)_5rem_5rem_5rem]"><span className="min-w-0 break-words pr-1 text-left text-xs font-bold sm:text-sm">{page.label}<span className="ml-1 text-subtle" aria-hidden>⌄</span></span><span className="tabular-nums">{number(page.visits)}</span><span className="tabular-nums">{number(page.page_views)}</span><span className="tabular-nums">{page.features === null ? <span className="text-[10px] text-muted" aria-label="집계 준비 중">준비 중</span> : number(page.features)}</span></summary>
          <div className="mb-4 rounded-2xl bg-surface-muted p-4"><p className="mb-3 text-xs font-bold text-muted">{data.services.find((s) => s.service === page.service)?.label ?? page.label} 서비스 전체 지표</p>{data.services.find((s) => s.service === page.service) && <Metrics service={data.services.find((s) => s.service === page.service)!} />}</div>
        </details>)}
        <p className="mt-4 text-xs leading-relaxed text-muted">0회는 수집 중인 이벤트가 없는 경우, ‘준비 중’은 아직 수집하지 않는 기능입니다. 같은 세션의 재방문은 페이지 조회만 늘어납니다. 미등록 경로는 기존 수집 기준에 따라 /other로 합산됩니다.</p>
      </section>
      {data.services.filter((s) => s.service === "realestate" || s.service === "golf").sort((a) => a.service === "realestate" ? -1 : 1).map((service) => <Flow key={service.service} service={service} />)}
      {period !== "today" && <Trend days={data.daily} />}
      <section className={panel} aria-label="최근 활동"><h2 className="text-lg font-extrabold">최근 활동</h2><p className="mt-1 text-xs text-muted">선택한 기간의 최근 기록 · 최대 20건 · 한국 시간</p>{data.recent.length === 0 ? <p className="mt-5 text-sm text-muted">아직 수집된 활동이 없어요.</p> : <ol className="mt-4 divide-y divide-border">{data.recent.map((activity, index) => <li key={`${activity.at}-${index}`} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 py-3 text-sm"><time dateTime={activity.at} className="text-xs tabular-nums text-muted">{time(activity.at)}</time><span className="text-xs font-bold text-accent">{activity.service_label}</span><span>{activity.label}</span></li>)}</ol>}</section>
      <p className="text-xs leading-relaxed text-muted">이벤트는 비동기로 수집되어 누락될 수 있습니다. 검색어·주소·세션 ID는 표시하지 않습니다. 최근 활동과 집계는 조회 전용입니다.</p>
    </>}
  </div>;
}
