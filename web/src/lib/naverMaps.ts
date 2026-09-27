/**
 * NAVER Maps JavaScript API v3 로더.
 *
 * 지도 Client ID는 브라우저가 SDK를 부를 때 URL에 실리므로 노출을 피할 수 없다. 보호
 * 장치는 NAVER 콘솔의 Web 서비스 URL 등록이다. Client Secret은 서버 지오코딩 전용이며
 * 이 파일에도, 번들에도 들어오지 않는다.
 *
 * 콘솔 세대에 따라 키 파라미터 이름이 ncpKeyId / ncpClientId로 갈린다. 서버가 둘 다
 * 내려주므로, 먼저 쓴 이름으로 스크립트가 로드되지 않으면 예비 이름으로 한 번만 더
 * 시도한다. 두 번 다 실패하면 조용히 빈 지도를 남기지 않고 오류를 올린다.
 */
import type { MapSdkConfig } from "./realestate";

export type NaverLatLng = { lat: () => number; lng: () => number };
export type NaverLatLngBounds = { extend: (latlng: NaverLatLng) => void };
export type NaverMapInstance = {
  setCenter: (latlng: NaverLatLng) => void;
  setZoom: (zoom: number, useEffect?: boolean) => void;
  getZoom: () => number;
  panTo: (latlng: NaverLatLng, options?: { duration?: number }) => void;
  fitBounds: (bounds: NaverLatLngBounds, options?: unknown) => void;
  getBounds: () => { getMax: () => NaverLatLng; getMin: () => NaverLatLng };
  destroy: () => void;
  setOptions: (options: Record<string, unknown>) => void;
};
export type NaverMarker = {
  setMap: (map: NaverMapInstance | null) => void;
  setIcon: (icon: unknown) => void;
  setZIndex: (index: number) => void;
  getPosition: () => NaverLatLng;
};
export type NaverInfoWindow = {
  open: (map: NaverMapInstance, anchor: NaverMarker | NaverLatLng) => void;
  close: () => void;
  setContent: (content: string) => void;
  getMap: () => NaverMapInstance | null;
};
export type NaverOverlay = { setMap: (map: NaverMapInstance | null) => void };

export type NaverMaps = {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => NaverMapInstance;
  LatLng: new (lat: number, lng: number) => NaverLatLng;
  LatLngBounds: new (sw?: NaverLatLng, ne?: NaverLatLng) => NaverLatLngBounds;
  Marker: new (options: Record<string, unknown>) => NaverMarker;
  InfoWindow: new (options: Record<string, unknown>) => NaverInfoWindow;
  Circle: new (options: Record<string, unknown>) => NaverOverlay;
  Polygon: new (options: Record<string, unknown>) => NaverOverlay;
  Point: new (x: number, y: number) => unknown;
  Size: new (width: number, height: number) => unknown;
  MapTypeId: { NORMAL: string; TERRAIN: string; SATELLITE: string; HYBRID: string };
  Position: Record<string, unknown>;
  Event: {
    addListener: (target: unknown, event: string, handler: (...args: unknown[]) => void) => unknown;
    removeListener: (listener: unknown) => void;
  };
};

declare global {
  interface Window {
    naver?: { maps?: NaverMaps };
  }
}

let pending: Promise<NaverMaps> | null = null;

function inject(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      script.remove();
      reject(new Error("NAVER_MAPS_SCRIPT_FAILED"));
    };
    document.head.appendChild(script);
  });
}

async function tryLoad(sdk: MapSdkConfig, param: string): Promise<NaverMaps> {
  await inject(`${sdk.script_url}?${param}=${encodeURIComponent(sdk.client_id ?? "")}`);
  const maps = window.naver?.maps;
  // 스크립트가 200으로 와도 키가 거부되면 naver.maps가 비어 있다.
  if (!maps) throw new Error("NAVER_MAPS_NOT_AVAILABLE");
  return maps;
}

/** SDK를 한 번만 불러온다. 이미 불러왔으면 같은 약속을 돌려준다. */
export function loadNaverMaps(sdk: MapSdkConfig | null | undefined): Promise<NaverMaps> {
  if (!sdk?.configured || !sdk.client_id) {
    return Promise.reject(new Error("NAVER_MAP_CLIENT_ID_NOT_CONFIGURED"));
  }
  if (window.naver?.maps) return Promise.resolve(window.naver.maps);
  if (pending) return pending;
  pending = tryLoad(sdk, sdk.key_param)
    .catch(() => tryLoad(sdk, sdk.key_param_fallback))
    .catch((error) => {
      pending = null;
      throw error;
    });
  return pending;
}
