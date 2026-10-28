"use client";

// STOCK:ON 화면 탭: 뉴스 속 숨은 종목(기본·첫 탭) · 오늘 시장(기존 화면 그대로).
// /stock → 뉴스 속 숨은 종목, /stock?tab=market → 오늘 시장. 예전 주소 /stock?tab=life도 뉴스 속 숨은 종목.
// 오늘 시장은 처음 열 때 붙이고(1분 갱신), 한 번 연 뒤에는 숨겨도 붙어 있어 돌아왔을 때 처음부터 다시 그리지 않는다.
import { useEffect, useState } from "react";
import LifeFinder from "@/components/stock/LifeFinder";
import StockOn from "@/components/stock/StockOn";

type Tab = "news" | "market";
const TABS: [Tab, string][] = [["news", "📰 뉴스 속 숨은 종목"], ["market", "📊 오늘 시장"]];

export default function StockTabs() {
  const [tab, setTab] = useState<Tab>("news");
  const [marketOpened, setMarketOpened] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") === "market") {
      setTab("market");
      setMarketOpened(true);
    }
  }, []);

  function choose(t: Tab) {
    setTab(t);
    if (t === "market") setMarketOpened(true);
    const url = new URL(window.location.href);
    if (t === "market") url.searchParams.set("tab", "market");
    else url.searchParams.delete("tab");
    window.history.replaceState(null, "", url);
  }

  return (
    <>
      <div role="tablist" aria-label="STOCK:ON 화면" className="grid grid-cols-2 gap-1 rounded-2xl bg-surface-muted p-1">
        {TABS.map(([t, label]) => (
          <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => choose(t)}
            className={`rounded-xl px-3 py-2.5 text-[15px] font-extrabold transition ${tab === t
              ? t === "news" ? "bg-[#0a1a38] text-white shadow-[0_0_18px_rgba(56,189,248,.35)]" : "bg-surface text-fg shadow-sm"
              : "text-muted hover:text-fg"}`}>
            {label}
          </button>
        ))}
      </div>
      <p className="mb-3 mt-2 text-center text-[14px] font-semibold text-muted">
        {tab === "news" ? "뉴스 한 줄에 연결된 회사들, AI가 찾아드려요" : "지수 · 히트맵 · 등락 상위 · 팀 관심 종목 · 뉴스 · 일정"}
      </p>
      <div role="tabpanel" hidden={tab !== "news"}><LifeFinder /></div>
      {marketOpened && <div role="tabpanel" hidden={tab !== "market"}><StockOn /></div>}
    </>
  );
}
