"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ACCESS_EVENT, accessApi, getToken, serviceForPath, setToken, type AccessStatus } from "@/lib/access";
import { SITE_NAME } from "@/lib/site";

type Ctx = { status: AccessStatus | null; refresh: () => void; logout: () => void };
const AccessContext = createContext<Ctx>({ status: null, refresh: () => {}, logout: () => {} });
export const useAccess = () => useContext(AccessContext);

function CodeForm({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <form
      className="space-y-2"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          const r = await accessApi.login(code.trim());
          setToken(r.token);
          onDone();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <input
        value={code}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
        placeholder="접속 코드 · 예: ABCD-2345"
        autoComplete="one-time-code"
        className="w-full rounded-xl border border-border bg-surface px-3 py-3 text-center font-mono text-base tracking-widest outline-none focus:border-accent/60"
        aria-label="접속 코드"
      />
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <button type="submit" disabled={busy || code.trim().length < 4} className="w-full rounded-xl bg-accent py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40">
        {busy ? "확인 중…" : "입장하기"}
      </button>
    </form>
  );
}

function Gate({ status, reason, onDone }: { status: AccessStatus; reason: "login" | "closed" | "hidden"; onDone: () => void }) {
  const openServices = Object.entries(status.services).filter(([, v]) => v.allowed && v.visible);
  const titles: Record<string, string> = {
    golf: "⛳ TEE:PICK",
    dreamcar: "🚙 내차에서 드림카까지",
    realestate: "🏠 ZIP:ON",
    report: "📄 보고서 작성기",
    saju: "🔮 AI 사주 · 대운 분석",
    "car-selector": "🚗 차량 선택기",
    gif: "🎞️ GIF 변환기",
  };
  const pages: Record<string, string> = { "car-selector": "/car-selector" };
  return (
    <main className="mx-auto flex min-h-[70dvh] max-w-md flex-col justify-center px-4 py-12">
      <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-slate-900 to-blue-700 text-2xl text-white shadow-lg">✦</div>
      <div className="text-center">
        <div className="text-[11px] font-extrabold tracking-[0.16em] text-accent">DIGITAL STRATEGY · AI LAB</div>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight">{SITE_NAME}</h1>
      </div>
      <div className="mt-6 space-y-4 rounded-3xl border border-border bg-surface p-6 shadow-sm">
        {reason === "closed" && (
          <p className="text-center text-sm leading-relaxed text-muted">
            지금은 점검 중이에요.
            <br />
            잠시 후 다시 방문해 주세요.
          </p>
        )}
        {reason === "hidden" && <p className="text-center text-sm leading-relaxed text-muted">현재 공개되지 않은 서비스예요.</p>}
        {reason === "login" && (
          <>
            <p className="text-center text-sm leading-relaxed text-muted">
              등록된 분만 이용할 수 있어요.
              <br />
              관리자에게 받은 <b className="text-fg">개인 접속 코드</b>를 입력해 주세요.
            </p>
            <CodeForm onDone={onDone} />
          </>
        )}
        {reason !== "closed" && (
          <Link href="/" className="block text-center text-sm font-semibold text-muted hover:text-fg">
            ← 처음 화면으로
          </Link>
        )}
      </div>
      {reason !== "closed" && openServices.length > 0 && (
        <div className="mt-5 text-center">
          <div className="text-xs font-bold text-subtle">누구나 이용할 수 있는 서비스</div>
          <div className="mt-2 flex flex-wrap justify-center gap-2">
            {openServices
              .filter(([id]) => titles[id])
              .map(([id]) => (
                <Link key={id} href={pages[id] ?? `/${id}`} className="rounded-xl border border-border bg-surface px-3 py-2 text-sm font-semibold hover:border-accent/40">
                  {titles[id]}
                </Link>
              ))}
          </div>
        </div>
      )}
    </main>
  );
}

export default function AccessProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [status, setStatus] = useState<AccessStatus | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(() => {
    accessApi
      .status()
      .then((s) => {
        // 토큰이 만료·무효인데 남아 있으면 정리
        if (!s.me && getToken()) setToken(null);
        setStatus(s);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(ACCESS_EVENT, refresh);
    return () => window.removeEventListener(ACCESS_EVENT, refresh);
  }, [refresh]);

  const logout = useCallback(() => setToken(null), []);
  const ctx = { status, refresh, logout };

  // 관리자 페이지는 자체 로그인을 쓴다
  if (pathname.startsWith("/admin")) return <AccessContext.Provider value={ctx}>{children}</AccessContext.Provider>;

  // 백엔드에 닿지 않으면 각 화면이 자체 오류를 보여주도록 그대로 렌더링
  if (!status) {
    if (failed) return <AccessContext.Provider value={ctx}>{children}</AccessContext.Provider>;
    return (
      <div className="flex min-h-[60dvh] items-center justify-center" role="status">
        <span className="size-6 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
      </div>
    );
  }

  const sid = serviceForPath(pathname);
  let reason: "login" | "closed" | "hidden" | null = null;
  if (status.site_mode === "closed" && status.me?.role !== "admin") reason = "closed";
  else if (sid) {
    const s = status.services[sid];
    if (s && !s.allowed) reason = s.level === "hidden" ? "hidden" : s.level === "admin" ? "closed" : "login";
  } else if (!status.site_allowed) reason = "login";

  return (
    <AccessContext.Provider value={ctx}>
      {status.notice && (
        <div className="bg-accent px-4 py-2 text-center text-[13px] font-semibold text-white" role="status">
          📢 {status.notice.text}
        </div>
      )}
      {reason ? <Gate status={status} reason={reason} onDone={refresh} /> : children}
    </AccessContext.Provider>
  );
}
