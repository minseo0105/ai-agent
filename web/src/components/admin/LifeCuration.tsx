"use client";

import { useCallback, useEffect, useState } from "react";
import { inputClass } from "@/components/golf/ui";
import { stockAdminApi, type Curation, type CurationItem } from "@/lib/stock";

const SOURCE_LABEL: Record<CurationItem["source"], string> = { topic: "오늘 이슈", reserve: "다음 후보", sector: "섹터 이슈", example: "예시(다른 날)" };

/** 뉴스 속 숨은 종목 시연 안전장치: 이슈 숨기기·다시 보이기, 첫 화면 순서, 제외 키워드, 금융회사 사고 이슈 첫 카드 제외. */
export default function LifeCuration() {
  const [data, setData] = useState<Curation | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [words, setWords] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const apply = useCallback((d: Curation) => {
    setData(d);
    setOrder(d.items.filter((i) => i.position).sort((a, b) => a.position! - b.position!).map((i) => i.key));
    setWords(d.words.join(", "));
  }, []);

  const load = useCallback(() => stockAdminApi.curation().then(apply).catch((e) => setMsg((e as Error).message)), [apply]);
  useEffect(() => { load(); }, [load]);

  async function send(body: Parameters<typeof stockAdminApi.setCuration>[0], done: string) {
    setBusy(true);
    setMsg("");
    try {
      apply(await stockAdminApi.setCuration(body));
      setMsg(done);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <p className="text-xs text-muted">{msg || "이슈 목록을 불러오는 중…"}</p>;

  const byKey = Object.fromEntries(data.items.map((i) => [i.key, i]));
  const shownNow = data.items.filter((i) => i.position).sort((a, b) => a.position! - b.position!).map((i) => i.key);
  const dirty = JSON.stringify(order) !== JSON.stringify(shownNow);
  const move = (i: number, d: number) => setOrder((o) => { const n = [...o]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); return n; });
  const waiting = data.items.filter((i) => !i.position && !i.hidden && !i.excluded_by);
  const blocked = data.items.filter((i) => i.hidden || i.excluded_by);
  const parsedWords = words.split(/[,\n]/).map((w) => w.trim()).filter(Boolean);
  const wordsDirty = JSON.stringify(parsedWords) !== JSON.stringify(data.words);

  const row = (it: CurationItem, right: React.ReactNode, lead?: React.ReactNode) => (
    <li key={it.key} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm">
      {lead}
      <div className="min-w-0 flex-1">
        <div className="font-bold">
          {it.name} <span className="text-xs font-normal text-subtle">{SOURCE_LABEL[it.source]}{it.sector ? ` · ${it.sector}` : ""}</span>
          {it.fin_incident && <span className="ml-1.5 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[11px] font-extrabold text-amber-800 dark:text-amber-300">금융 사고·제재</span>}
          {it.excluded_by && <span className="ml-1.5 rounded-full bg-red-500/15 px-1.5 py-0.5 text-[11px] font-extrabold text-red-700 dark:text-red-300">제외 키워드 &lsquo;{it.excluded_by}&rsquo;</span>}
        </div>
        <div className="truncate text-xs text-muted">{it.title}{it.rep_title && <> · 대표 기사 <a href={it.rep_url} target="_blank" rel="noreferrer" className="underline">{it.rep_title}</a> ({it.rep_press})</>}</div>
      </div>
      {right}
    </li>
  );

  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-1.5 text-sm font-extrabold">첫 화면에 보이는 이슈 ({order.length}개 · {data.day}) </h3>
        <p className="mb-2 text-xs text-muted">위에서부터 카드 순서예요. 순서는 오늘만 적용되고 날짜가 바뀌면 처음 순서로 돌아가요. 숨기면 다음 후보로 채워 {data.min}개 이상을 유지해요.</p>
        <ol className="space-y-1.5">
          {order.map((k, i) => byKey[k] && row(byKey[k], (
            <>
              <button type="button" aria-label={`${byKey[k].name} 위로`} disabled={i === 0 || busy} onClick={() => move(i, -1)} className="px-1.5 text-muted disabled:opacity-30">▲</button>
              <button type="button" aria-label={`${byKey[k].name} 아래로`} disabled={i === order.length - 1 || busy} onClick={() => move(i, 1)} className="px-1.5 text-muted disabled:opacity-30">▼</button>
              <button type="button" disabled={busy} onClick={() => send({ action: "hide", key: k }, `'${byKey[k].name}'을(를) 숨겼어요.`)} className="rounded-lg border border-border px-2 py-1 text-xs font-bold text-red-600">숨기기</button>
            </>
          ), <span className="w-5 text-xs font-bold text-subtle">{i + 1}</span>))}
        </ol>
        <div className="mt-2 flex flex-wrap justify-end gap-2">
          {data.order.length > 0 && <button type="button" disabled={busy} onClick={() => send({ action: "order", keys: [] }, "처음 순서로 돌렸어요.")} className="rounded-xl px-3 py-2 text-xs font-bold text-muted">처음 순서로</button>}
          {dirty && <button type="button" onClick={() => setOrder(shownNow)} className="rounded-xl px-3 py-2 text-xs font-bold text-muted">되돌리기</button>}
          <button type="button" disabled={!dirty || busy} onClick={() => send({ action: "order", keys: order }, "오늘 순서를 저장했어요.")} className="rounded-xl bg-accent px-4 py-2 text-xs font-extrabold text-white disabled:opacity-40">순서 저장</button>
        </div>
      </div>

      {waiting.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-sm font-extrabold">대기 중인 후보</h3>
          <ul className="space-y-1.5">
            {waiting.map((it) => row(it, (
              <>
                <button type="button" disabled={busy} onClick={() => send({ action: "order", keys: [it.key, ...shownNow] }, `'${it.name}'을(를) 첫 카드로 올렸어요.`)} className="rounded-lg border border-border px-2 py-1 text-xs font-bold">첫 카드로</button>
                <button type="button" disabled={busy} onClick={() => send({ action: "hide", key: it.key }, `'${it.name}'을(를) 숨겼어요.`)} className="rounded-lg border border-border px-2 py-1 text-xs font-bold text-red-600">숨기기</button>
              </>
            )))}
          </ul>
        </div>
      )}

      {(blocked.length > 0 || data.hidden_other.length > 0) && (
        <div>
          <h3 className="mb-1.5 text-sm font-extrabold">숨긴 이슈</h3>
          <ul className="space-y-1.5">
            {blocked.map((it) => row(it, it.hidden ? (
              <button type="button" disabled={busy} onClick={() => send({ action: "show", key: it.key }, `'${it.name}'을(를) 다시 보이게 했어요.`)} className="rounded-lg border border-border px-2 py-1 text-xs font-bold">다시 보이기</button>
            ) : <span className="text-xs text-muted">키워드를 지우면 보여요</span>))}
            {data.hidden_other.map((h) => (
              <li key={h.key} className="flex items-center gap-2 rounded-xl border border-dashed border-border px-3 py-2 text-sm text-muted">
                <span className="flex-1">{h.name} <span className="text-xs">· 지금 후보에 없음(이름이 같은 이슈가 다시 나와도 숨겨요)</span></span>
                <button type="button" disabled={busy} onClick={() => send({ action: "show", key: h.key }, `'${h.name}' 숨김을 풀었어요.`)} className="rounded-lg border border-border px-2 py-1 text-xs font-bold">숨김 풀기</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-1.5 text-sm font-extrabold">제외 키워드</h3>
        <p className="mb-2 text-xs text-muted">쉼표로 나눠 적어요(예: 은행 이름, 회사명). 이슈 이름·제목·대표 기사 제목에 들어 있으면 자동으로 숨겨요(섹터 이슈도). 띄어쓰기·대소문자는 무시해요.</p>
        <textarea value={words} onChange={(e) => setWords(e.target.value)} rows={2} className={inputClass} aria-label="제외 키워드" placeholder="예: OO은행, OO카드" />
        <div className="mt-2 flex justify-end">
          <button type="button" disabled={!wordsDirty || busy} onClick={() => send({ action: "words", words: parsedWords }, "제외 키워드를 저장했어요.")} className="rounded-xl bg-accent px-4 py-2 text-xs font-extrabold text-white disabled:opacity-40">키워드 저장</button>
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={data.fin_first} disabled={busy} onChange={(e) => send({ action: "fin_first", on: e.target.checked }, e.target.checked ? "금융회사 사고 이슈를 첫 카드에서 뺐어요." : "금융회사 사고 이슈도 첫 카드에 올 수 있어요.")} className="mt-1" />
        <span><b>국내 금융회사(은행·카드·보험·증권) 사고·제재·유출 이슈는 첫 카드에 두지 않기</b><span className="block text-xs text-muted">기본 켜짐. 다른 카드로는 보여요. 관리자가 직접 첫 카드로 정하면 그 순서를 따라요.</span></span>
      </label>

      {msg && <p className="text-xs text-muted" role="status">{msg}</p>}
    </div>
  );
}
