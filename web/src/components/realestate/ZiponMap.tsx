"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DevelopmentMapPoint, MapConfig } from "@/lib/realestate";
import { getProjectCoordinate, type ProjectCoordinate } from "@/lib/projectCoordinate";
import {
  loadNaverMaps,
  type NaverInfoWindow,
  type NaverMapInstance,
  type NaverMarker,
  type NaverMaps,
  type NaverOverlay,
} from "@/lib/naverMaps";

const SEOUL = { lat: 37.5512, lng: 127.1265 };
/** 사업유형별 marker 색. 정책 프로그램은 테두리로 구분해 유형과 섞지 않는다. */
const TYPE_COLOR: Record<string, string> = {
  REDEVELOPMENT: "#B42332",
  RECONSTRUCTION: "#1D4ED8",
  MOATOWN: "#0F766E",
  OTHER_PROJECT: "#64748B",
};
const PROGRAM_RING: Record<string, string> = { FAST_TRACK: "#7C3AED", MOATOWN: "#0F766E" };
const LEGEND: { label: string; color: string; ring?: string }[] = [
  { label: "재개발", color: TYPE_COLOR.REDEVELOPMENT },
  { label: "재건축", color: TYPE_COLOR.RECONSTRUCTION },
  { label: "모아타운", color: TYPE_COLOR.MOATOWN },
  { label: "신속통합기획", color: TYPE_COLOR.OTHER_PROJECT, ring: PROGRAM_RING.FAST_TRACK },
];

export type MapFocus = { latitude: number; longitude: number; label: string } | null;
export type MapBounds = { north: number; south: number; east: number; west: number };

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

/** marker 하나. 선택된 것은 크기와 흰 테두리로 확실히 구분하고, 지도를 가릴 만큼 키우지 않는다. */
function markerIcon(maps: NaverMaps, point: DevelopmentMapPoint, selected: boolean) {
  const color = TYPE_COLOR[point.development_layer ?? "OTHER_PROJECT"] ?? TYPE_COLOR.OTHER_PROJECT;
  const ring = point.program_layer ? PROGRAM_RING[point.program_layer] ?? PROGRAM_RING.FAST_TRACK : null;
  const size = selected ? 26 : 16;
  const border = ring ?? "#FFFFFF";
  const width = selected ? 4 : ring ? 3 : 2;
  return {
    content:
      `<div style="width:${size}px;height:${size}px;border-radius:9999px;background:${color};` +
      `border:${width}px solid ${border};box-sizing:border-box;` +
      `box-shadow:0 1px 3px rgba(0,0,0,.35)${selected ? ",0 0 0 3px rgba(180,35,50,.35)" : ""};"></div>`,
    size: new maps.Size(size, size),
    anchor: new maps.Point(size / 2, size / 2),
  };
}

function infoHtml(point: DevelopmentMapPoint) {
  const tags = [point.type_label, point.program_label].filter(Boolean).join(" · ");
  const rows = [
    `<div style="font-weight:800;font-size:13px">${escapeHtml(point.name ?? "")}</div>`,
    tags ? `<div style="color:#475569;font-size:12px">${escapeHtml(tags)}</div>` : "",
    point.stage_label ? `<div style="font-size:12px">${escapeHtml(point.stage_label)}</div>` : "",
    point.address ? `<div style="color:#64748B;font-size:11px">${escapeHtml(point.address)}</div>` : "",
    `<div style="color:#94A3B8;font-size:11px">${escapeHtml(point.accuracy_label)} · ${escapeHtml(
      point.boundary_status_label,
    )}</div>`,
  ];
  return `<div style="padding:10px 12px;max-width:240px;line-height:1.5">${rows.filter(Boolean).join("")}</div>`;
}

/**
 * ZIP:ON 개발정보 지도. NAVER Maps JavaScript API v3 Dynamic Map을 쓴다.
 *
 * 대표좌표는 대표좌표로만 그린다: 선택 사업 주변에 옅은 원을 둘 수 있지만 그것은
 * '대표위치 주변'이며 사업구역 경계가 아니다. 면은 공식 경계가 확인된 사업만 Polygon으로
 * 그리고, 오늘은 그런 사업이 없으므로 아무 면도 그려지지 않는다. INSIDE 판정은 하지 않는다.
 */
