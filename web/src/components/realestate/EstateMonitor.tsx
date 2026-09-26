"use client";

import { useEffect, useState } from "react";
import { ChoiceChips, Field, Segmented, Spinner, Tag, inputClass } from "@/components/golf/ui";
import {
  currentMonth,
  estateApi,
  type EstateOptions,
  type MonitorState,
  type Notification,
  type Subscription,
  type Trade,
} from "@/lib/realestate";
import RegionPicker from "./RegionPicker";

type Tab = "청약 조회" | "실거래 조회" | "모니터링 조건" | "알림함";
const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm">{children}</div>;
}

function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`w-full rounded-xl bg-estate py-2.5 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-40 ${props.className ?? ""}`}
    />
  );
}

function ErrorBox({ message }: { message: string }) {
  return message ? <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{message}</p> : null;
}

// ------------------------------------------------------------------ 청약

function SubscriptionTab({ options }: { options: EstateOptions }) {
  const [regions, setRegions] = useState<string[]>([]);
  const [supply, setSupply] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<string[]>([]);
  const [result, setResult] = useState<{ kind: "apt" | "unsold"; total: number; items: Subscription[] } | null>(null);
  const [loading, setLoading] = useState<"apt" | "unsold" | null>(null);
  const [error, setError] = useState("");

  async function search(kind: "apt" | "unsold") {
    setLoading(kind);
    setError("");
    try {
      const r = await estateApi.subscriptions({ kind, regions, supply_types: supply, kinds, statuses });
      setResult({ kind, ...r });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-4">
      <Field label="조회지역" hint="선택하지 않으면 전체">
        <RegionPicker regions={options.regions} value={regions} onChange={setRegions} selectWholeScope />
      </Field>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="공급구분">
          <ChoiceChips accent="estate" options={options.supply_types} selected={supply} onToggle={(v) => setSupply(toggle(supply, v))} />
        </Field>
        <Field label="청약유형">
          <ChoiceChips accent="estate" options={options.kinds} selected={kinds} onToggle={(v) => setKinds(toggle(kinds, v))} />
        </Field>
        <Field label="접수상태">
          <ChoiceChips accent="estate" options={options.statuses} selected={statuses} onToggle={(v) => setStatuses(toggle(statuses, v))} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <PrimaryButton onClick={() => search("apt")} disabled={!!loading}>
          신규 APT 청약 조회
        </PrimaryButton>
        <button
          type="button"
          onClick={() => search("unsold")}
          disabled={!!loading}
          className="w-full rounded-xl border border-estate/40 py-2.5 text-sm font-extrabold text-estate transition hover:bg-estate-soft disabled:opacity-40"
        >
          무순위 / 잔여세대 조회
        </button>
      </div>
      {loading && <Spinner label="청약홈 공고를 조회하고 있어요…" />}
      <ErrorBox message={error} />

      {result && !loading && (
        <div className="space-y-3">
          <p className="text-sm font-bold">
            {result.kind === "apt" ? "신규 APT 청약" : "무순위 / 잔여세대"} · 전체 {result.total}건 중 조건에 맞는 {result.items.length}건
          </p>
          {result.items.length === 0 && <p className="text-sm text-muted">조건에 맞는 공고가 없어요. 지역이나 상태 조건을 넓혀 보세요.</p>}
          <div className="grid gap-3 md:grid-cols-2">
            {result.items.slice(0, 60).map((it) => (
              <Card key={it.id}>
                <div className="text-base font-extrabold leading-snug">{it.name}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-estate-soft px-2.5 py-0.5 text-[11px] font-bold text-estate">{it.status}</span>
                  <Tag>{it.supply_type}</Tag>
                  <Tag>{it.subscription_kind}</Tag>
                </div>
                <p className="mt-2 text-xs text-muted">{[it.region, it.address].filter(Boolean).join(" · ")}</p>
                <p className="mt-1 text-xs text-muted">
                  모집공고 {it.announce_date || "-"} · 접수 {it.apply_date || "-"}
                </p>
                {it.homepage && (
                  <a href={it.homepage.startsWith("http") ? it.homepage : `https://${it.homepage}`} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs font-bold text-estate hover:underline">
                    분양 홈페이지 ↗
                  </a>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 실거래

function TradeTab({ options }: { options: EstateOptions }) {
  const [types, setTypes] = useState<string[]>(["아파트", "연립·다세대"]);
  const [regions, setRegions] = useState<string[]>(["서울 > 송파구", "서울 > 강동구", "경기 > 하남시"]);
  const [month, setMonth] = useState(currentMonth());
  const [maxPrice, setMaxPrice] = useState("");
  const [appliedPrice, setAppliedPrice] = useState<number | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [result, setResult] = useState<{ items: Trade[]; errors: string[]; counts: Record<string, number>; requests: number } | null>(null);
  const [typeFilter, setTypeFilter] = useState<string[]>([]);
  const [visible, setVisible] = useState(40);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function search() {
    setError("");
    if (!types.length) return setError("주택유형을 1개 이상 선택해주세요.");
    if (!regions.length) return setError("조회지역을 1개 이상 선택해주세요.");
    const price = maxPrice.trim() === "" ? undefined : Number(maxPrice);
    if (price !== undefined && (!Number.isFinite(price) || price <= 0 || price > 10000)) {
      return setError("최대 매매가격은 0보다 크고 10,000억원 이하로 입력해주세요.");
    }
    setLoading(true);
    setResult(null);
    setProgress({ done: 0, total: regions.length });
    try {
      setResult(await estateApi.trades({ regions, property_types: types, month, max_price_100m: price }, (done, total) => setProgress({ done, total })));
      setAppliedPrice(price ?? null);
      setTypeFilter([]);
      setVisible(40);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const items = (result?.items ?? []).filter((x) => !typeFilter.length || typeFilter.includes(x.property_type));
  const monthValue = `${month.slice(0, 4)}-${month.slice(4, 6)}`;

  return (
    <div className="space-y-4">
      <Field label="주택유형" hint="여러 개 선택 가능">
        <ChoiceChips accent="estate" options={options.property_types} selected={types} onToggle={(v) => setTypes(toggle(types, v))} />
      </Field>
      <Field label="조회지역">
        <RegionPicker regions={options.regions} value={regions} onChange={setRegions} selectWholeScope />
      </Field>
      <Field label="계약년월">
        <input
          type="month"
          className={`${inputClass} max-w-48`}
          value={monthValue}
          onChange={(e) => e.target.value && setMonth(e.target.value.replace("-", ""))}
        />
      </Field>
      <Field label="최대 매매가격" hint="억원 단위 · 비워두면 전체 · 입력한 금액 포함 이하">
        <div className="flex items-center gap-2">
          <input aria-label="최대 매매가격 (억원)" type="number" inputMode="decimal" min="0.01" max="10000" step="0.01" placeholder="예: 5 → 5억원 이하" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} className={`${inputClass} max-w-64`} />
          <span className="shrink-0 text-sm text-muted">억원 이하</span>
        </div>
        <div className="mt-2">
          <ChoiceChips accent="estate" options={["전체", "3억 이하", "5억 이하", "7억 이하", "10억 이하"]} selected={[maxPrice === "" ? "전체" : `${maxPrice}억 이하`]} onToggle={(v) => setMaxPrice(v === "전체" ? "" : v.replace("억 이하", ""))} />
        </div>
        <p className="mt-2 text-xs text-muted">실제 계약된 매매가격 기준이며 현재 매물의 호가가 아닙니다. 가격 미확인 거래는 가격 조건 적용 시 제외합니다.</p>
      </Field>
      <PrimaryButton onClick={search} disabled={loading}>
        실거래 조회 · {regions.length}개 지역 × {types.length}개 유형
      </PrimaryButton>
      {loading && <Spinner label={`지역 ${progress.done}/${progress.total}곳 조회 완료 · 전체 지역은 나누어 조회하므로 시간이 걸릴 수 있어요…`} />}
      <ErrorBox message={error} />

      {result && !loading && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {Object.entries(result.counts).map(([k, v]) => (
              <div key={k} className="rounded-2xl bg-surface-muted px-4 py-2.5">
                <div className="text-[11px] font-semibold text-muted">{k}</div>
                <div className="text-lg font-extrabold">{v}건</div>
              </div>
            ))}
          </div>
          {result.errors.length > 0 && (
            <details className="rounded-xl bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
              <summary className="cursor-pointer">일부 조회 실패 {result.errors.length}건</summary>
              <ul className="mt-1 list-disc pl-4">
                {result.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
              <p className="mt-1">연립·다세대·단독/다가구·오피스텔 API는 공공데이터포털에서 별도 활용신청이 필요할 수 있어요.</p>
            </details>
          )}
          {Object.keys(result.counts).length > 1 && (
            <ChoiceChips accent="estate" options={Object.keys(result.counts)} selected={typeFilter} onToggle={(v) => setTypeFilter(toggle(typeFilter, v))} />
          )}
          <p className="text-xs text-subtle">
            {items.length}건 · 최근 거래일 순 · {appliedPrice === null ? "가격 전체" : `${appliedPrice}억원 이하`}
          </p>
          {items.length === 0 && <p className="text-sm text-muted">조건에 맞는 실거래가 없어요. 가격 상한·지역·계약년월을 조정해 보세요.</p>}
          <div className="grid gap-3 md:grid-cols-2">
            {items.slice(0, visible).map((it) => (
              <Card key={it.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap gap-1.5">
                      <span className="rounded-full bg-estate-soft px-2.5 py-0.5 text-[11px] font-bold text-estate">{it.property_type}</span>
                      <Tag>{it.region_label}</Tag>
                    </div>
                    <div className="mt-1.5 truncate text-base font-extrabold">{it.name}</div>
                    <p className="text-xs text-muted">{[it.region, it.road_name, it.jibun].filter(Boolean).join(" · ")}</p>
                    <p className="text-xs text-muted">
                      {it.area > 0 ? `${it.area.toFixed(1)}㎡ (${(it.area / 3.3058).toFixed(1)}평)` : "면적정보 없음"} · {it.floor || "-"}층 · 준공 {it.build_year || "-"}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-lg font-extrabold text-estate">{it.price_text}</div>
                    <div className="text-[11px] text-subtle">{it.date}</div>
                  </div>
                </div>
                <a href={it.naver_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs font-bold text-estate hover:underline">
                  네이버부동산 주변 매물 ↗
                </a>
              </Card>
            ))}
          </div>
          {visible < items.length && (
            <button type="button" onClick={() => setVisible(visible + 40)} className="w-full rounded-xl border border-border py-2.5 text-sm font-bold text-muted hover:text-fg">
              40건 더보기 · 남은 {items.length - visible}건
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 모니터링

function MonitorTab({ options }: { options: EstateOptions }) {
  const [state, setState] = useState<MonitorState | null>(null);
  const [regions, setRegions] = useState<string[]>(["서울 > 송파구", "서울 > 강동구", "경기 > 하남시"]);
  const [events, setEvents] = useState<string[]>(["신규청약", "무순위청약"]);
  const [types, setTypes] = useState<string[]>(["아파트", "연립·다세대"]);
  const [supply, setSupply] = useState<string[]>([]);
  const [maxPrice, setMaxPrice] = useState(20);
  const [minArea, setMinArea] = useState(40);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [runResult, setRunResult] = useState<Awaited<ReturnType<typeof estateApi.runNow>> | null>(null);

  useEffect(() => {
    estateApi.monitor().then(setState).catch((e) => setError((e as Error).message));
  }, []);

  async function act(label: string, fn: () => Promise<MonitorState>) {
    setBusy(label);
    setError("");
    try {
      setState(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function runNow() {
    setBusy("run");
    setError("");
    try {
      setRunResult(await estateApi.runNow());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  if (!state) return error ? <ErrorBox message={error} /> : <Spinner label="모니터링 조건을 불러오는 중…" />;

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-extrabold">자동 모니터링 {state.auto_enabled ? "ON" : "OFF"}</div>
            <p className="text-xs text-muted">
              {state.auto_enabled ? "설정된 주기마다 활성 조건을 확인합니다." : "OFF이면 예약 실행 중에도 공공데이터 API를 호출하지 않습니다."}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={state.auto_enabled}
            disabled={!!busy}
            onClick={() => act("auto", () => estateApi.setAuto(!state.auto_enabled))}
            className={`relative h-7 w-12 rounded-full transition ${state.auto_enabled ? "bg-estate" : "bg-surface-muted"}`}
          >
            <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition ${state.auto_enabled ? "left-6" : "left-1"}`} />
          </button>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center">
          {[
            ["활성 조건", state.usage.enabled_rules],
            ["청약 API/회", state.usage.subscription_calls],
            ["실거래 API/회", state.usage.trade_calls],
            ["총 호출/회", state.usage.total_calls_per_cycle],
          ].map(([k, v]) => (
            <div key={k} className="rounded-xl bg-surface-muted py-2">
              <div className="text-lg font-extrabold">{v}</div>
              <div className="text-[10px] font-semibold text-muted">{k}</div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-subtle">호출량은 공공데이터포털 API 요청 수이며, 자동 모니터링에는 AI 토큰을 쓰지 않습니다.</p>
      </Card>

      <Card>
        <div className="mb-3 text-sm font-extrabold">새 모니터링 조건</div>
        <div className="space-y-4">
          <Field label="관심지역">
            <RegionPicker regions={options.regions} value={regions} onChange={setRegions} />
          </Field>
          <Field label="탐지 이벤트">
            <ChoiceChips accent="estate" options={options.event_types} selected={events} onToggle={(v) => setEvents(toggle(events, v))} />
          </Field>
          {events.includes("신규실거래") && (
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="실거래 주택유형">
                <ChoiceChips accent="estate" options={options.property_types} selected={types} onToggle={(v) => setTypes(toggle(types, v))} />
              </Field>
              <Field label="최대가격" hint="억원 · 0이면 제한 없음">
                <input type="number" min={0} max={100} step={0.5} className={inputClass} value={maxPrice} onChange={(e) => setMaxPrice(Number(e.target.value))} />
              </Field>
              <Field label="최소면적" hint="㎡ · 0이면 제한 없음">
                <input type="number" min={0} max={500} step={1} className={inputClass} value={minArea} onChange={(e) => setMinArea(Number(e.target.value))} />
              </Field>
            </div>
          )}
          {(events.includes("신규청약") || events.includes("무순위청약")) && (
            <Field label="청약 공급구분" hint="선택하지 않으면 전체">
              <ChoiceChips accent="estate" options={options.supply_types} selected={supply} onToggle={(v) => setSupply(toggle(supply, v))} />
            </Field>
          )}
          <PrimaryButton
            disabled={!!busy || !regions.length || !events.length}
            onClick={() =>
              act("add", () =>
                estateApi.addRules({
                  regions,
                  event_types: events,
                  property_types: events.includes("신규실거래") ? types : [],
                  supply_types: supply,
                  max_price_100m: maxPrice,
                  min_area: minArea,
                }),
              )
            }
          >
            이 조건으로 모니터링 시작 · {regions.length}개 지역 × {events.length}개 이벤트
          </PrimaryButton>
        </div>
      </Card>

      <div className="space-y-2">
        <button
          type="button"
          onClick={runNow}
          disabled={!!busy}
          className="w-full rounded-xl border border-estate/40 py-2.5 text-sm font-extrabold text-estate transition hover:bg-estate-soft disabled:opacity-40"
        >
          지금 한 번 전체 확인
        </button>
        {busy === "run" && <Spinner label="저장된 조건으로 새 이벤트를 확인하고 있어요…" />}
        {runResult && busy !== "run" && (
          <p className="rounded-xl bg-surface-muted px-3 py-2 text-sm">
            탐지 이벤트 {runResult.events} · 새 알림 {runResult.notifications} · 조회 데이터{" "}
            {(runResult.fetched?.subscriptions ?? 0) + (runResult.fetched?.trades ?? 0)}건
            {runResult.errors?.length ? ` · 오류 ${runResult.errors.length}건: ${runResult.errors.join(" / ")}` : ""}
          </p>
        )}
      </div>
      <ErrorBox message={error} />

      <div className="space-y-2">
        <h3 className="text-sm font-extrabold">저장된 조건 {state.rules.length}개</h3>
        {state.rules.length === 0 && <p className="text-sm text-muted">아직 저장된 모니터링 조건이 없어요.</p>}
        {state.rules.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-surface px-4 py-3">
            <div className="min-w-0">
              <div className="text-sm font-bold">
                {r.region} · {r.event_type}
              </div>
              <div className="text-xs text-muted">
                {r.event_type === "신규실거래"
                  ? `${r.property_type ?? "아파트"} · ${r.max_price_100m ? `${r.max_price_100m}억원 이하` : "가격 제한 없음"} · ${r.min_area ? `${r.min_area}㎡ 이상` : "면적 제한 없음"}`
                  : `공급구분 ${r.supply_type || "전체"}`}{" "}
                · {r.enabled ? "모니터링 중" : "중지됨"}
              </div>
            </div>
            <div className="flex gap-1.5">
              <button type="button" disabled={!!busy} onClick={() => act("t", () => estateApi.toggleRule(r.id))} className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold hover:bg-surface-muted">
                {r.enabled ? "중지" : "재시작"}
              </button>
              <button type="button" disabled={!!busy} onClick={() => act("d", () => estateApi.deleteRule(r.id))} className="rounded-lg border border-border px-3 py-1.5 text-xs font-bold text-red-600 hover:bg-red-500/10 dark:text-red-400">
                삭제
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ 알림함

function AlertTab({ onUnread }: { onUnread: (n: number) => void }) {
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    estateApi
      .notifications()
      .then((r) => {
        setItems(r.items);
        onUnread(r.unread);
      })
      .catch((e) => setError((e as Error).message));
  }, [onUnread]);

  async function read(id: number) {
    const r = await estateApi.markRead(id);
    setItems(r.items);
    onUnread(r.unread);
  }

  if (error) return <ErrorBox message={error} />;
  if (!items) return <Spinner label="알림을 불러오는 중…" />;
  if (!items.length) return <p className="text-sm text-muted">아직 생성된 알림이 없어요. 모니터링 조건을 저장하고 ‘지금 한 번 전체 확인’을 눌러 보세요.</p>;

  return (
    <div className="space-y-2">
      {items.map((n) => (
        <div key={n.id} className={`flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 ${n.is_read ? "border-border bg-surface" : "border-estate/30 bg-estate-soft"}`}>
          <div className="min-w-0">
            <div className="text-sm font-bold">
              {!n.is_read && <span className="mr-1.5 inline-block size-2 rounded-full bg-estate align-middle" />}
              {n.title}
            </div>
            <p className="mt-0.5 text-xs text-muted">
              {n.category} · {n.message}
            </p>
            <p className="text-[11px] text-subtle">{n.created_at}</p>
          </div>
          {!n.is_read && (
            <button type="button" onClick={() => read(n.id)} className="shrink-0 rounded-lg border border-border px-3 py-1.5 text-xs font-bold hover:bg-surface">
              읽음
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ 페이지

export default function EstateMonitor() {
  const [options, setOptions] = useState<EstateOptions | null>(null);
  const [tab, setTab] = useState<Tab>("실거래 조회");
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    estateApi.options().then(setOptions).catch(() => setError("백엔드에 연결하지 못했어요. FastAPI 서버가 실행 중인지 확인해 주세요."));
    estateApi.notifications().then((r) => setUnread(r.unread)).catch(() => {});
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!options) return <Spinner label="불러오는 중…" />;

  return (
    <div className="space-y-4">
      {!options.api_key && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">
          PUBLIC_DATA_API_KEY가 없어요. .streamlit/secrets.toml의 [realestate] 설정을 확인해 주세요.
        </p>
      )}
      <Segmented
        value={tab}
        onChange={setTab}
        full
        ariaLabel="부동산 모니터 메뉴"
        options={[
          { value: "실거래 조회" as const, label: "실거래" },
          { value: "청약 조회" as const, label: "청약" },
          { value: "모니터링 조건" as const, label: "모니터링" },
          { value: "알림함" as const, label: unread ? `알림 ${unread}` : "알림" },
        ]}
      />
      <div className="rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
        {/* 탭을 숨겨도 입력값·결과가 유지되도록 언마운트하지 않는다 */}
        <div hidden={tab !== "청약 조회"}>
          <SubscriptionTab options={options} />
        </div>
        <div hidden={tab !== "실거래 조회"}>
          <TradeTab options={options} />
        </div>
        <div hidden={tab !== "모니터링 조건"}>{tab === "모니터링 조건" && <MonitorTab options={options} />}</div>
        <div hidden={tab !== "알림함"}>{tab === "알림함" && <AlertTab onUnread={setUnread} />}</div>
      </div>
      <p className="text-[11px] text-subtle">
        저장소: {options.storage === "supabase" ? "Supabase (클라우드 · GitHub Actions 예약 모니터와 공유)" : "이 PC의 로컬 DB (realestate_monitor.db)"}
      </p>
    </div>
  );
}
