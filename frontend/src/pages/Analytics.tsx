import {
  Box, Button, Chip, Grid2 as Grid, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, ToggleButton,
  ToggleButtonGroup, Typography,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useLive } from "../live";
import { Kpi, RULE_LABEL, SectionTitle } from "../components/common";
import { CountBars, GradeStack, ScoreLine } from "../components/Charts";
import { scoreColor } from "../theme";

interface Daily {
  date: string; walls: number; avgScore: number | null; avgRisk: number; hazardousWalls: number; excellentWalls: number;
  alerts: number; ruleScores: Record<string, number>; issues: Record<string, number>;
}
interface ShiftRow {
  date: string; shift: string; walls: number; avgScore: number | null; minScore: number; avgRisk: number; hazardousWalls: number;
  alerts: number; handlers: string[]; topIssue: string | null;
}
interface TrailerRow {
  trailerId: string; door: number; walls: number; avgScore: number | null; bestScore: number | null; worstScore: number | null;
  avgRisk: number | null; hazardRate: number | null; alerts: number; topIssues: { name: string; count: number }[];
}
interface HandlerRow {
  handlerId: number; name: string; badge: string; walls7d: number; avgScore7d: number | null; avgScorePrev7d: number | null;
  improvement: number | null; weekly: { week: string; avgScore: number | null; walls: number }[]; focusArea: string | null;
  avgAckSeconds: number | null;
}
interface Weekly {
  weekStart: string; weekEnd: string; walls: number; avgScore: number | null; avgScorePrevWeek: number | null; hazardousWalls: number;
  excellentWalls: number; alerts: number; alertAckRate: number | null; avgAckSeconds: number | null; highlights: string[];
  topIssues: { name: string; count: number }[];
}

const ISSUE_NAMES: Record<string, string> = {
  VERTICAL_SEAM: "Vertical seams", PROTRUSION: "Protruding packages", SHELF_SLOPE: "Uneven shelves", VOID_CAVITY: "Voids",
  VOID_GAP: "Chimney gaps", HEAVY_HIGH: "Heavy freight high", FLOATING: "Unsupported", OVERHANG: "Overhangs", LEANING: "Leaning",
};
const RULES = ["T_STACK", "UNSUPPORTED", "VOIDS", "LEVEL_SHELF", "BOTTOM_HEAVY", "FLUSH_FACE"];

function Score({ v }: { v: number | null }) {
  return <Typography component="span" fontWeight={700} sx={{ borderBottom: `3px solid ${scoreColor(v)}` }}>{v ?? "–"}</Typography>;
}

