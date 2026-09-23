"use client";

import { useEffect, useRef, useState } from "react";
import { Field, Segmented, Spinner } from "@/components/golf/ui";
import { DEFAULT_OPTIONS, MAX_UPLOAD_MB, gifApi, type GifMeta, type GifOptions } from "@/lib/gif";

const ACCEPT = "image/png,image/jpeg,image/webp";
const EFFECTS: { key: keyof GifOptions; label: string; help?: string }[] = [
  { key: "use_drive", label: "🚗 달려가기", help: "좌우 이동 + 원근감" },
  { key: "use_zoom", label: "🔎 줌 인/아웃" },
  { key: "use_bounce", label: "↕️ 바운스", help: "주행 시 미세한 상하 움직임" },
  { key: "use_shake", label: "↔️ 좌우 흔들림" },
  { key: "use_tilt", label: "↗️ 틸트", help: "좌우로 아주 살짝 기울기" },
  { key: "use_pan", label: "🎥 화면 패닝", help: "배경 또는 화면이 서서히 이동" },
];

function useObjectUrl(blob: Blob | File | null) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url;
}

function Section({ kicker, title, desc, children }: { kicker: string; title: string; desc: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-3xl border border-border bg-surface p-5 shadow-sm sm:p-6">
      <div>
        <div className="text-[10px] font-extrabold tracking-[0.12em] text-accent">{kicker}</div>
        <h2 className="mt-0.5 text-lg font-extrabold tracking-tight">{title}</h2>
        <p className="text-xs text-muted">{desc}</p>
      </div>
      {children}
    </section>
  );
}

function Toggle({ checked, onChange, label, help, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; help?: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`flex w-full items-center justify-between gap-3 rounded-2xl border px-3.5 py-3 text-left transition disabled:opacity-40 ${
        checked ? "border-accent/60 bg-accent-soft" : "border-border hover:border-accent/40"
      }`}
    >
      <span>
        <span className="block text-sm font-bold">{label}</span>
        {help && <span className="block text-[11px] text-subtle">{help}</span>}
      </span>
      <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${checked ? "bg-accent" : "bg-border"}`}>
        <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow transition-all ${checked ? "left-[18px]" : "left-0.5"}`} />
      </span>
    </button>
  );
}

function Slider({ label, value, min, max, step, onChange, suffix = "" }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; suffix?: string }) {
  return (
    <label className="block space-y-1">
      <span className="flex justify-between text-xs font-bold text-muted">
        {label}
        <span className="text-fg">
          {value}
          {suffix}
        </span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--accent)]" />
    </label>
  );
}

