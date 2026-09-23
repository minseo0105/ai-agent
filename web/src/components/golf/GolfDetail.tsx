"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { golfApi, loadState, won, type ClubDetail, type Reviews } from "@/lib/golf";
import { Spinner, Tag } from "./ui";

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-extrabold tracking-tight">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl bg-surface-muted p-4">
      <div className="text-xs font-semibold text-muted">{label}</div>
      <div className="mt-1 text-xl font-extrabold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted">{sub}</div>}
    </div>
  );
}

function range(r: [number, number] | null | undefined) {
  if (!r) return "확인 필요";
  return r[0] === r[1] ? won(r[0]) : `${won(r[0])} ~ ${won(r[1])}`;
}

function SourceLink({ url, date, label = "출처" }: { url?: string; date?: string; label?: string }) {
  if (!url) return null;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-[11px] font-semibold text-golf hover:underline">
      {label}
      {date ? ` · ${date.slice(0, 10)} 확인` : ""} ↗
    </a>
  );
}

const STATUS_STYLE = {
  complete: "border-golf/30 bg-golf-soft text-golf",
  partial: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  missing: "border-border bg-surface-muted text-subtle",
} as const;
const STATUS_TEXT = { complete: "확인", partial: "일부", missing: "미확보" } as const;

function ActionLink({ href, children, external = true }: { href?: string; children: React.ReactNode; external?: boolean }) {
  const base = "flex items-center justify-center gap-1.5 rounded-xl border px-3 py-2.5 text-sm font-bold transition";
  if (!href) return <span className={`${base} cursor-not-allowed border-border text-subtle`}>{children}</span>;
  return (
    <a
      href={href}
      className={`${base} border-border hover:border-golf/50 hover:bg-golf-soft hover:text-golf`}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
    >
      {children}
    </a>
  );
}

function ReviewLinkCard({ item }: { item: Reviews["links"][number] }) {
  return (
    <a href={item.url} target="_blank" rel="noopener noreferrer" className="block rounded-2xl border border-border p-3.5 transition hover:border-golf/40">
      <div className="text-sm font-bold">
        {item.date ? item.date.slice(0, 10) : item.year} · {item.title}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted">{item.preview}</p>
      <span className="mt-1.5 inline-block text-xs font-bold text-golf">원문 보기 ↗</span>
    </a>
  );
}

