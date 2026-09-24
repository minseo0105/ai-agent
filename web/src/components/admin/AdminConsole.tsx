"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { Spinner, inputClass } from "@/components/golf/ui";
import { adminApi, setToken, type AdminSettings, type Member, type ServiceMode, type SiteMode } from "@/lib/access";
import { SITE_NAME } from "@/lib/site";

const SITE_MODES: { value: SiteMode; icon: string; title: string; desc: string }[] = [
  { value: "public", icon: "🌐", title: "모두 공개", desc: "주소를 아는 누구나 이용할 수 있어요." },
  { value: "members", icon: "🔐", title: "등록된 사람만", desc: "관리자가 발급한 개인 접속 코드로 입장해요." },
  { value: "closed", icon: "🛠", title: "점검 중", desc: "관리자만 볼 수 있고, 방문자에게는 점검 안내가 보여요." },
];
const SITE_LABEL: Record<SiteMode, string> = { public: "모두 공개", members: "등록된 사람만", closed: "점검 중" };
const SERVICE_MODES: { value: ServiceMode; label: string }[] = [
  { value: "inherit", label: "사이트 설정 따름" },
  { value: "public", label: "모두 공개" },
  { value: "members", label: "등록된 사람만" },
  { value: "hidden", label: "숨김" },
];
const TOKEN_DAYS = [1, 7, 30, 90];

const fmt = (ts: number | null) => (ts ? new Date(ts * 1000).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" }) : "—");

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

function AdminLogin({ onDone }: { onDone: () => void }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    adminApi
      .info()
      .then((r) => setConfigured(r.configured))
      .catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
  }, []);

  return (
    <div className="mx-auto max-w-sm space-y-4 rounded-3xl border border-border bg-surface p-6 shadow-sm">
      <div className="text-center">
        <div className="text-3xl">🛠</div>
        <h1 className="mt-1 text-xl font-extrabold">관리자 로그인</h1>
        <p className="text-xs text-muted">{SITE_NAME} 공개 범위와 구성원을 관리합니다.</p>
      </div>
      {configured === false ? (
        <div className="space-y-2 rounded-2xl bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-300">
          <p className="font-bold">관리자 비밀번호가 아직 설정되지 않았어요.</p>
          <p className="text-xs leading-relaxed">
            <code className="rounded bg-black/5 px-1">.streamlit/secrets.toml</code> 파일에 아래 한 줄을 직접 추가하고 FastAPI 서버를 다시 시작해 주세요. (배포 환경에서는 같은 이름의 환경변수)
          </p>
          <pre className="overflow-x-auto rounded-lg bg-black/80 px-3 py-2 text-xs text-white">ADMIN_PASSWORD = &quot;원하는 비밀번호&quot;</pre>
        </div>
      ) : (
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const r = await adminApi.login(password);
              setToken(r.token);
              setPassword("");
              onDone();
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="관리자 비밀번호" autoComplete="current-password" className={inputClass} aria-label="관리자 비밀번호" />
          <button type="submit" disabled={busy || !password || configured === null} className="w-full rounded-xl bg-accent py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40">
            {busy ? "확인 중…" : "로그인"}
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

function IssuedCode({ name, code, onClose }: { name: string; code: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-3 rounded-2xl border-2 border-accent/40 bg-accent-soft p-4" role="alert">
      <div className="text-sm font-bold">
        {name}님의 접속 코드가 발급됐어요. <span className="text-red-600 dark:text-red-400">이 화면을 닫으면 다시 볼 수 없어요.</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded-xl bg-surface px-4 py-2 font-mono text-2xl font-extrabold tracking-[0.2em]">{code}</code>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(code);
              setCopied(true);
            } catch {}
          }}
          className="rounded-xl border border-border bg-surface px-3 py-2 text-sm font-bold hover:border-accent/50"
        >
          {copied ? "✓ 복사됨" : "복사"}
        </button>
        <button type="button" onClick={onClose} className="rounded-xl px-3 py-2 text-sm font-bold text-muted hover:text-fg">
          전달했어요 · 닫기
        </button>
      </div>
      <p className="text-[11px] text-muted">이 코드를 본인에게만 전달해 주세요. 잃어버리면 &apos;코드 재발급&apos;으로 새 코드를 만들 수 있어요(이전 코드와 로그인은 바로 끊겨요).</p>
    </div>
  );
}

