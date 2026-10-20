"use client";

import AgentChat from "@/components/AgentChat";
import { useAccess } from "@/components/access/AccessProvider";
import styles from "./home/Home.module.css";

/** 홈의 AI 에이전트 섹션. 관리자 설정에서 숨기면 사라지고, 권한이 없으면 안내만 보인다. */
export default function AgentSection({ open = false, onOpenChange }: { open?: boolean; onOpenChange?: (open: boolean) => void }) {
  const { status } = useAccess();
  const s = status?.services.agent;
  if (s && !s.visible) return null;
  return (
    <details id="agent" className={styles.agentArea} open={open} onToggle={event => onOpenChange?.(event.currentTarget.open)}>
      <summary className={styles.agentSummary}><span><strong>AI 에이전트</strong><span>기업 공시 · 법령 · 웹 검색을 한 번에</span></span><span aria-hidden="true">{open ? "−" : "+"}</span></summary>
      <div className={styles.agentContent}>
      {s && !s.allowed ? (
        <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">
          🔒 등록된 분만 이용할 수 있어요. 관리자에게 받은 접속 코드로 입장해 주세요.
        </p>
      ) : (
        <AgentChat />
      )}
      </div>
    </details>
  );
}
