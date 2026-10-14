"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { AdminLogin } from "./AdminConsole";
import { API_URL, apiFetch, setToken } from "@/lib/access";

type Run = { run_id: string; started_at: string; finished_at: string | null; status: string; new_count: number; changed_count: number; unchanged_count: number; validation_failed_count: number; sources: { source: string; status: string; source_complete: boolean }[] };
type Summary = { total: number; locations: number; boundaries: number; pending: number; new_30d: number; changed_30d: number; auto_applied_30d: number; last_success: string | null; last_attempt: string | null; source_date: string | null; runs: Run[]; recent_projects: { project_id: string; project_name: string; created_at: string }[]; recent_changes: { update_id: string; project_name: string; update_kind: string; recorded_at: string }[] };
const panel = "rounded-2xl border border-border bg-surface p-5";
const when = (value: string | null) => value ? new Date(value).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "확인된 기록 없음";
const state: Record<string, string> = { SUCCEEDED: "성공", PARTIAL: "부분 성공", FAILED: "실패", RUNNING: "실행 중", ABORTED: "중단" };

export default function ZiponData() {
  const { status, refresh } = useAccess();
  const isAdmin = status?.me?.role === "admin";
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!isAdmin) { setData(null); return; }
    const controller = new AbortController();
    setError("");
    apiFetch(`${API_URL}/api/admin/zipon-data`, { signal: controller.signal, cache: "no-store", timeoutMs: 8000 })
      .then(async (r) => {
        if (!r.ok) {
          if (r.status === 401) setToken(null);
          throw new Error(r.status === 401 ? "관리자 로그인이 필요해요." : "조회할 수 없습니다. ZIP 연결 설정과 운영현황 SQL을 확인해 주세요.");
        }
        return r.json() as Promise<Summary>;
      }).then((d) => { if (!controller.signal.aborted) setData(d); })
      .catch((e: Error) => { if (!controller.signal.aborted) { setData(null); setError(e.message); } });
    return () => controller.abort();
  }, [isAdmin, revision]);
  useEffect(() => {
    if (!isAdmin) return;
    const timer = setInterval(() => { if (!document.hidden) setRevision((v) => v + 1); }, 60000);
    return () => clearInterval(timer);
  }, [isAdmin]);
  if (!status) return <p role="status">관리자 권한을 확인하고 있어요.</p>;
  if (!isAdmin) return <AdminLogin onDone={refresh} />;
  const delayed = data && (!data.last_success || Date.now() - Date.parse(data.last_success) > 8 * 86400000);
  return <div className="space-y-5 pb-10">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-xs font-bold text-estate">ZIP:ON · ADMIN</p><h1 className="mt-1 text-2xl font-extrabold">개발정보 최신화 현황</h1></div><Link href="/admin" className="text-sm text-accent">관리자 설정</Link></header>
    <p className="text-sm text-muted">공식 원천 수집과 반영 상태 · 한국 시간 · 조회 전용</p>
    <button className="min-h-11 rounded-xl border border-border px-4" onClick={() => setRevision((v) => v + 1)}>새로고침</button>
    {error && <p className={panel} role="alert">{error} 오류를 0건으로 표시하지 않습니다.</p>}
    {!data && !error && <p role="status">운영현황을 불러오고 있어요.</p>}
    {data && <>
      {delayed && <p className={`${panel} text-estate`} role="alert">완전 성공 기록이 없거나 8일 이상 지연됐습니다. 원천별 결과와 GitHub Actions 실행 기록을 확인해 주세요.</p>}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">{[["전체 사업", data.total], ["대표 좌표", data.locations], ["공식 경계", data.boundaries], ["검토 대기", data.pending], ["30일 신규", data.new_30d], ["30일 변경 사업", data.changed_30d], ["30일 자동 반영", data.auto_applied_30d]].map(([label, count]) => <div key={label} className={panel}><p className="text-xs text-muted">{label}</p><strong className="mt-2 block text-2xl">{count}</strong></div>)}</section>
      <section className={panel}><h2 className="font-bold">최신성</h2><p className="mt-3">마지막 완전 성공: {when(data.last_success)}</p><p>마지막 시도: {when(data.last_attempt)}</p><p>저장된 원천 기준일 최댓값: {data.source_date ?? "미확인"}</p><p className="mt-2 text-xs text-muted">수집 시각은 원천 기준일과 다릅니다. 변경 없음은 정상 수집 결과이며 부분 성공을 완전 성공으로 세지 않습니다.</p></section>
      <section className={panel}><h2 className="font-bold">최근 실행과 원천별 결과</h2><ol className="mt-4 divide-y divide-border">{data.runs.map((r) => <li key={r.run_id} className="py-4"><p className="font-bold">{when(r.started_at)} · {state[r.status] ?? "미확인"}</p><p className="text-sm text-muted">신규 {r.new_count} · 변경 {r.changed_count} · 변경 없음 {r.unchanged_count} · 오류 {r.validation_failed_count}</p><ul className="mt-2 text-xs text-muted">{r.sources.map((s, i) => <li key={`${s.source}-${i}`}>{s.source}: {state[s.status] ?? "미확인"} {s.source_complete ? "· 완전수집" : "· 완전수집 미확인"}</li>)}</ul></li>)}</ol>{data.runs.length === 0 && <p className="mt-3 text-muted">자동 수집 실행 기록이 없습니다.</p>}</section>
      <section className={panel}><h2 className="font-bold">최근 신규 사업</h2><ul className="mt-3 space-y-2">{data.recent_projects.map((p) => <li key={p.project_id}>{p.project_name} <time className="text-xs text-muted">{when(p.created_at)}</time></li>)}</ul></section>
      <section className={panel}><h2 className="font-bold">최근 반영 이력</h2><ul className="mt-3 space-y-2">{data.recent_changes.map((p) => <li key={p.update_id}>{p.project_name} <time className="text-xs text-muted">{when(p.recorded_at)}</time></li>)}</ul></section>
      <p className="text-xs text-muted">검토 대기 후보는 자동 삭제하지 않습니다. 현재 화면에는 승인·DB 변경 기능이 없습니다.</p>
    </>}
  </div>;
}