function Dropzone({ label, file, onFile, optional }: { label: string; file: File | null; onFile: (f: File | null) => void; optional?: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const url = useObjectUrl(file);
  const [drag, setDrag] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`relative flex min-h-40 flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border-2 border-dashed p-3 text-center transition ${
        drag ? "border-accent bg-accent-soft" : "border-border bg-surface-muted"
      }`}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={label} className="max-h-36 rounded-xl object-contain" />
      ) : (
        <>
          <div className="text-sm font-bold">{label}</div>
          <div className="text-[11px] text-subtle">PNG · JPG · WEBP · {MAX_UPLOAD_MB}MB 이하{optional ? " · 선택" : ""}</div>
        </>
      )}
      <div className="flex gap-2">
        <button type="button" onClick={() => inputRef.current?.click()} className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-bold hover:border-accent/50">
          {file ? "바꾸기" : "파일 선택"}
        </button>
        {file && (
          <button type="button" onClick={() => onFile(null)} className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-bold text-muted hover:text-fg">
            지우기
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export default function GifMaker() {
  const [image, setImage] = useState<File | null>(null);
  const [background, setBackground] = useState<File | null>(null);
  const [o, setO] = useState<GifOptions>(DEFAULT_OPTIONS);
  const [preview, setPreview] = useState<Blob | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [gif, setGif] = useState<Blob | null>(null);
  const [meta, setMeta] = useState<GifMeta | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const imageUrl = useObjectUrl(image);
  const previewUrl = useObjectUrl(preview);
  const gifUrl = useObjectUrl(gif);
  const resultRef = useRef<HTMLDivElement>(null);

  const set = <K extends keyof GifOptions>(k: K, v: GifOptions[K]) => setO((prev) => ({ ...prev, [k]: v }));

  function pickFile(f: File | null, which: "image" | "background") {
    setError("");
    if (f && f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`이미지는 ${MAX_UPLOAD_MB}MB 이하만 올릴 수 있습니다.`);
      return;
    }
    if (f && !ACCEPT.split(",").includes(f.type)) {
      setError("PNG · JPG · WEBP 이미지만 지원합니다.");
      return;
    }
    if (which === "image") {
      setImage(f);
      setGif(null);
      setMeta(null);
    } else {
      setBackground(f);
      // 원본처럼 배경을 올리면 배경 사용 + 차량 배경 제거를 기본으로 켠다
      setO((prev) => ({ ...prev, use_background: !!f, remove_bg: f ? true : prev.remove_bg }));
    }
  }

  // 합성 미리보기 (배경 제거·배경 합성이 켜졌을 때만 서버에서 만든다)
  const needsPreview = !!image && (o.remove_bg || (o.use_background && !!background));
  useEffect(() => {
    if (!image || !needsPreview) {
      setPreview(null);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      setPreviewBusy(true);
      try {
        setPreview(await gifApi.preview(image, background, { remove_bg: o.remove_bg, use_background: o.use_background, canvas_color: o.canvas_color }, ctrl.signal));
        setError("");
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      } finally {
        if (!ctrl.signal.aborted) setPreviewBusy(false);
      }
    }, 350);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [image, background, needsPreview, o.remove_bg, o.use_background, o.canvas_color]);

  const anyEffect = EFFECTS.some((e) => o[e.key]);

  async function generate() {
    if (!image) return;
    if (!anyEffect) {
      setError("효과를 최소 1개 선택해주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await gifApi.generate(image, background, o);
      setGif(r.blob);
      setMeta(r.meta);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Section kicker="STEP 01 · SOURCE" title="이미지를 준비해주세요" desc="차량 이미지만 올려도 되고, 별도 배경을 함께 올려 합성할 수도 있습니다.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Dropzone label="차량(전경) 이미지" file={image} onFile={(f) => pickFile(f, "image")} />
          <Dropzone label="배경 이미지" file={background} onFile={(f) => pickFile(f, "background")} optional />
        </div>
        {!image && <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-muted">차량 이미지를 올리면 GIF 제작 옵션이 나타납니다.</p>}
      </Section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {image && (
        <>
          <Section kicker="STEP 02 · COMPOSITE" title="전경과 배경을 정리합니다" desc="배경 제거는 처음 한 번만 시간이 걸리고, 같은 이미지는 이후 빨라집니다.">
            <div className="grid gap-2 sm:grid-cols-3">
              <Toggle checked={o.remove_bg} onChange={(v) => set("remove_bg", v)} label="차량 배경 제거" help="차량만 투명하게 분리" />
              <Toggle checked={o.use_background} onChange={(v) => set("use_background", v)} label="배경 이미지 사용" help={background ? undefined : "배경 이미지를 올리면 켤 수 있어요"} disabled={!background} />
              <label className={`flex items-center justify-between gap-3 rounded-2xl border border-border px-3.5 py-3 ${o.use_background ? "opacity-40" : ""}`}>
                <span className="text-sm font-bold">배경색</span>
                <input
                  type="color"
                  value={o.canvas_color}
                  disabled={o.use_background}
                  onChange={(e) => set("canvas_color", e.target.value.toUpperCase())}
                  className="h-8 w-12 cursor-pointer rounded-lg border border-border bg-transparent"
                  aria-label="배경색"
                />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <figure className="space-y-1">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {imageUrl && <img src={imageUrl} alt="원본" className="w-full rounded-2xl border border-border object-contain" />}
                <figcaption className="text-center text-[11px] text-subtle">원본</figcaption>
              </figure>
              <figure className="space-y-1">
                <div className="relative flex min-h-24 items-center justify-center overflow-hidden rounded-2xl border border-border bg-surface-muted">
                  {needsPreview ? (
                    previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={previewUrl} alt="합성 미리보기" className={`w-full object-contain transition ${previewBusy ? "opacity-40" : ""}`} />
                    ) : null
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    imageUrl && <img src={imageUrl} alt="합성 미리보기" className="w-full object-contain" />
                  )}
                  {previewBusy && (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Spinner label={o.remove_bg ? "배경을 분리하고 있어요…" : "합성 중…"} />
                    </div>
                  )}
                </div>
                <figcaption className="text-center text-[11px] text-subtle">합성 미리보기</figcaption>
              </figure>
            </div>
            <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-[11px] leading-relaxed text-muted">
              TIP · 차량이 화면 전체를 차지하는 사진이라면 배경 제거 후 &apos;달려가기&apos; 효과가 가장 자연스럽습니다. 이미 배경까지 완성된 사진이라면 배경 제거 없이 줌·패닝·바운스 조합을
              추천합니다.
            </p>
          </Section>

          <Section kicker="STEP 03 · MOTION" title="움직임을 조합해주세요" desc="여러 효과를 동시에 적용할 수 있습니다. 기본값은 차량 콘텐츠에 가장 무난한 조합입니다.">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {EFFECTS.map((e) => (
                <Toggle key={e.key} checked={o[e.key] as boolean} onChange={(v) => set(e.key, v as never)} label={e.label} help={e.help} />
              ))}
            </div>
            <p className="text-xs text-subtle">추천 조합: 차량 이미지 → 달려가기 + 바운스 / 완성 사진 → 줌 + 패닝</p>

            {o.use_drive && (
              <div className="grid gap-4 rounded-2xl bg-surface-muted p-4 sm:grid-cols-3">
                <Field label="달리는 방향">
                  <Segmented value={o.direction} options={["왼쪽 → 오른쪽", "오른쪽 → 왼쪽"] as const} onChange={(v) => set("direction", v)} full ariaLabel="달리는 방향" />
                </Field>
                <Slider label="이동 거리" value={o.travel_strength} min={5} max={35} step={5} onChange={(v) => set("travel_strength", v)} suffix="%" />
                <Slider label="원근감" value={o.perspective_strength} min={0} max={30} step={3} onChange={(v) => set("perspective_strength", v)} />
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Slider label="재생 속도" value={o.speed} min={1} max={5} step={1} onChange={(v) => set("speed", v)} />
              <Field label="반복 방식" hint="부메랑은 끝에서 역방향으로 돌아와요">
                <Segmented value={o.loop_style} options={["일반 반복", "부메랑"] as const} onChange={(v) => set("loop_style", v)} full ariaLabel="반복 방식" />
              </Field>
              <Field label="프레임 수" hint="낮을수록 빨리 만들어져요">
                <Segmented value={String(o.frame_count)} options={["12", "16", "20", "24", "30"]} onChange={(v) => set("frame_count", Number(v))} full ariaLabel="프레임 수" />
              </Field>
              <Field label="출력 폭" hint="작을수록 용량이 줄어요">
                <Segmented
                  value={String(o.max_width)}
                  options={["480", "640", "800", "960", "1200"]}
                  onChange={(v) => set("max_width", Number(v))}
                  full
                  ariaLabel="출력 폭"
                />
              </Field>
              <Slider label="밝기" value={o.brightness} min={80} max={120} step={5} onChange={(v) => set("brightness", v)} suffix="%" />
              <Slider label="대비" value={o.contrast} min={80} max={120} step={5} onChange={(v) => set("contrast", v)} suffix="%" />
            </div>

            <button
              type="button"
              onClick={generate}
              disabled={busy || !anyEffect}
              className="w-full rounded-xl bg-gradient-to-r from-accent to-violet-600 py-3 text-sm font-extrabold text-white transition hover:brightness-110 disabled:opacity-50"
            >
              {busy ? "모션을 합성하고 GIF를 만들고 있어요…" : "✨ GIF 만들기"}
            </button>
            {!anyEffect && <p className="text-center text-xs text-amber-600">효과를 최소 1개 선택해주세요.</p>}
          </Section>
        </>
      )}

      {gifUrl && meta && (
        <div ref={resultRef} className="scroll-mt-4">
          <Section kicker="RESULT" title="완성된 모션 GIF" desc="결과가 마음에 들지 않으면 위 효과를 조정하고 다시 생성해보세요.">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={gifUrl} alt="변환된 GIF" className="w-full rounded-2xl border border-border" />
            <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              {[
                ["출력 크기", `${meta.width} × ${meta.height}`],
                ["총 프레임", `${meta.frames} frame`],
                ["프레임 간격", `${meta.duration} ms`],
                ["파일 크기", `${(meta.bytes / 1024 / 1024).toFixed(2)} MB`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-surface-muted px-3 py-2">
                  <dt className="text-[11px] text-subtle">{k}</dt>
                  <dd className="font-bold">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="grid grid-cols-[2fr_1fr] gap-2">
              <a href={gifUrl} download="animated_motion.gif" className="rounded-xl bg-accent py-3 text-center text-sm font-extrabold text-white transition hover:brightness-110">
                📥 GIF 다운로드
              </a>
              <button
                type="button"
                onClick={() => {
                  setGif(null);
                  setMeta(null);
                }}
                className="rounded-xl border border-border py-3 text-sm font-bold hover:bg-surface-muted"
              >
                결과 지우기
              </button>
            </div>
          </Section>
        </div>
      )}
    </div>
  );
}