function MemberRow({ m, onChange, onIssued }: { m: Member; onChange: () => void; onIssued: (name: string, code: string) => void }) {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      onChange();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border px-4 py-3 ${m.active ? "" : "opacity-60"}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-bold">{m.name}</span>
          {!m.active && <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-bold text-muted">사용 중지</span>}
        </div>
        <div className="text-[11px] text-subtle">
          {m.note && <>{m.note} · </>}코드 ····{m.code_hint} · 최근 입장 {fmt(m.last_login_at)}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button type="button" disabled={busy} onClick={() => run(() => adminApi.updateMember(m.id, { active: !m.active }))} className="rounded-lg border border-border px-2.5 py-1.5 text-xs font-bold hover:border-accent/50 disabled:opacity-50">
          {m.active ? "사용 중지" : "다시 허용"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (!confirm(`${m.name}님의 코드를 재발급할까요? 이전 코드와 현재 로그인은 바로 끊겨요.`)) return;
            run(async () => {
              const r = await adminApi.reissue(m.id);
              onIssued(r.member.name, r.code);
            });
          }}
          className="rounded-lg border border-border px-2.5 py-1.5 text-xs font-bold hover:border-accent/50 disabled:opacity-50"
        >
          코드 재발급
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            if (confirm(`${m.name}님을 목록에서 삭제할까요? 되돌릴 수 없어요.`)) run(() => adminApi.removeMember(m.id));
          }}
          className="rounded-lg border border-red-500/30 px-2.5 py-1.5 text-xs font-bold text-red-600 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
        >
          삭제
        </button>
      </div>
    </li>
  );
}

