"use client";

import { useEffect, useState } from "react";
import { useAccess } from "@/components/access/AccessProvider";
import { serviceLink } from "@/lib/services";
import AgentSection from "./AgentSection";
import ServiceArtwork from "./home/ServiceArtwork";
import { AGENT, CATALOG, CATEGORIES, type Category, type CatalogItem } from "./home/catalog";
import styles from "./home/Home.module.css";

function Arrow() {
  return <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export default function ServiceGrid() {
  const { status } = useAccess();
  const [category, setCategory] = useState<Category>("전체");
  const [agentOpen, setAgentOpen] = useState(false);
  useEffect(() => {
    const openAgent = () => { setAgentOpen(true); setCategory(current => current === "전체" ? current : "AI Agent"); };
    const openFromHash = () => { if (window.location.hash === "#agent") openAgent(); };
    const openFromLink = (event: MouseEvent) => { if (event.target instanceof Element && event.target.closest('a[href="#agent"]')) openAgent(); };
    openFromHash();
    window.addEventListener("hashchange", openFromHash);
    document.addEventListener("click", openFromLink);
    return () => { window.removeEventListener("hashchange", openFromHash); document.removeEventListener("click", openFromLink); };
  }, []);
  const visible = [...CATALOG, AGENT].filter(item => status?.services[item.service.id]?.visible ?? true);
  const filtered = visible.filter(item => category === "전체" || item.category === category);

  function card(item: CatalogItem) {
    const { service } = item;
    const { href, external } = serviceLink(service);
    const locked = status?.services[service.id]?.allowed === false;
    const featured = Boolean(service.featured);
    return <a key={service.id} href={href} data-service={service.id} data-category={item.category}
      aria-label={`${item.name} · ${item.subtitle}${locked ? " · 등록자 전용" : ""}`}
      className={`${styles.card} ${styles[item.artwork]} ${featured ? styles.featured : ""}`}
      onClick={service.id === "agent" ? () => setAgentOpen(true) : undefined}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
      <div className={styles.visual}><ServiceArtwork kind={item.artwork} /></div>
      <div className={styles.cardBody}>
        <div className={styles.cardTop}><span className={styles.category}>{featured ? "FEATURED" : item.category}</span>
          {locked && <span className={styles.lock} title="등록된 분만 이용할 수 있어요" aria-label="등록자 전용"><svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="2" stroke="currentColor" /><path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="currentColor" /></svg></span>}
          {!service.href && <span className={styles.legacy}>기존 버전</span>}
        </div>
        <h3>{item.name}</h3>
        <p className={styles.subtitle}>{item.subtitle}</p>
        <p className={styles.capability}>{item.capability}</p>
        <span className={styles.cardAction}>{featured && <span>서비스 둘러보기</span>}<span className={styles.arrow}><Arrow /></span></span>
      </div>
    </a>;
  }

  return <>
    <div className={styles.filterRow}>
      <div className={styles.filters} role="group" aria-label="서비스 카테고리">
        {CATEGORIES.map(value => <button key={value} type="button" aria-pressed={category === value}
          onClick={() => setCategory(value)}>{value}</button>)}
      </div>
      <span className={styles.resultCount} role="status" aria-live="polite">{filtered.length}개 서비스</span>
    </div>
    {filtered.length ? <div className={styles.grid} aria-label={`${category} 서비스 목록`}>{filtered.map(card)}</div>
      : <p className={styles.empty}>이 카테고리에 공개된 서비스가 없어요.</p>}
    {/* Closing/filtering keeps the existing chat mounted and preserves its state. */}
    <div hidden={category !== "전체" && category !== "AI Agent"}>
      <AgentSection open={agentOpen} onOpenChange={setAgentOpen} />
    </div>
  </>;
}