export default function Analytics() {
  const { trailers } = useLive();
  const [days, setDays] = useState(21);
  const [trailer, setTrailer] = useState("");
  const [daily, setDaily] = useState<Daily[]>([]);
  const [shifts, setShifts] = useState<ShiftRow[]>([]);
  const [tm, setTm] = useState<TrailerRow[]>([]);
  const [hm, setHm] = useState<HandlerRow[]>([]);
  const [weekly, setWeekly] = useState<Weekly | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);

  useEffect(() => {
    api.get<{ daily: Daily[] }>(`/api/analytics/trends?days=${days}${trailer ? `&trailer_id=${trailer}` : ""}`).then((r) => setDaily(r.daily));
  }, [days, trailer]);
  useEffect(() => {
    api.get<{ rows: ShiftRow[] }>("/api/analytics/shifts?days=7").then((r) => setShifts(r.rows));
    api.get<{ trailers: TrailerRow[] }>(`/api/analytics/trailers?days=${days}`).then((r) => setTm(r.trailers));
    api.get<{ handlers: HandlerRow[] }>("/api/analytics/handlers").then((r) => setHm(r.handlers));
  }, [days]);
  useEffect(() => void api.get<Weekly>(`/api/reports/weekly?week_offset=${weekOffset}`).then(setWeekly), [weekOffset]);

  const lineData = useMemo(() => daily.map((d) => ({
    label: d.date.slice(5), score: d.avgScore,
    ...Object.fromEntries(RULES.map((r) => [r, d.ruleScores[r] != null ? Math.round(d.ruleScores[r] * 100) : null])),
  })), [daily]);
  const stackData = daily.map((d) => ({
    label: d.date.slice(5), hazardous: d.hazardousWalls, excellent: d.excellentWalls, ok: d.walls - d.hazardousWalls - d.excellentWalls,
  }));
  const issueTotals = useMemo(() => {
    const c: Record<string, number> = {};
    daily.forEach((d) => Object.entries(d.issues).forEach(([k, v]) => (c[k] = (c[k] ?? 0) + v)));
    return Object.entries(c).map(([k, v]) => ({ name: ISSUE_NAMES[k] ?? k, value: v })).sort((a, b) => b.value - a.value);
  }, [daily]);

  return (
    <Stack spacing={2.5}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h4">Analytics & reporting</Typography>
          <Typography color="text.secondary">Completed-wall quality over time, by shift, trailer and handler.</Typography>
        </Box>
        <ToggleButtonGroup size="small" exclusive value={days} onChange={(_, v) => v && setDays(v)}>
          <ToggleButton value={7}>7 days</ToggleButton><ToggleButton value={14}>14 days</ToggleButton><ToggleButton value={21}>21 days</ToggleButton>
        </ToggleButtonGroup>
        <TextField select size="small" label="Trailer" value={trailer} onChange={(e) => setTrailer(e.target.value)} sx={{ minWidth: 150 }}>
          <MenuItem value="">All trailers</MenuItem>
          {Object.keys(trailers).map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
        </TextField>
      </Stack>

      {weekly && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <SectionTitle action={
            <Stack direction="row" spacing={1}>
              <TextField select size="small" value={weekOffset} onChange={(e) => setWeekOffset(Number(e.target.value))}>
                <MenuItem value={0}>This week</MenuItem><MenuItem value={1}>Last week</MenuItem><MenuItem value={2}>2 weeks ago</MenuItem>
              </TextField>
              <Button size="small" variant="outlined" startIcon={<DownloadIcon />} href={`/api/reports/weekly?week_offset=${weekOffset}&format=csv`}>CSV</Button>
            </Stack>}>
            Weekly report · {new Date(weekly.weekStart).toLocaleDateString()} – {new Date(weekly.weekEnd).toLocaleDateString()}
          </SectionTitle>
          <Grid container spacing={2}>
            <Grid size={{ xs: 6, md: 3 }}><Kpi label="Walls" value={weekly.walls} sub={`${weekly.excellentWalls} excellent · ${weekly.hazardousWalls} hazardous`} /></Grid>
            <Grid size={{ xs: 6, md: 3 }}><Kpi label="Avg WQI" value={weekly.avgScore ?? "–"}
              sub={weekly.avgScorePrevWeek != null && weekly.avgScore != null ? `${weekly.avgScore >= weekly.avgScorePrevWeek ? "▲" : "▼"} ${Math.abs(weekly.avgScore - weekly.avgScorePrevWeek).toFixed(1)} vs prior week` : "–"} /></Grid>
            <Grid size={{ xs: 6, md: 3 }}><Kpi label="Alerts" value={weekly.alerts} sub={weekly.alertAckRate != null ? `${Math.round(weekly.alertAckRate * 100)}% acknowledged` : "–"} /></Grid>
            <Grid size={{ xs: 6, md: 3 }}><Kpi label="Avg time to ack" value={weekly.avgAckSeconds != null ? `${Math.round(weekly.avgAckSeconds / 6) / 10}m` : "–"} sub="alert → handler response" /></Grid>
          </Grid>
          <Box component="ul" sx={{ mb: 0, pl: 2.5 }}>
            {weekly.highlights.map((h) => <li key={h}><Typography variant="body2">{h}</Typography></li>)}
          </Box>
        </Paper>
      )}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SectionTitle>Average wall score per day</SectionTitle>
            <ScoreLine data={lineData} xKey="label" series={[{ key: "score", name: "Avg WQI" }]} />
            <Typography variant="caption" color="text.secondary">Dashed lines: 75 (Good) and 50 (Hazardous) thresholds.</Typography>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SectionTitle>Walls per day by grade</SectionTitle>
            <GradeStack data={stackData} height={258} />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SectionTitle>Practice scores per day (rule score × 100)</SectionTitle>
            <ScoreLine data={lineData} xKey="label" series={RULES.map((r) => ({ key: r, name: RULE_LABEL[r] }))} height={280} />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SectionTitle>Most frequent defects</SectionTitle>
            <CountBars data={issueTotals.slice(0, 9)} height={280} />
          </Paper>
        </Grid>
      </Grid>

      <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
        <SectionTitle>Handler improvement</SectionTitle>
        <Table size="small">
          <TableHead>
            <TableRow><TableCell>Handler</TableCell><TableCell>Walls (7d)</TableCell><TableCell>Avg WQI 7d</TableCell><TableCell>Prior 7d</TableCell>
              <TableCell>Change</TableCell><TableCell>Last 4 weeks</TableCell><TableCell>Coaching focus</TableCell><TableCell>Avg ack</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {hm.map((h) => (
              <TableRow key={h.handlerId}>
                <TableCell><b>{h.name}</b> <Typography variant="caption" color="text.secondary">{h.badge}</Typography></TableCell>
                <TableCell>{h.walls7d}</TableCell>
                <TableCell><Score v={h.avgScore7d} /></TableCell>
                <TableCell>{h.avgScorePrev7d ?? "–"}</TableCell>
                <TableCell>
                  {h.improvement == null ? "–" : (
                    <Chip size="small" variant="outlined" label={`${h.improvement >= 0 ? "▲" : "▼"} ${Math.abs(h.improvement).toFixed(1)}`}
                      color={h.improvement > 2 ? "success" : h.improvement < -2 ? "error" : "default"} />
                  )}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{h.weekly.map((w) => w.avgScore ?? "–").join(" → ")}</TableCell>
                <TableCell>{h.focusArea ?? "–"}</TableCell>
                <TableCell>{h.avgAckSeconds != null ? `${Math.round(h.avgAckSeconds)}s` : "–"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
            <SectionTitle>Trailer performance ({days}d)</SectionTitle>
            <Table size="small">
              <TableHead><TableRow><TableCell>Trailer</TableCell><TableCell>Walls</TableCell><TableCell>Avg</TableCell><TableCell>Worst</TableCell>
                <TableCell>Hazard rate</TableCell><TableCell>Alerts</TableCell><TableCell>Top issue</TableCell></TableRow></TableHead>
              <TableBody>
                {tm.map((t) => (
                  <TableRow key={t.trailerId}>
                    <TableCell><b>{t.trailerId}</b></TableCell><TableCell>{t.walls}</TableCell><TableCell><Score v={t.avgScore} /></TableCell>
                    <TableCell>{t.worstScore ?? "–"}</TableCell>
                    <TableCell>{t.hazardRate != null ? `${Math.round(t.hazardRate * 100)}%` : "–"}</TableCell>
                    <TableCell>{t.alerts}</TableCell><TableCell>{t.topIssues[0]?.name ?? "–"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, overflowX: "auto", maxHeight: 460 }}>
            <SectionTitle>Shift report (7d)</SectionTitle>
            <Table size="small" stickyHeader>
              <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Shift</TableCell><TableCell>Walls</TableCell><TableCell>Avg</TableCell>
                <TableCell>Min</TableCell><TableCell>Hazardous</TableCell><TableCell>Alerts</TableCell><TableCell>Top issue</TableCell></TableRow></TableHead>
              <TableBody>
                {shifts.map((s) => (
                  <TableRow key={`${s.date}${s.shift}`}>
                    <TableCell>{s.date}</TableCell><TableCell>{s.shift}</TableCell><TableCell>{s.walls}</TableCell>
                    <TableCell><Score v={s.avgScore} /></TableCell><TableCell>{s.minScore}</TableCell><TableCell>{s.hazardousWalls}</TableCell>
                    <TableCell>{s.alerts}</TableCell><TableCell>{s.topIssue ?? "–"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </Grid>
      </Grid>
    </Stack>
  );
}
