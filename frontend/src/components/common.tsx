import { Box, Chip, LinearProgress, Paper, Stack, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import ReportIcon from "@mui/icons-material/Report";
import PowerOffIcon from "@mui/icons-material/PowerOff";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import type { ReactNode } from "react";
import { scoreColor, sevColor, statusColor, STATUS } from "../theme";

export function StatusChip({ status, size = "small" }: { status: string; size?: "small" | "medium" }) {
  const icon =
    status === "Good" ? <CheckCircleIcon /> : status === "Warning" ? <WarningAmberIcon /> : status === "Hazard" ? <ReportIcon /> : <PowerOffIcon />;
  const c = statusColor(status);
  return (
    <Chip
      size={size}
      icon={icon}
      label={status}
      variant="outlined"
      sx={{ color: c, borderColor: c, "& .MuiChip-icon": { color: c } }}
    />
  );
}

export function RuleStatusChip({ status }: { status: string }) {
  const c =
    status === "PASS" ? STATUS.good : status === "WARNING" ? STATUS.warning : status === "FAIL" ? STATUS.critical : "#8a8f98";
  const icon =
    status === "PASS" ? <CheckCircleIcon /> : status === "WARNING" ? <WarningAmberIcon /> : status === "FAIL" ? <ErrorOutlineIcon /> : <InfoOutlinedIcon />;
  return (
    <Chip size="small" icon={icon} label={status} variant="outlined"
      sx={{ color: c, borderColor: c, "& .MuiChip-icon": { color: c }, minWidth: 86 }} />
  );
}

export function SeverityChip({ severity }: { severity: string }) {
  const c = sevColor(severity);
  const icon = severity === "HIGH" ? <ReportIcon /> : severity === "MEDIUM" ? <WarningAmberIcon /> : <InfoOutlinedIcon />;
  return (
    <Chip size="small" icon={icon} label={severity} sx={{ bgcolor: c, color: "#111", "& .MuiChip-icon": { color: "#111" } }} />
  );
}

/** Wall Quality Index gauge: the score is the hero number; the ring shows it against 100. */
export function ScoreRing({ score, size = 96, label = "WQI" }: { score: number | null; size?: number; label?: string }) {
  const r = size / 2 - 7;
  const c = 2 * Math.PI * r;
  const pct = score == null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  const col = scoreColor(score);
  return (
    <Box sx={{ position: "relative", width: size, height: size, flex: "none" }} role="img" aria-label={`${label} ${score ?? "unknown"} of 100`}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeOpacity={0.12} strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={8} strokeLinecap="round"
          strokeDasharray={`${c * pct} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: "stroke-dasharray .6s ease" }} />
      </svg>
      <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
        <Box>
          <Typography sx={{ fontSize: size * 0.3, fontWeight: 800, lineHeight: 1 }}>{score ?? "–"}</Typography>
          <Typography sx={{ fontSize: Math.max(10, size * 0.11), color: "text.secondary", fontWeight: 600 }}>{label}</Typography>
        </Box>
      </Box>
    </Box>
  );
}

export function RiskBar({ risk }: { risk: number | null }) {
  const v = risk == null ? 0 : risk * 100;
  const col = v < 30 ? STATUS.good : v < 60 ? STATUS.warning : STATUS.critical;
  return (
    <Tooltip title="Estimated probability the wall fails (shifts or collapses) in transit">
      <Box>
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="caption" color="text.secondary">Collapse risk</Typography>
          <Typography variant="caption" fontWeight={700}>{risk == null ? "–" : `${Math.round(v)}%`}</Typography>
        </Stack>
        <LinearProgress variant="determinate" value={v}
          sx={{ height: 6, borderRadius: 3, bgcolor: "action.hover", "& .MuiLinearProgress-bar": { bgcolor: col, borderRadius: 3 } }} />
      </Box>
    </Tooltip>
  );
}

export function Kpi({ label, value, sub, icon }: { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ color: "text.secondary", mb: 0.5 }}>
        {icon}
        <Typography variant="overline" sx={{ lineHeight: 1.5 }}>{label}</Typography>
      </Stack>
      <Typography variant="h4">{value}</Typography>
      {sub && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{sub}</Typography>}
    </Paper>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
      <Typography variant="h6">{children}</Typography>
      {action}
    </Stack>
  );
}

export function timeAgo(iso: string | number | null | undefined) {
  if (iso == null) return "–";
  const t = typeof iso === "number" ? iso * 1000 : new Date(iso).getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export const RULE_LABEL: Record<string, string> = {
  T_STACK: "T-Stacking",
  FLUSH_FACE: "Flush face",
  LEVEL_SHELF: "Level shelves",
  VOIDS: "Voids",
  BOTTOM_HEAVY: "Heavy on bottom",
  UNSUPPORTED: "Support",
  HIGH_SEVERITY_PENALTY: "High-severity penalty",
  WALL_HEIGHT: "Wall height",
};
