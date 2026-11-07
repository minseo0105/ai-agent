/**
 * 집:ON 금융 입력값의 브라우저 저장 정책(서버로 보내지 않음).
 * - 저장은 사용자가 명시적으로 동의(CONSENT_KEY)했을 때만 한다.
 * - '지우기'는 아래 금융 키를 모두 지우고 동의도 해제한다.
 * - 동의 전 버전이 자동 저장한 값(zip:budget:v1, zip:sim:v1:*)은 '이전 저장값'으로 보고,
 *   사용자가 '저장 유지(동의)' 또는 '삭제'를 고를 때까지 불러오지도 새로 쓰지도 않는다.
 */
export type KV = Pick<Storage, "getItem" | "setItem" | "removeItem" | "key" | "length">;

export const CONSENT_KEY = "zip:fin-consent:v1";
export const MONEY_KEY = "zip:money:v1";
export const LEGACY_BUDGET_KEY = "zip:budget:v1";
export const SIM_PREFIX = "zip:sim:v1:";
const FIN_KEYS = [MONEY_KEY, LEGACY_BUDGET_KEY];

const store = (): KV | null => {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
};

/** 저장소에 있는 금융 입력 키 목록(동의 플래그 제외). */
export function finKeys(s: KV | null = store()): string[] {
  if (!s) return [];
  const out: string[] = [];
  try {
    for (let i = 0; i < s.length; i++) {
      const k = s.key(i);
      if (k && (FIN_KEYS.includes(k) || k.startsWith(SIM_PREFIX))) out.push(k);
    }
  } catch {
    // 접근 불가면 빈 목록
  }
  return out;
}

export function hasConsent(s: KV | null = store()): boolean {
  try {
    return s?.getItem(CONSENT_KEY) === "1";
  } catch {
    return false;
  }
}

/** 동의 없이 남아 있는 이전 버전 저장값이 있는지. */
export function hasLegacy(s: KV | null = store()): boolean {
  return !hasConsent(s) && finKeys(s).length > 0;
}

/** 동의했을 때만 읽는다. */
export function readFin<T>(key: string, s: KV | null = store()): T | null {
  if (!s || !hasConsent(s)) return null;
  try {
    const raw = s.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** 동의했을 때만 쓴다. 동의가 없으면 아무것도 저장하지 않는다. */
export function writeFin(key: string, value: unknown, s: KV | null = store()): boolean {
  if (!s || !hasConsent(s)) return false;
  try {
    s.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function setConsent(on: boolean, s: KV | null = store()): void {
  if (!s) return;
  try {
    if (on) s.setItem(CONSENT_KEY, "1");
    else clearFinancial(s);
  } catch {
    // 무시
  }
}

/** 금융 입력 키 전부와 동의 플래그를 지운다. 지운 키 수를 돌려준다. */
export function clearFinancial(s: KV | null = store()): number {
  if (!s) return 0;
  const keys = finKeys(s);
  try {
    keys.forEach((k) => s.removeItem(k));
    s.removeItem(CONSENT_KEY);
  } catch {
    // 무시
  }
  return keys.length;
}
