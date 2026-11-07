"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { estateApi, type ZoneDetail } from "@/lib/realestate";

export type DetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: ZoneDetail }
  | { status: "error"; code: number | null; message: string };

const TTL_MS = 60_000; // 서버 캐시와 같은 길이. 오래된 상세를 오래 들고 있지 않는다.
const cache = new Map<string, { at: number; data: ZoneDetail }>();

export function describeDetailError(error: unknown): { code: number | null; message: string } {
  const status = (error as { status?: number })?.status ?? null;
  if (status === 404) return { code: 404, message: "해당 개발사업을 찾을 수 없어요." };
  if (status === 422) return { code: 422, message: "사업 번호가 올바르지 않아요." };
  if (status === 401 || status === 403) return { code: status, message: "이 정보를 볼 권한이 없어요. 로그인 상태를 확인해 주세요." };
  return { code: status, message: "개발사업 상세 정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요." };
}

/**
 * 선택한 사업의 상세(읽기 전용). 구역을 고를 때만 1건 조회한다. 같은 사업은 60초간 다시 부르지 않는다.
 * 사업을 바꾸면 이전 요청은 취소한다(늦게 온 이전 응답이 새 선택을 덮어쓰지 않게).
 */
/** 경기데이터드림 사업 번호(서버가 gg-로 시작하게 만든다). */
export const isGyeonggiId = (id: string | null | undefined) => !!id && id.startsWith("gg-");

export function useZoneDetail(projectId: string | null) {
  const [state, setState] = useState<DetailState>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const requested = useRef<string | null>(null);

  useEffect(() => {
    requested.current = projectId;
    if (!projectId) {
      setState({ status: "idle" });
      return;
    }
    const hit = cache.get(projectId);
    if (hit && Date.now() - hit.at < TTL_MS && attempt === 0) {
      setState({ status: "ready", data: hit.data });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading" });
    // 경기 사업(gg-…)은 경기 전용 상세를, 서울 사업은 기존 상세를 읽는다.
    const load = isGyeonggiId(projectId) ? estateApi.gyeonggiDetail : estateApi.developmentDetail;
    load(projectId, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted || requested.current !== projectId) return;
        cache.set(projectId, { at: Date.now(), data });
        setState({ status: "ready", data });
      })
      .catch((error) => {
        if (controller.signal.aborted || requested.current !== projectId) return;
        setState({ status: "error", ...describeDetailError(error) });
      });
    return () => controller.abort();
    // attempt: 다시 시도 버튼이 같은 사업을 강제로 다시 읽게 한다.
  }, [projectId, attempt]);

  const retry = useCallback(() => {
    if (projectId) cache.delete(projectId);
    setAttempt((n) => n + 1);
  }, [projectId]);

  return { state, retry };
}