function ReviewSection({ clubId, initial }: { clubId: string; initial: Reviews }) {
  const [reviews, setReviews] = useState(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      setReviews(await golfApi.refreshReviews(clubId));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const [first, ...rest] = reviews.links;

  return (
    <Section
      title="후기 · 상세정보"
      aside={
        <a href={reviews.naver_search_url} target="_blank" rel="noopener noreferrer" className="text-xs font-bold text-golf hover:underline">
          네이버 후기 찾기 ↗
        </a>
      }
    >
      {reviews.analysis ? (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            {reviews.analysis.cards.map((c) => (
              <div key={c.name} className="rounded-2xl bg-surface-muted p-3">
                <div className="text-xs font-semibold text-muted">{c.name}</div>
                <div className="mt-0.5 text-sm font-extrabold">{c.verdict}</div>
                <div className="mt-0.5 text-[11px] text-subtle">{c.sub}</div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-subtle">{reviews.analysis.meta}</p>
        </>
      ) : (
        <div className="rounded-2xl bg-surface-muted p-4 text-sm">
          <b>아직 저장된 후기 분석이 없습니다.</b>
          <p className="mt-1 text-xs text-muted">골프장 정보는 바로 확인할 수 있고, 후기 분석은 필요할 때만 실행합니다.</p>
        </div>
      )}

      {first && (
        <div className="mt-5 space-y-3">
          <div>
            <h3 className="text-sm font-extrabold">최근 후기 직접 보기</h3>
            <p className="text-xs text-subtle">
              {reviews.cutoff_year}~{reviews.current_year}년 · 날짜가 확인된 후기만
            </p>
          </div>
          <ReviewLinkCard item={first} />
          {rest.length > 0 && (
            <details>
              <summary className="cursor-pointer text-sm font-semibold text-muted">후기 {rest.length}개 더 보기</summary>
              <div className="mt-3 space-y-3">
                {rest.map((item) => (
                  <ReviewLinkCard key={item.url} item={item} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {reviews.evidence && reviews.evidence.length > 0 && (
        <details className="mt-5">
          <summary className="cursor-pointer text-sm font-semibold text-muted">후기 근거 상세</summary>
          <div className="mt-3 space-y-4">
            {reviews.evidence.map((ev) => (
              <div key={ev.name}>
                <div className="text-sm font-bold">
                  {ev.name} · {ev.verdict}
                </div>
                {ev.quotes.map((q, i) => (
                  <blockquote key={i} className="mt-1.5 border-l-2 border-golf/40 pl-3 text-xs text-muted">
                    “{q.text}” <span className="text-subtle">· {q.date}</span>
                    {q.url && (
                      <a href={q.url} target="_blank" rel="noopener noreferrer" className="ml-1 text-golf">
                        ↗ 원문
                      </a>
                    )}
                  </blockquote>
                ))}
              </div>
            ))}
          </div>
        </details>
      )}

      <details className="mt-5 rounded-2xl border border-border px-4 py-3">
        <summary className="cursor-pointer text-sm font-semibold text-muted">↻ 후기 최신화</summary>
        <div className="mt-3 space-y-2 text-xs text-muted">
          <p>전체 후기 요약은 최근 5년 웹 후기 기준입니다. 이 버튼을 눌렀을 때만 Tavily + GPT를 실행합니다 (수십 초 소요).</p>
          {!reviews.can_analyze && <p className="text-amber-600 dark:text-amber-400">TAVILY_API_KEY와 OPENAI_API_KEY를 확인해주세요.</p>}
          <button
            type="button"
            onClick={refresh}
            disabled={!reviews.can_analyze || loading}
            className="w-full rounded-xl bg-golf py-2.5 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40"
          >
            후기 빠른 최신화
          </button>
          {loading && <Spinner label="최근 후기 수집 → 유효 후기 선별 → AI 요약 중…" />}
          {reviews.notice && !loading && <p className="rounded-lg bg-surface-muted px-3 py-2 text-muted">{reviews.notice}</p>}
          {error && <p className="text-red-600 dark:text-red-400">{error}</p>}
        </div>
      </details>
    </Section>
  );
}

export default function GolfDetail({ id }: { id: string }) {
  const [club, setClub] = useState<ClubDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const last = loadState()?.last ?? null;
    golfApi.detail(id, last).then(setClub).catch((e) => setError((e as Error).message));
  }, [id]);

  const back = (
    <Link href="/golf" className="inline-flex items-center gap-1 text-sm font-bold text-muted hover:text-fg">
      ← 검색결과로
    </Link>
  );

  if (error) {
    return (
      <div className="space-y-4">
        {back}
        <p className="rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">{error}</p>
      </div>
    );
  }
  if (!club) {
    return (
      <div className="space-y-4">
        {back}
        <Spinner label="골프장 정보를 불러오는 중…" />
      </div>
    );
  }

  const fee = club.fee_block;
  const c = club.contact;

  return (
    <div className="space-y-4">
      {back}

      <header className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-950 via-emerald-800 to-green-600 px-6 py-7 text-white shadow-lg sm:px-8">
        <div className="text-[11px] font-bold tracking-[0.14em] text-emerald-200">GOLF COURSE</div>
        <h1 className="mt-1.5 text-2xl font-extrabold tracking-tight sm:text-3xl">{club.name}</h1>
        <p className="mt-1.5 text-sm text-emerald-100">
          {[club.region, club.city].filter(Boolean).join(" ")} · {club.holes}
        </p>
        {club.candidate && <span className="mt-3 inline-block rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-semibold">기본정보 확인 중</span>}
      </header>

      <Section title="한눈에 보기">
        <div className="flex flex-wrap gap-1.5">
          {club.overview_bits.map((b) => (
            <Tag key={b}>{b}</Tag>
          ))}
          {club.trait_badges.map((b) => (
            <Tag key={b} tone="golf">
              {b}
            </Tag>
          ))}
        </div>
        {club.holes_is_evidence && <p className="mt-2 text-xs text-subtle">※ 참고정보는 복수 출처에서 지지되지만 아직 확정 필드로 승격하지 않은 정보입니다.</p>}
        {club.profile && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {club.profile.official_name && <Tag tone="golf">정식명칭 {club.profile.official_name}</Tag>}
            {club.profile.facts.map((f) => (
              <Tag key={f}>{f}</Tag>
            ))}
            <SourceLink url={club.profile.source_url} label="공식 개요" />
          </div>
        )}
        <p className="mt-4 text-sm leading-relaxed">{club.intro}</p>
        <p className="mt-2 text-sm">
          {club.course_labels.length ? (
            <>
              <b>코스 구성</b> · {club.course_labels.join(" · ")}
            </>
          ) : (
            <span className="text-xs text-subtle">코스 구성 · 확인 가능한 상세정보가 아직 없습니다.</span>
          )}
        </p>
        {(club.verified_fields.length > 0 || club.evidence_fields.length > 0) && (
          <details className="mt-3 text-xs text-muted">
            <summary className="cursor-pointer">정보 출처 · 검증상태</summary>
            {club.verified_fields.length > 0 && <p className="mt-1">확정 검증 · {club.verified_fields.join(", ")}</p>}
            {club.evidence_fields.length > 0 && <p>참고정보 · {club.evidence_fields.join(", ")}</p>}
          </details>
        )}

        <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ActionLink href={c.phone ? `tel:${c.phone}` : undefined} external={false}>
            ☎ 전화
          </ActionLink>
          <ActionLink href={c.official_url || undefined}>⌂ 홈페이지</ActionLink>
          <ActionLink href={c.kakao_map}>↗ 카카오맵</ActionLink>
          <ActionLink href={c.naver_map}>↗ 네이버지도</ActionLink>
        </div>
        {c.phone_is_evidence && <p className="mt-2 text-xs text-subtle">☎ 전화번호는 참고정보입니다. 이용 전 공식 홈페이지에서 재확인해 주세요.</p>}
        {!club.has_coord && <p className="mt-2 text-xs text-subtle">📍 위치정보 확인 필요</p>}
      </Section>

      <Section title="라운드 핵심정보">
        <div className="grid grid-cols-2 gap-2">
          <Metric
            label={`${club.round.session} 그린피`}
            value={club.round.fee != null ? won(club.round.fee) : "확인 필요"}
            sub={`3인 플레이 · ${club.round.three_person}`}
          />
          <Metric label="캐디" value={club.round.caddie_mode} sub={club.round.fee_bits.join(" · ") || "캐디피 · 카트비 확인 필요"} />
        </div>
        {club.round.summary && <p className="mt-3 rounded-2xl bg-golf-soft px-4 py-3 text-sm leading-relaxed">{club.round.summary}</p>}
        {club.round.eval_bits.length > 0 && <p className="mt-2 text-xs text-muted">{club.round.eval_bits.join(" · ")}</p>}
        {club.snapshot.length > 0 && <p className="mt-2 text-xs text-muted">{club.snapshot.join(" · ")}</p>}
        {club.route && <p className="mt-3 rounded-2xl bg-accent-soft px-4 py-3 text-sm">🚗 {club.route}</p>}

        <div className="mt-4">
          {fee.verified && fee.kind === "table" ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <Metric
                  label="주중 그린피"
                  value={range(fee.weekday ?? fee.unspecified)}
                  sub={fee.weekday_total ? `1인 예상 ${range(fee.weekday_total)}` : undefined}
                />
                <Metric
                  label="주말 그린피"
                  value={range(fee.weekend ?? fee.unspecified)}
                  sub={fee.weekend_total ? `1인 예상 ${range(fee.weekend_total)}` : undefined}
                />
              </div>
              {(Object.keys(fee.weekday_sessions).length > 0 || Object.keys(fee.weekend_sessions).length > 0) && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(fee.weekday_sessions).map(([s, p]) => (
                    <Tag key={`d${s}`}>
                      주중 {s} {won(p)}~
                    </Tag>
                  ))}
                  {Object.entries(fee.weekend_sessions).map(([s, p]) => (
                    <Tag key={`e${s}`}>
                      주말 {s} {won(p)}~
                    </Tag>
                  ))}
                </div>
              )}
              <p className="text-xs text-subtle">
                {fee.note}
                {fee.latest_notice_month && ` · 최신 공지 ${fee.latest_notice_month}`}
              </p>
              <SourceLink url={fee.source_url} date={fee.checked_at} label="공식 요금표" />
            </div>
          ) : fee.verified && fee.kind === "legacy" ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Metric label="주중 · 1인 예상" value={won(fee.weekday_total)} sub={`그린피 ${won(fee.weekday_green)} + 카트 ${won(fee.cart)}÷4 + 캐디 ${won(fee.caddie)}÷4`} />
                <Metric label="주말 · 1인 예상" value={won(fee.weekend_total)} sub={`그린피 ${won(fee.weekend_green)} + 카트 ${won(fee.cart)}÷4 + 캐디 ${won(fee.caddie)}÷4`} />
              </div>
              <p className="mt-2 text-xs text-subtle">{fee.note}</p>
            </>
          ) : (
            <p className="rounded-2xl bg-surface-muted px-4 py-3 text-sm text-muted">{fee.text}</p>
          )}
        </div>
      </Section>

      {(club.operations.sessions.length > 0 ||
        club.operations.caddie.bits.length > 0 ||
        club.operations.cart.bits.length > 0 ||
        club.operations.players.length > 0) && (
        <Section title="운영 정보">
          <dl className="space-y-3 text-sm">
            {club.operations.sessions.length > 0 && (
              <div>
                <dt className="text-xs font-bold text-muted">티오프 시간대</dt>
                <dd className="mt-1 flex flex-wrap gap-1.5">
                  {club.operations.sessions.map((s) => (
                    <Tag key={s.name}>
                      {s.name} {s.time}
                    </Tag>
                  ))}
                </dd>
              </div>
            )}
            <div>
              <dt className="text-xs font-bold text-muted">캐디</dt>
              <dd className="mt-1 flex flex-wrap items-center gap-1.5">
                <Tag tone={club.operations.caddie.mode === "확인 필요" ? "default" : "golf"}>{club.operations.caddie.mode}</Tag>
                {club.operations.caddie.bits.map((b) => (
                  <Tag key={b}>{b}</Tag>
                ))}
                <SourceLink url={club.operations.caddie.source_url} date={club.operations.caddie.checked_at} />
              </dd>
            </div>
            {club.operations.cart.bits.length > 0 && (
              <div>
                <dt className="text-xs font-bold text-muted">카트</dt>
                <dd className="mt-1 flex flex-wrap items-center gap-1.5">
                  {club.operations.cart.bits.map((b) => (
                    <Tag key={b}>{b}</Tag>
                  ))}
                  <SourceLink url={club.operations.cart.source_url} date={club.operations.cart.checked_at} />
                </dd>
              </div>
            )}
            {club.operations.players.length > 0 && (
              <div>
                <dt className="text-xs font-bold text-muted">인원 조건</dt>
                <dd className="mt-1 space-y-1">
                  {club.operations.players.map((p) => (
                    <div key={p.label} className="flex flex-wrap items-center gap-1.5">
                      <Tag tone={p.status === "가능" ? "golf" : "warn"}>
                        {p.label} {p.status}
                      </Tag>
                      {p.note && <span className="text-xs text-muted">{p.note}</span>}
                    </div>
                  ))}
                  <SourceLink url={club.operations.players_source_url} />
                </dd>
              </div>
            )}
          </dl>
        </Section>
      )}

      <Section title="이용조건">
        <p className="text-sm text-muted">{club.objective_summary.length ? club.objective_summary.join(" · ") : "확인된 이용조건이 아직 없습니다."}</p>
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-semibold text-muted">이용조건 근거 · KGA 코스정보</summary>
          <div className="mt-3 space-y-3">
            {club.objective_details.map((d) => (
              <div key={d.feature} className="text-sm">
                <b>{d.feature}</b> · {d.label}
                <div className="text-xs text-subtle">{d.verification}</div>
                {d.notes.map((n, i) => (
                  <div key={i} className="text-xs text-subtle">
                    {n}
                  </div>
                ))}
              </div>
            ))}
            <div className="border-t border-border pt-3">
              {club.kga.matched ? (
                <div className="space-y-2 text-sm">
                  <h3 className="font-extrabold">⛳ KGA 공인 코스정보</h3>
                  <p className="text-xs text-subtle">
                    {club.kga.status} · 확인일 {club.kga.checked_at} · 대한골프협회
                  </p>
                  {club.kga.combos?.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {club.kga.combos.map((x) => (
                        <Tag key={x}>{x}</Tag>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-subtle">KGA 매칭은 확인됐지만 코스 조합 상세는 확인되지 않았습니다.</p>
                  )}
                  {club.ratings.length ? (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[320px] text-xs">
                        <thead className="text-left text-muted">
                          <tr>
                            <th className="py-1 pr-2 font-semibold">티</th>
                            <th className="py-1 pr-2 font-semibold">전장</th>
                            <th className="py-1 pr-2 font-semibold">Course Rating</th>
                            <th className="py-1 font-semibold">Slope</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                          {club.ratings.map((r, i) => (
                            <tr key={i}>
                              <td className="py-1 pr-2">
                                {r.course && club.ratings.some((x) => x.course !== r.course) ? `${r.course} · ` : ""}
                                {r.tee} {r.gender}
                              </td>
                              <td className="py-1 pr-2">{r.length_yards ? `${r.length_yards.toLocaleString("ko-KR")}yd` : "-"}</td>
                              <td className="py-1 pr-2">{r.rating ?? "-"}</td>
                              <td className="py-1">{r.slope ?? "-"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-xs text-subtle">Course Rating · Slope Rating 상세값은 KGA 상세 데이터가 연결된 코스부터 표시됩니다.</p>
                  )}
                  {club.kga.source_url && (
                    <a href={club.kga.source_url} target="_blank" rel="noopener noreferrer" className="inline-block text-xs font-bold text-golf">
                      KGA 코스레이팅 DB ↗
                    </a>
                  )}
                </div>
              ) : (
                <p className="text-xs text-subtle">KGA 공인 코스정보는 아직 연결되지 않았습니다.</p>
              )}
            </div>
          </div>
        </details>
      </Section>

      <Section title="코스 · 홀 정보">
        {club.course_cards.length > 0 ? (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {club.course_cards.map((cc, i) => (
              <div key={i} className="rounded-2xl bg-surface-muted p-3">
                <div className="text-sm font-bold">{cc.title}</div>
                {cc.specs && <div className="text-[11px] font-semibold text-muted">{cc.specs}</div>}
                {cc.type && <div className="mt-1 text-xs leading-relaxed text-muted">{cc.type}</div>}
                {cc.source_url && (
                  <div className="mt-1">
                    <SourceLink url={cc.source_url} />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-subtle">코스 구성 · 확인 가능한 상세정보가 아직 없습니다.</p>
        )}

        {club.hole_rows.length > 0 ? (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-semibold text-muted">홀별 정보 {club.hole_rows.length}개</summary>
            <div className="mt-3 divide-y divide-border">
              {club.hole_rows.map((r, i) => (
                <div key={i} className="py-2.5 text-sm">
                  <b>{r.course ? `${r.course} · ${r.hole}번 홀` : `${r.hole}번 홀`}</b>
                  {r.facts && <div className="text-xs text-muted">{r.facts}</div>}
                  {r.strategy && <div className="text-xs text-muted">공략 · {r.strategy}</div>}
                </div>
              ))}
            </div>
          </details>
        ) : (
          <p className="mt-3 text-xs text-subtle">홀별 Par · 거리 · HDCP · 공략 정보는 확인된 골프장부터 표시됩니다.</p>
        )}
        <p className="mt-3 text-xs text-muted">{club.course_overview}</p>
        <p className="mt-1 text-xs text-subtle">{club.data_checked ? `공식정보 확인 · ${club.data_checked}` : "공식정보 최신 확인 필요"}</p>
      </Section>

      <ReviewSection clubId={club.id} initial={club.reviews} />

      {(club.completeness || club.sources.items.length > 0 || club.sources.public_status) && (
        <Section
          title="정보 출처 · 데이터 충실도"
          aside={club.completeness && <span className="text-xs font-bold text-muted">{club.completeness.complete}/{club.completeness.total} 항목 확인</span>}
        >
          {club.completeness && (
            <div className="flex flex-wrap gap-1.5">
              {club.completeness.items.map((it) => (
                <span key={it.label} className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[it.status]}`}>
                  {it.label} {STATUS_TEXT[it.status]}
                </span>
              ))}
            </div>
          )}
          {club.sources.public_status && (
            <p className="mt-3 text-xs text-muted">
              공공데이터(행정안전부) 영업상태 · {club.sources.public_status}
              {club.sources.public_checked_at && ` · ${club.sources.public_checked_at.slice(0, 10)} 갱신`}
            </p>
          )}
          {club.sources.items.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {club.sources.items.map((s) => (
                <li key={s.url} className="text-xs">
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-golf hover:underline">
                    {s.label} ↗
                  </a>
                  <span className="text-subtle">
                    {s.checked_at && ` · ${s.checked_at.slice(0, 10)}`}
                    {s.fields.length > 0 && ` · ${s.fields.join(", ")}`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-[11px] text-subtle">공식 홈페이지 · KGA · 공공데이터에서 확인한 정보만 확정값으로 표시합니다.</p>
        </Section>
      )}
    </div>
  );
}
