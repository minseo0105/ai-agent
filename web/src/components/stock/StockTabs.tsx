"use client";

// STOCK:ON 화면 탭: 오늘 시장(기존 화면 그대로) · 생활 속 종목 찾기.
// 시장 탭은 숨겨도 계속 붙어 있어서(1분 갱신·고른 종목 유지) 돌아왔을 때 처음부터 다시 그리지 않는다.
// 생활 속 종목 찾기는 처음 열 때만 코드를 받는다(시장 탭만 보는 사람의 첫 화면을 무겁게 하지 않음).
// 바로 열기: /stock?tab=life
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import StockOn from "@/components/stock/StockOn";

const LifeFinder = dynamic(() => import("@/components/stock/LifeFinder"), {
  ssr: false,
  loading: () => <div className="rounded-3xl bg-[#071226] py-24 text-center text-sm text-slate-300">마인드맵을 불러오는 중…</div>,
});

type Tab = "market" | "life";
const TABS: [Tab, string][] = [["market", "📊 오늘 시장"], ["life", "🧭 생활 속 종목 찾기"]];

export default function StockTabs() {
  const [tab, setTab] = useState<Tab>("market");
  const [lifeOpened, setLifeOpened] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") === "life") {
      setTab("life");
      setLifeOpened(true);
    }
  }, []);

  function choose(t: Tab) {
    setTab(t);
    if (t === "life") setLifeOpened(true);
    const url = new URL(window.location.href);
    if (t === "life") url.searchParams.set("tab", "life");
    else url.searchParams.delete("tab");
    window.history.replaceState(null, "", url);
  }

  return (
    <>
      <div role="tablist" aria-label="STOCK:ON 화면" className="mb-3 grid grid-cols-2 gap-1 rounded-2xl bg-surface-muted p-1">
        {TABS.map(([t, label]) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => choose(t)}
            className={`rounded-xl px-3 py-2.5 text-sm font-extrabold transition ${tab === t
              ? t === "life" ? "bg-[#0a1a38] text-white shadow-[0_0_18px_rgba(56,189,248,.35)]" : "bg-surface text-fg shadow-sm"
              : "text-muted hover:text-fg"}`}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" hidden={tab !== "market"}><StockOn /></div>
      {lifeOpened && <div role="tabpanel" hidden={tab !== "life"}><LifeFinder /></div>}
    </>
  );
}
