"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap } from "leaflet";
import type { DevelopmentMapPoint, MapConfig } from "@/lib/realestate";

const OSM = {
  url_template: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "© OpenStreetMap contributors",
  max_zoom: 19,
};
const SEOUL: [number, number] = [37.5512, 127.1265];
/** 사업유형(DEVELOPMENT) 레이어 색. 정책 프로그램은 별도 링으로 덧그린다. */
const DEVELOPMENT_COLOR: Record<string, string> = {
  REDEVELOPMENT: "#B42332",
  RECONSTRUCTION: "#1D4ED8",
  OTHER_PROJECT: "#64748B",
};
const PROGRAM_COLOR: Record<string, string> = { FAST_TRACK: "#7C3AED", MOATOWN: "#0F766E" };

export type MapFocus = { latitude: number; longitude: number; label: string } | null;
export type MapBounds = { north: number; south: number; east: number; west: number };

/**
 * 부동산 개발정보 지도. Leaflet은 브라우저에서만 불러오므로 static export/SSR에서 안전하다.
 * 레이어를 분리한다: 선택 부동산 / 사업유형 / 정책 프로그램 / 공식 경계 / 대표위치.
 * 공식 경계가 확인된 사업만 면으로 그리고, 대표좌표로는 면을 만들지 않는다.
 */
export default function ZiponMap({
  points,
  property = null,
  config = null,
  selectedId = null,
  height = 340,
  onSelect,
  onBoundsChange,
}: {
  points: DevelopmentMapPoint[];
  property?: MapFocus;
  config?: MapConfig | null;
  selectedId?: string | null;
  height?: number;
  onSelect?: (projectId: string | null) => void;
  onBoundsChange?: (bounds: MapBounds) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const group = useRef<unknown>(null);
  const tile = config?.tile ?? OSM;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      if (cancelled || !container.current || map.current) return;
      map.current = L.map(container.current, { scrollWheelZoom: false }).setView(SEOUL, 13);
      L.tileLayer(tile.url_template ?? OSM.url_template, {
        maxZoom: tile.max_zoom ?? OSM.max_zoom,
        attribution: tile.attribution ?? OSM.attribution,
      }).addTo(map.current);
      group.current = L.layerGroup().addTo(map.current);
      if (onBoundsChange) {
        const emit = () => {
          const b = map.current?.getBounds();
          if (b) onBoundsChange({ north: b.getNorth(), south: b.getSouth(), east: b.getEast(), west: b.getWest() });
        };
        map.current.on("moveend", emit);
      }
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      group.current = null;
    };
    // 타일 설정은 최초 1회만 적용한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !map.current || !group.current) return;
      const layer = group.current as ReturnType<typeof L.layerGroup>;
      layer.clearLayers();
      const bounds: [number, number][] = [];

      for (const point of points) {
        if (point.latitude == null || point.longitude == null) continue;
        const position: [number, number] = [point.latitude, point.longitude];
        bounds.push(position);
        const color = DEVELOPMENT_COLOR[point.development_layer ?? "OTHER_PROJECT"] ?? DEVELOPMENT_COLOR.OTHER_PROJECT;
        const selected = selectedId === point.project_id;

        // BOUNDARY 레이어: 공식 경계가 확인된 사업만 면으로.
        if (point.boundary_status === "OFFICIAL_VERIFIED" && point.boundary) {
          L.geoJSON(point.boundary as never, { style: { color, weight: 2, fillOpacity: 0.12 } }).addTo(layer);
        }
        // PROGRAM 레이어: 정책 프로그램은 바깥 링으로 덧그려 유형과 구분한다.
        if (point.program_layer) {
          L.circleMarker(position, {
            radius: selected ? 14 : 11,
            color: PROGRAM_COLOR[point.program_layer] ?? "#7C3AED",
            weight: 2,
            fill: false,
            dashArray: "3 3",
          }).addTo(layer);
        }
        // POINT 레이어: 대표위치.
        const marker = L.circleMarker(position, {
          radius: selected ? 9 : 7,
          color,
          weight: selected ? 3 : 2,
          fillColor: color,
          fillOpacity: selected ? 0.85 : 0.55,
        });
        const tags = [point.type_label, point.program_label].filter(Boolean).join(" · ");
        marker.bindPopup(
          [
            `<strong>${point.name ?? ""}</strong>`,
            tags,
            point.stage_label ?? "",
            point.address ?? "",
            point.last_checked ? `최근 공식 확인 ${point.last_checked}` : "",
            `<span style="color:#64748B">${point.accuracy_label} · ${point.boundary_status_label}</span>`,
            point.official_url ? `<a href="${point.official_url}" target="_blank" rel="noopener noreferrer">공식자료 ↗</a>` : "",
          ]
            .filter(Boolean)
            .join("<br/>"),
        );
        if (onSelect) marker.on("click", () => onSelect(point.project_id));
        marker.addTo(layer);
      }

      // PROPERTY 레이어: 선택 부동산은 별도 마커로 구분한다.
      if (property) {
        const position: [number, number] = [property.latitude, property.longitude];
        bounds.push(position);
        L.circleMarker(position, {
          radius: 10,
          color: "#111827",
          weight: 3,
          fillColor: "#FFFFFF",
          fillOpacity: 1,
        })
          .bindPopup(`<strong>${property.label}</strong><br/>선택 부동산`)
          .addTo(layer)
          .openPopup();
        map.current.setView(position, 15);
      } else if (bounds.length > 0) {
        map.current.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [points, property, selectedId, onSelect]);

  const mappable = points.filter((p) => p.latitude != null && p.longitude != null).length;

  return (
    <div className="space-y-1.5">
      <div
        ref={container}
        role="application"
        aria-label="부동산 개발정보 지도"
        style={{ height }}
        className="w-full overflow-hidden rounded-2xl border border-border bg-surface-muted"
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block size-2.5 rounded-full border-2 border-slate-900 bg-white dark:border-white" /> 선택 부동산
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block h-2.5 w-4 border-2 border-estate bg-estate/15" /> 공식 사업구역
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block size-2.5 rounded-full border-2 border-estate bg-estate/50" /> 사업 대표위치
        </span>
        <span className="ml-auto">
          지도 표시 {mappable}/{points.length}건
          {mappable === 0 && points.length > 0 && " · 위치 데이터 준비 중"}
        </span>
      </div>
    </div>
  );
}
