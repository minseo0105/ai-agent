"use client";

import AgentChat from "@/components/AgentChat";
import { useAccess } from "@/components/access/AccessProvider";

/** 홈의 AI 에이전트 섹션. 관리자 설정에서 숨기면 사라지고, 권한이 없으면 안내만 보인다. */
export default function AgentSection() {
  const { status } = useAccess();
  const s = status?.services.agent;
  if (s && !s.visible) return null;
  return (
    <section id="agent" className="mt-10 scroll-mt-6 sm:mt-12">
      <div className="mb-5 border-t border-border pt-8">
        <h2 className="flex items-center gap-2 text-xl font-extrabold tracking-tight">
          <span aria-hidden className="flex size-7 items-center justify-center rounded-lg bg-accent-soft text-sm text-woori">✦</span>
          AI 에이전트
        </h2>
        <p className="mt-1.5 text-sm text-slate-600 dark:text-muted">공시·법령·웹 검색을 필요한 순간에 호출하는 도구형 에이전트입니다.</p>
      </div>
      {s && !s.allowed ? (
        <p className="rounded-2xl border border-border bg-surface px-4 py-6 text-center text-sm text-muted">
          🔒 등록된 분만 이용할 수 있어요. 관리자에게 받은 접속 코드로 입장해 주세요.
        </p>
      ) : (
        <AgentChat />
      )}
    </section>
  );
}
