"use client";

import { useEffect, useRef } from "react";
import type { Map as LeafletMap } from "leaflet";
import type { DevelopmentMapPoint } from "@/lib/realestate";

const TYPE_COLOR: Record<string, string> = {
  REDEVELOPMENT: "#B42332",
  RECONSTRUCTION: "#1D4ED8",
  MOATOWN: "#0F766E",
  MOAHOUSE: "#0F766E",
  SHINTONG: "#7C3AED",
};
const SEOUL: [number, number] = [37.5512, 127.1265];

export type MapFocus = { latitude: number; longitude: number; label: string } | null;

/**
 * OpenStreetMap 타일 + Leaflet. 유료 지도 API에 의존하지 않는다.
 * Leaflet은 브라우저에서만 불러오므로 static export/SSR에서 안전하다.
 * 공식 경계가 확인된 사업만 면으로 그리고, 대표좌표는 핀으로만 표시한다.
 */
export default function ZiponMap({
  points,
  focus = null,
  height = 340,
  onSelect,
}: {
  points: DevelopmentMapPoint[];
  focus?: MapFocus;
  height?: number;
  onSelect?: (projectId: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const layer = useRef<{ clearLayers: () => void; addTo: (m: LeafletMap) => void } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      await import("leaflet/dist/leaflet.css");
      if (cancelled || !container.current || map.current) return;
      map.current = L.map(container.current, { scrollWheelZoom: false, attributionControl: true }).setView(SEOUL, 13);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors",
      }).addTo(map.current);
      layer.current = L.layerGroup().addTo(map.current);
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      layer.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      if (cancelled || !map.current || !layer.current) return;
      const group = layer.current as unknown as ReturnType<typeof L.layerGroup>;
      group.clearLayers();
      const bounds: [number, number][] = [];

      for (const point of points) {
        if (point.latitude == null || point.longitude == null) continue;
        const color = TYPE_COLOR[point.type_code ?? ""] ?? "#64748B";
        const position: [number, number] = [point.latitude, point.longitude];
        bounds.push(position);
        const marker = L.circleMarker(position, {
          radius: 7,
          color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.55,
        });
        const tags = [point.type_label, point.program_label].filter(Boolean).join(" · ");
        marker.bindPopup(
          `<strong>${point.name ?? ""}</strong><br/>${tags}<br/>${point.stage_label ?? ""}<br/><span style="color:#64748B">${point.accuracy_label}</span>`,
        );
        if (onSelect) marker.on("click", () => onSelect(point.project_id));
        marker.addTo(group);
        // 공식 경계가 확인된 사업만 면으로 그린다. 대표좌표로 면을 만들지 않는다.
        if (point.accuracy === "OFFICIAL_BOUNDARY" && point.boundary) {
          L.geoJSON(point.boundary as never, { style: { color, weight: 2, fillOpacity: 0.12 } }).addTo(group);
        }
      }

      if (focus) {
        const position: [number, number] = [focus.latitude, focus.longitude];
        bounds.push(position);
        L.marker(position).bindPopup(`<strong>${focus.label}</strong>`).addTo(group).openPopup();
        map.current.setView(position, 15);
      } else if (bounds.length > 0) {
        map.current.fitBounds(bounds, { padding: [24, 24], maxZoom: 15 });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [points, focus, onSelect]);

  const mappable = points.filter((p) => p.latitude != null && p.longitude != null).length;

  return (
    <div className="space-y-1.5">
      <div
        ref={container}
        role="application"
        aria-label="개발사업 지도"
        style={{ height }}
        className="w-full overflow-hidden rounded-2xl border border-border bg-surface-muted"
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block size-2.5 rounded-full border-2 border-estate bg-estate/50" /> 대표 위치
        </span>
        <span className="inline-flex items-center gap-1">
          <span aria-hidden className="inline-block h-2.5 w-4 border-2 border-estate bg-estate/15" /> 공식 경계 확인
        </span>
        <span>지도 미표시 = 위치 데이터 준비 중</span>
        <span className="ml-auto">
          지도 표시 {mappable}/{points.length}건
        </span>
      </div>
    </div>
  );
}
