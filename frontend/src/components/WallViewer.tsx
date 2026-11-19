import { Box, Chip, Stack, Tooltip } from "@mui/material";
import { useState } from "react";
import type { AnalysisResult } from "../types";
import { sevColor, STATUS } from "../theme";

export type Layer = "boxes" | "seams" | "voids" | "heatmap" | "arrows" | "markers";
const LAYERS: { key: Layer; label: string }[] = [
  { key: "boxes", label: "Packages" },
  { key: "seams", label: "Seams" },
  { key: "voids", label: "Voids" },
  { key: "heatmap", label: "Heatmap" },
  { key: "arrows", label: "Fix arrows" },
  { key: "markers", label: "Markers" },
];

/**
 * The analyzed frame with an interactive SVG overlay. Hovering an issue in the list (or a marker
 * here) highlights its region; every overlay layer can be toggled.
 */
export function WallViewer({
  src, result, highlight, onHover, showControls = true,
}: {
  src: string;
  result: AnalysisResult | null;
  highlight?: number | null;
  onHover?: (id: number | null) => void;
  showControls?: boolean;
}) {
  const [layers, setLayers] = useState<Set<Layer>>(new Set(["boxes", "seams", "voids", "arrows", "markers"]));
  const toggle = (k: Layer) =>
    setLayers((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  const W = result?.imageSize.width ?? 960;
  const H = result?.imageSize.height ?? 720;
  const pkgSev = new Map<number, string>();
  const rank: Record<string, number> = { HIGH: 3, MEDIUM: 2, LOW: 1 };
  result?.issues.forEach((i) =>
    i.packageIds.forEach((p) => {
      if ((rank[i.severity] ?? 0) > (rank[pkgSev.get(p) ?? ""] ?? 0)) pkgSev.set(p, i.severity);
    }),
  );
  const hi = result?.issues.find((i) => i.id === highlight);

  return (
    <Box>
      {showControls && (
        <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: "wrap", rowGap: 1 }}>
          {LAYERS.map((l) => (
            <Chip key={l.key} label={l.label} size="small" onClick={() => toggle(l.key)}
              color={layers.has(l.key) ? "primary" : "default"} variant={layers.has(l.key) ? "filled" : "outlined"} />
          ))}
        </Stack>
      )}
      <Box sx={{ position: "relative", width: "100%", aspectRatio: `${W} / ${H}`, bgcolor: "#000", borderRadius: 2, overflow: "hidden" }}>
        <img src={src} alt="Trailer wall" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "fill" }} />
        {result && (
          <svg viewBox={`0 0 ${W} ${H}`} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
            <defs>
              <pattern id="hatch" patternUnits="userSpaceOnUse" width="10" height="10" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="10" stroke={STATUS.critical} strokeWidth="3" />
              </pattern>
              <radialGradient id="heat">
                <stop offset="0%" stopColor={STATUS.critical} stopOpacity="0.55" />
                <stop offset="100%" stopColor={STATUS.critical} stopOpacity="0" />
              </radialGradient>
              <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 z" fill="#fff" />
              </marker>
            </defs>
            {layers.has("heatmap") &&
              result.issues.map((i) => (
                <ellipse key={`h${i.id}`} cx={i.region.x + i.region.width / 2} cy={i.region.y + i.region.height / 2}
                  rx={i.region.width * 0.9 + 40} ry={i.region.height * 0.9 + 40} fill="url(#heat)"
                  opacity={i.severity === "HIGH" ? 1 : 0.6} />
              ))}
            {layers.has("voids") &&
              result.wall.voids.map((v) => (
                <g key={`v${v.id}`}>
                  <rect x={v.bbox.x} y={v.bbox.y} width={v.bbox.width} height={v.bbox.height} fill="url(#hatch)" opacity={0.55} />
                  <rect x={v.bbox.x} y={v.bbox.y} width={v.bbox.width} height={v.bbox.height} fill="none"
                    stroke={sevColor(v.severity)} strokeWidth={2.5} />
                </g>
              ))}
            {layers.has("boxes") &&
              result.detections.map((d) => {
                const s = pkgSev.get(d.id);
                return (
                  <Tooltip key={`d${d.id}`} title={`#${d.id} ${d.class} · ${(d.confidence * 100).toFixed(0)}%${d.protrusion != null ? ` · ${d.protrusion.toFixed(1)}" out` : ""}`}>
                    <rect x={d.bbox.x} y={d.bbox.y} width={d.bbox.width} height={d.bbox.height} rx={2}
                      fill="transparent" stroke={s ? sevColor(s) : STATUS.good} strokeWidth={s ? 3 : 1.5} strokeOpacity={s ? 1 : 0.8} />
                  </Tooltip>
                );
              })}
            {layers.has("seams") &&
              result.wall.seams.filter((s) => s.layers >= 3).map((s, k) => (
                <line key={`s${k}`} x1={s.x} x2={s.x} y1={s.yTop} y2={s.yBottom} stroke={sevColor(s.layers >= 4 ? "HIGH" : "MEDIUM")}
                  strokeWidth={5} strokeDasharray="12 8" strokeLinecap="round" />
              ))}
            {layers.has("arrows") &&
              result.issues.filter((i) => i.arrow).map((i) => (
                <g key={`a${i.id}`}>
                  <line x1={i.arrow!.x1} y1={i.arrow!.y1} x2={i.arrow!.x2} y2={i.arrow!.y2} stroke="#000" strokeOpacity={0.5} strokeWidth={8} />
                  <line x1={i.arrow!.x1} y1={i.arrow!.y1} x2={i.arrow!.x2} y2={i.arrow!.y2} stroke={sevColor(i.severity)}
                    strokeWidth={4} markerEnd="url(#arrowhead)" />
                </g>
              ))}
            {hi && (
              <rect x={hi.region.x - 4} y={hi.region.y - 4} width={hi.region.width + 8} height={hi.region.height + 8} rx={6}
                fill="rgba(255,255,255,0.12)" stroke="#fff" strokeWidth={3} strokeDasharray="8 5" />
            )}
            {layers.has("markers") &&
              result.issues.map((i) => (
                <g key={`m${i.id}`} style={{ cursor: "pointer" }} onMouseEnter={() => onHover?.(i.id)} onMouseLeave={() => onHover?.(null)}>
                  <circle cx={i.marker.x} cy={i.marker.y} r={22} fill="transparent" />
                  <circle cx={i.marker.x} cy={i.marker.y} r={14} fill="#fff" stroke={sevColor(i.severity)} strokeWidth={4} />
                  <text x={i.marker.x} y={i.marker.y + 5} textAnchor="middle" fontSize={14} fontWeight={800} fill="#111">{i.id}</text>
                </g>
              ))}
          </svg>
        )}
      </Box>
    </Box>
  );
}