export default function AdminConsole() {
  const { status, refresh: refreshAccess } = useAccess();
  const [data, setData] = useState<AdminSettings | null>(null);
  const [draft, setDraft] = useState<Pick<AdminSettings, "site_mode" | "notice" | "services" | "member_token_days"> | null>(null);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState("");
  const [issued, setIssued] = useState<{ name: string; code: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [newNote, setNewNote] = useState("");
  const [adding, setAdding] = useState(false);
  const isAdmin = status?.me?.role === "admin";

  const load = useCallback(async (resetDraft: boolean) => {
    try {
      const s = await adminApi.settings();
      setData(s);
      if (resetDraft) setDraft({ site_mode: s.site_mode, notice: s.notice, services: s.services, member_token_days: s.member_token_days });
      setLoadError("");
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 401) setToken(null);
      else setLoadError(err.message);
    }
  }, []);

  useEffect(() => {
    if (isAdmin) load(true);
  }, [isAdmin, load]);

  const dirty = useMemo(() => {
    if (!data || !draft) return false;
    return JSON.stringify({ a: draft.site_mode, b: draft.notice, c: draft.services, d: draft.member_token_days }) !== JSON.stringify({ a: data.site_mode, b: data.notice, c: data.services, d: data.member_token_days });
  }, [data, draft]);

  if (!status) return <Spinner label="불러오는 중…" />;
  if (!isAdmin) return <AdminLogin onDone={refreshAccess} />;
  if (loadError) return <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{loadError}</p>;
  if (!data || !draft) return <Spinner label="설정을 불러오는 중…" />;

  async function save() {
    if (!draft) return;
    setSaving(true);
    setSaved("");
    try {
      const s = await adminApi.save(draft);
      setData(s);
      setDraft({ site_mode: s.site_mode, notice: s.notice, services: s.services, member_token_days: s.member_token_days });
      setSaved("저장했어요. 방문자 화면에 바로 적용됩니다.");
      refreshAccess();
    } catch (e) {
      setSaved("");
      alert((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const activeCount = data.members.filter((m) => m.active).length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-accent">ADMIN SETTINGS</div>
          <h1 className="text-2xl font-extrabold tracking-tight">관리자 설정</h1>
          <p className="text-xs text-muted">마지막 저장 {fmt(data.updated_at || null)}</p>
        </div>
        <div className="flex gap-2">
          <Link href="/" className="rounded-xl border border-border px-3 py-2 text-sm font-bold hover:bg-surface-muted">
            사이트 보기
          </Link>
          <button type="button" onClick={() => setToken(null)} className="rounded-xl border border-border px-3 py-2 text-sm font-bold text-muted hover:text-fg">
            로그아웃
          </button>
        </div>
      </div>

      <Card title="사이트 공개 범위" desc="사이트 전체의 기본 공개 범위예요. 서비스별로 따로 정할 수도 있어요.">
        <div className="grid gap-2 sm:grid-cols-3">
          {SITE_MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              aria-pressed={draft.site_mode === m.value}
              onClick={() => setDraft((d) => (d ? { ...d, site_mode: m.value } : d))}
              className={`rounded-2xl border p-4 text-left transition ${draft.site_mode === m.value ? "border-accent bg-accent-soft ring-2 ring-accent/20" : "border-border hover:border-accent/40"}`}
            >
              <div className="text-xl">{m.icon}</div>
              <div className="mt-1 font-extrabold">{m.title}</div>
              <div className="text-xs text-muted">{m.desc}</div>
            </button>
          ))}
        </div>
        {draft.site_mode === "members" && activeCount === 0 && (
          <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">아직 등록된 사람이 없어요. 아래 &apos;구성원 관리&apos;에서 먼저 추가해 주세요.</p>
        )}
      </Card>

      <Card title="서비스별 공개" desc="'사이트 설정 따름'이면 위의 공개 범위를 그대로 따라요. 숨김은 홈에서 사라지고 관리자만 들어갈 수 있어요.">
        {draft.site_mode === "closed" && <p className="rounded-xl bg-surface-muted px-3 py-2 text-xs text-muted">점검 중에는 서비스별 설정과 관계없이 관리자만 이용할 수 있어요.</p>}
        <ul className="divide-y divide-border">
          {data.catalog.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <span className="text-sm font-bold">
                {c.icon} {c.title}
              </span>
              <select
                value={draft.services[c.id] ?? "inherit"}
                onChange={(e) => setDraft((d) => (d ? { ...d, services: { ...d.services, [c.id]: e.target.value as ServiceMode } } : d))}
                className="rounded-xl border border-border bg-surface px-3 py-2 text-sm"
                aria-label={`${c.title} 공개 범위`}
              >
                {SERVICE_MODES.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.value === "inherit" ? `${m.label} (${SITE_LABEL[draft.site_mode]})` : m.label}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="공지 배너" desc="켜 두면 모든 페이지 맨 위에 공지가 보여요.">
        <label className="flex items-center gap-2 text-sm font-bold">
          <input type="checkbox" checked={draft.notice.enabled} onChange={(e) => setDraft((d) => (d ? { ...d, notice: { ...d.notice, enabled: e.target.checked } } : d))} className="size-4 accent-[var(--accent)]" />
          공지 배너 보이기
        </label>
        <input
          value={draft.notice.text}
          maxLength={300}
          onChange={(e) => setDraft((d) => (d ? { ...d, notice: { ...d.notice, text: e.target.value } } : d))}
          placeholder="예: 10월 5일 18시~20시 서버 점검이 있어요."
          className={inputClass}
          aria-label="공지 내용"
        />
      </Card>

      <Card title="로그인 유지 기간" desc="접속 코드로 입장한 뒤 다시 코드를 묻기까지의 기간이에요.">
        <div className="flex flex-wrap gap-2">
          {TOKEN_DAYS.map((days) => (
            <button
              key={days}
              type="button"
              aria-pressed={draft.member_token_days === days}
              onClick={() => setDraft((d) => (d ? { ...d, member_token_days: days } : d))}
              className={`rounded-xl border px-4 py-2 text-sm font-bold ${draft.member_token_days === days ? "border-accent bg-accent text-white" : "border-border hover:border-accent/40"}`}
            >
              {days}일
            </button>
          ))}
        </div>
      </Card>

      <div className="sticky bottom-3 z-10 flex flex-wrap items-center justify-end gap-3 rounded-2xl border border-border bg-surface/95 p-3 shadow-lg backdrop-blur">
        {saved && !dirty && <span className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">✓ {saved}</span>}
        {dirty && <span className="text-sm text-muted">저장하지 않은 변경이 있어요</span>}
        {dirty && (
          <button type="button" onClick={() => setDraft({ site_mode: data.site_mode, notice: data.notice, services: data.services, member_token_days: data.member_token_days })} className="rounded-xl px-3 py-2 text-sm font-bold text-muted hover:text-fg">
            되돌리기
          </button>
        )}
        <button type="button" onClick={save} disabled={!dirty || saving} className="rounded-xl bg-accent px-5 py-2.5 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40">
          {saving ? "저장 중…" : "설정 저장"}
        </button>
      </div>

      <Card title="구성원 관리" desc="'등록된 사람만'으로 설정한 곳에 들어갈 수 있는 사람이에요. 추가하면 개인 접속 코드가 발급돼요." right={<span className="text-xs font-bold text-muted">허용 {activeCount}명 / 전체 {data.members.length}명</span>}>
        <form
          className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]"
          onSubmit={async (e) => {
            e.preventDefault();
            setAdding(true);
            try {
              const r = await adminApi.addMember(newName, newNote);
              setIssued({ name: r.member.name, code: r.code });
              setNewName("");
              setNewNote("");
              await load(false);
            } catch (err) {
              alert((err as Error).message);
            } finally {
              setAdding(false);
            }
          }}
        >
          <input value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={40} placeholder="이름" className={inputClass} aria-label="이름" />
          <input value={newNote} onChange={(e) => setNewNote(e.target.value)} maxLength={100} placeholder="메모 (소속 등, 선택)" className={inputClass} aria-label="메모" />
          <button type="submit" disabled={adding || !newName.trim()} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-extrabold text-white disabled:opacity-40">
            + 추가
          </button>
        </form>
        {issued && <IssuedCode name={issued.name} code={issued.code} onClose={() => setIssued(null)} />}
        {data.members.length === 0 ? (
          <p className="rounded-2xl bg-surface-muted px-4 py-6 text-center text-sm text-muted">아직 등록된 사람이 없어요.</p>
        ) : (
          <ul className="space-y-2">
            {data.members.map((m) => (
              <MemberRow key={m.id} m={m} onChange={() => load(false)} onIssued={(name, code) => setIssued({ name, code })} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