export default function ZiponMap({
  points,
  property = null,
  config = null,
  selectedId = null,
  height = 340,
  compact = false,
  onSelect,
  onBoundsChange,
}: {
  points: DevelopmentMapPoint[];
  property?: MapFocus;
  config?: MapConfig | null;
  selectedId?: string | null;
  height?: number;
  /** mini-map 모드: 범례와 범위 통지 없이 선택 사업만 보여준다. */
  compact?: boolean;
  onSelect?: (projectId: string | null) => void;
  onBoundsChange?: (bounds: MapBounds) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const markers = useRef<Map<string, NaverMarker>>(new Map());
  const overlays = useRef<NaverOverlay[]>([]);
  const circle = useRef<NaverOverlay | null>(null);
  const info = useRef<NaverInfoWindow | null>(null);
  const listeners = useRef<unknown[]>([]);
  const select = useRef(onSelect);
  const bounds = useRef(onBoundsChange);
  // 지도 인스턴스는 SDK가 로드된 뒤에 생긴다. ref에 담으면 렌더가 다시 일어나지 않아
  // marker/center 효과가 '아직 지도 없음'으로 한 번 빠져나간 뒤 영영 다시 돌지 않는다.
  // 그래서 상태로 들고 있는다. 이것이 상세 지도에 위치가 찍히지 않던 원인이다.
  const [api, setApi] = useState<NaverMaps | null>(null);
  const [instance, setInstance] = useState<NaverMapInstance | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const sdk = config?.sdk ?? null;

  select.current = onSelect;
  bounds.current = onBoundsChange;

  /** 좌표는 공통 helper로만 읽는다. 메인 지도와 상세 지도가 같은 값을 쓴다. */
  const located = useMemo(
    () =>
      points
        .map((point) => ({ point, coordinate: getProjectCoordinate(point) }))
        .filter((entry): entry is { point: DevelopmentMapPoint; coordinate: ProjectCoordinate } =>
          entry.coordinate !== null,
        ),
    [points],
  );
  const selectedEntry = useMemo(
    () => located.find((entry) => entry.point.project_id === selectedId) ?? null,
    [located, selectedId],
  );

  useEffect(() => {
    if (!sdk) return;
    let cancelled = false;
    let created: NaverMapInstance | null = null;
    loadNaverMaps(sdk)
      .then((loaded) => {
        if (cancelled || !container.current) return;
        created = new loaded.Map(container.current, {
          center: new loaded.LatLng(SEOUL.lat, SEOUL.lng),
          zoom: compact ? 16 : 12,
          mapTypeId: loaded.MapTypeId.NORMAL,
          scaleControl: false,
          logoControl: true,
          mapDataControl: false,
          zoomControl: !compact,
          scrollWheel: !compact,
        });
        info.current = new loaded.InfoWindow({ content: "", borderWidth: 0, disableAnchor: true });
        if (!compact && bounds.current) {
          listeners.current.push(
            loaded.Event.addListener(created, "idle", () => {
              const box = created?.getBounds();
              if (!box) return;
              const max = box.getMax();
              const min = box.getMin();
              bounds.current?.({ north: max.lat(), south: min.lat(), east: max.lng(), west: min.lng() });
            }),
          );
        }
        setApi(loaded);
        setInstance(created);
        setFailed(null);
      })
      .catch((error: Error) => {
        if (!cancelled) setFailed(error.message);
      });
    return () => {
      cancelled = true;
      for (const listener of listeners.current) window.naver?.maps?.Event.removeListener(listener);
      listeners.current = [];
      info.current?.close();
      info.current = null;
      for (const marker of markers.current.values()) marker.setMap(null);
      markers.current.clear();
      for (const overlay of overlays.current) overlay.setMap(null);
      overlays.current = [];
      circle.current?.setMap(null);
      circle.current = null;
      created?.destroy();
      setInstance(null);
    };
    // 지도 인스턴스는 한 번만 만든다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sdk, compact]);

  // marker 갱신. 좌표가 없는 사업은 marker를 만들지 않는다(가짜 좌표 금지).
  // 이미 있는 marker는 지우고 다시 만들지 않고 위치와 아이콘만 바꾼다.
  useEffect(() => {
    if (!api || !instance) return;
    const wanted = new Set(located.map((entry) => entry.point.project_id));
    for (const [projectId, marker] of markers.current) {
      if (!wanted.has(projectId)) {
        marker.setMap(null);
        markers.current.delete(projectId);
      }
    }
    for (const overlay of overlays.current) overlay.setMap(null);
    overlays.current = [];

    for (const { point, coordinate } of located) {
      // NAVER SDK는 (위도, 경도) 순서다. API는 longitude/latitude로 준다.
      const position = new api.LatLng(coordinate.lat, coordinate.lng);
      // 공식 경계가 확인된 사업만 면으로. 오늘은 해당 사업이 없어 아무 면도 그리지 않는다.
      if (point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary) {
        const paths = point.boundary as { coordinates?: number[][][] };
        const ring = paths.coordinates?.[0];
        if (ring) {
          overlays.current.push(
            new api.Polygon({
              map: instance,
              paths: [ring.map(([lng, lat]) => new api.LatLng(lat, lng))],
              strokeColor: TYPE_COLOR[point.development_layer ?? "OTHER_PROJECT"],
              strokeWeight: 2,
              fillColor: TYPE_COLOR[point.development_layer ?? "OTHER_PROJECT"],
              fillOpacity: 0.12,
            }),
          );
        }
      }
      const selected = selectedId === point.project_id;
      const existing = markers.current.get(point.project_id);
      if (existing) {
        existing.setPosition(position);
        existing.setIcon(markerIcon(api, point, selected));
        existing.setZIndex(selected ? 1000 : 1);
        existing.setMap(instance);
        continue;
      }
      const marker = new api.Marker({
        map: instance,
        position,
        title: point.name ?? undefined,
        icon: markerIcon(api, point, selected),
        zIndex: selected ? 1000 : 1,
      });
      if (select.current) {
        listeners.current.push(
          api.Event.addListener(marker, "click", () => select.current?.(point.project_id)),
        );
      }
      markers.current.set(point.project_id, marker);
    }

    if (property) {
      overlays.current.push(
        new api.Marker({
          map: instance,
          position: new api.LatLng(property.latitude, property.longitude),
          icon: {
            content:
              '<div style="width:18px;height:18px;border-radius:9999px;background:#FFFFFF;' +
              'border:3px solid #111827;box-sizing:border-box"></div>',
            size: new api.Size(18, 18),
            anchor: new api.Point(9, 9),
          },
          zIndex: 1200,
        }) as unknown as NaverOverlay,
      );
    }
  }, [api, instance, located, property, selectedId]);

  // 선택 사업으로 지도를 옮기고 InfoWindow를 띄운다. 화면을 강제로 스크롤하지 않는다.
  useEffect(() => {
    if (!api || !instance) return;
    circle.current?.setMap(null);
    circle.current = null;
    if (!selectedEntry) {
      info.current?.close();
      if (!compact && !property && located.length > 0) {
        const box = new api.LatLngBounds();
        for (const entry of located) box.extend(new api.LatLng(entry.coordinate.lat, entry.coordinate.lng));
        instance.fitBounds(box, { top: 24, right: 24, bottom: 24, left: 24 });
      }
      return;
    }
    const { point, coordinate } = selectedEntry;
    const position = new api.LatLng(coordinate.lat, coordinate.lng);
    // 접혀 있던 영역에서 만들어진 지도는 크기가 0이라 중심이 어긋난다. 크기가 확정된
    // 다음 프레임에 resize를 알리고 다시 중심을 잡는다.
    const settle = () => {
      api.Event.trigger(instance, "resize");
      if (compact) {
        instance.setCenter(position);
        instance.setZoom(17, false);
      } else {
        instance.panTo(position, { duration: 320 });
        if (instance.getZoom() < 15) instance.setZoom(15, true);
      }
    };
    settle();
    const frame = window.requestAnimationFrame(settle);
    // 선택 사업 주변 표시. '대표위치 주변'이며 사업구역 경계가 아니다.
    circle.current = new api.Circle({
      map: instance,
      center: position,
      radius: 120,
      strokeColor: TYPE_COLOR[point.development_layer ?? "OTHER_PROJECT"],
      strokeWeight: 1,
      strokeOpacity: 0.7,
      fillColor: TYPE_COLOR[point.development_layer ?? "OTHER_PROJECT"],
      fillOpacity: 0.08,
    });
    const marker = markers.current.get(point.project_id);
    if (info.current && marker) {
      info.current.setContent(infoHtml(point));
      info.current.open(instance, marker);
    }
    return () => window.cancelAnimationFrame(frame);
  }, [api, instance, selectedEntry, located, compact, property]);

  const mappable = located.length;

  if (!sdk?.configured || failed) {
    return (
      <div
        style={{ height }}
        className="flex w-full items-center justify-center rounded-2xl border border-border bg-surface-muted px-4 text-center text-xs text-muted"
      >
        지도를 불러오지 못했어요. 네이버 지도 설정을 확인해 주세요.
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div
        ref={container}
        role="application"
        aria-label={compact ? "선택 사업 위치 지도" : "부동산 개발정보 지도"}
        style={{ height }}
        className="w-full overflow-hidden rounded-2xl border border-border bg-surface-muted"
      />
      {!compact && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
          {LEGEND.map((item) => (
            <span key={item.label} className="inline-flex items-center gap-1">
              <span
                aria-hidden
                className="inline-block size-2.5 rounded-full"
                style={{
                  background: item.color,
                  border: `2px solid ${item.ring ?? "#FFFFFF"}`,
                  boxSizing: "border-box",
                }}
              />
              {item.label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1">
            <span
              aria-hidden
              className="inline-block size-2.5 rounded-full border-2 border-slate-900 bg-white dark:border-white"
            />
            선택 부동산
          </span>
          <span className="ml-auto">
            지도 표시 {mappable}/{points.length}건
            {points.length > mappable && ` · 좌표 없는 ${points.length - mappable}건은 목록에만 표시`}
          </span>
        </div>
      )}
    </div>
  );
}
