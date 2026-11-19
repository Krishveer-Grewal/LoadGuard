import {
  Alert as MuiAlert, Box, Button, Chip, Grid2 as Grid, Paper, Stack, Tab, Table, TableBody, TableCell, TableHead, TableRow, Tabs, Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PhoneAndroidIcon from "@mui/icons-material/PhoneAndroid";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, frameUrl, streamUrl } from "../api";
import { useInterval, useLive } from "../live";
import { RiskBar, ScoreRing, SectionTitle, SeverityChip, StatusChip, timeAgo } from "../components/common";
import { WallViewer } from "../components/WallViewer";
import { IssueList, RuleTable, ScoreBreakdown } from "../components/Explain";
import { RiskLine, ScoreLine } from "../components/Charts";
import type { Alert, AnalysisResult, TrailerSummary } from "../types";

interface WallRow {
  id: number; timestamp: string; shift: string; wallSeq: number; wallScore: number; collapseRisk: number; grade: string;
  issueCounts: Record<string, number>; summary: string; handler: string | null; hasDetail: boolean;
}

export default function TrailerDetail() {
  const { id = "" } = useParams();
  const { trailers, activeAlerts, ackAlert } = useLive();
  const live = trailers[id];
  const [info, setInfo] = useState<TrailerSummary | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [imgT, setImgT] = useState(Date.now());
  const [hover, setHover] = useState<number | null>(null);
  const [view, setView] = useState<"interactive" | "live" | "raw">("interactive");
  const [paused, setPaused] = useState(false);
  const [timeline, setTimeline] = useState<{ t: number; score: number; risk: number }[]>([]);
  const [walls, setWalls] = useState<WallRow[]>([]);
  const [history, setHistory] = useState<Alert[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<TrailerSummary>(`/api/trailers/${id}`).then(setInfo).catch((e) => setErr(String(e.message)));
  }, [id]);

  // Pull the full analysis whenever the live summary says a new one exists (throttled to 1/s).
  useInterval(() => {
    if (paused) return;
    api.get<AnalysisResult>(`/api/trailers/${id}/latest`).then((r) => {
      setResult(r);
      setImgT(Date.now());
    }).catch(() => undefined);
  }, 1000, [id, paused]);

  useInterval(() => {
    api.get<{ points: { t: number; score: number; risk: number }[] }>(`/api/trailers/${id}/timeline?minutes=30`).then((r) => setTimeline(r.points)).catch(() => undefined);
    api.get<WallRow[]>(`/api/trailers/${id}/walls?limit=15`).then(setWalls).catch(() => undefined);
    api.get<{ alerts: Alert[] }>(`/api/alerts?trailer_id=${id}&limit=30`).then((r) => setHistory(r.alerts)).catch(() => undefined);
  }, 5000, [id]);

  const chartData = useMemo(() => timeline.map((p) => ({
    time: new Date(p.t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    score: p.score, riskPct: Math.round(p.risk * 100),
  })), [timeline]);

  const t = { ...info, ...live } as TrailerSummary;
  const open = activeAlerts.filter((a) => a.trailerId === id);
  if (err) return <MuiAlert severity="error">{err}</MuiAlert>;

  const src = view === "interactive" ? frameUrl(id, { layers: "", t: imgT }) : streamUrl(id, view === "live");

  return (
    <Stack spacing={2.5}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
        <Button component={Link} to="/" startIcon={<ArrowBackIcon />} sx={{ alignSelf: "flex-start" }}>Dashboard</Button>
        <Box sx={{ flex: 1 }}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h4">Trailer {id}</Typography>
            {t.status && <StatusChip status={t.status} size="medium" />}
          </Stack>
          <Typography color="text.secondary">
            Door {t.door} · Handler {t.handler?.name ?? "unassigned"} · Source: {t.sourceType}
            {result?.meta?.wall_seq != null && ` · Wall #${result.meta.wall_seq}`}
            {result && ` · analysed in ${result.timing.totalMs.toFixed(0)} ms`}
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<PhoneAndroidIcon />} component={Link} to={`/handler/${id}`}>Handler view</Button>
      </Stack>

      {open.slice(0, 3).map((a) => (
        <MuiAlert key={a.id} severity={a.severity === "HIGH" ? "error" : "warning"}
          action={a.status === "active" ? <Button color="inherit" size="small" onClick={() => ackAlert(a.id)}>Acknowledge</Button> : undefined}>
          <b>{a.message}</b> — {a.detail.recommendation} <Typography component="span" variant="caption">({timeAgo(a.timestamp)})</Typography>
        </MuiAlert>
      ))}
      {open.length > 3 && (
        <Button component={Link} to="/alerts" size="small" sx={{ alignSelf: "flex-start" }}>
          +{open.length - 3} more open alert{open.length - 3 > 1 ? "s" : ""} for this trailer
        </Button>
      )}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
              <Tabs value={view} onChange={(_, v) => setView(v)} sx={{ flex: 1, minHeight: 36, "& .MuiTab-root": { minHeight: 36 } }}>
                <Tab value="interactive" label="Analysis" />
                <Tab value="live" label="Live (annotated)" />
                <Tab value="raw" label="Live (raw)" />
              </Tabs>
              {view === "interactive" && <Chip size="small" label={paused ? "Paused" : "Live"} color={paused ? "default" : "success"} onClick={() => setPaused(!paused)} />}
            </Stack>
            {view === "interactive" ? (
              <WallViewer src={src} result={result} highlight={hover} onHover={setHover} />
            ) : (
              <Box sx={{ bgcolor: "#000", borderRadius: 2, overflow: "hidden" }}>
                <img src={src} alt="Live feed" style={{ width: "100%", display: "block" }} />
              </Box>
            )}
            {result && <Typography variant="body2" sx={{ mt: 1.5 }}>{result.summary}</Typography>}
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Stack spacing={2}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Stack direction="row" spacing={2} alignItems="center">
                <ScoreRing score={result?.wallScore ?? null} size={104} />
                <Box sx={{ flex: 1 }}>
                  <Typography variant="h6">{result?.grade ?? "–"}</Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {result ? `${result.detections.length} packages · ${result.wall.metrics.layerCount} layers · ${result.wall.metrics.wallHeightIn}" tall` : "Waiting for analysis…"}
                  </Typography>
                  <RiskBar risk={result?.collapseRisk ?? null} />
                </Box>
              </Stack>
            </Paper>
            {result && <ScoreBreakdown result={result} />}
            <Paper variant="outlined" sx={{ p: 2, maxHeight: 520, overflow: "auto" }}>
              <SectionTitle>Issues & corrective actions</SectionTitle>
              <IssueList issues={result?.issues ?? []} highlight={hover} onHover={setHover} />
            </Paper>
          </Stack>
        </Grid>
      </Grid>

      {result && (
        <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
          <SectionTitle>Rule breakdown</SectionTitle>
          <RuleTable rules={result.rules} />
        </Paper>
      )}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SectionTitle>Wall Quality Index — last 30 min</SectionTitle>
            <ScoreLine data={chartData} xKey="time" series={[{ key: "score", name: "WQI" }]} />
            <Typography variant="subtitle2" sx={{ mt: 2 }}>Collapse risk</Typography>
            <RiskLine data={chartData} xKey="time" />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper variant="outlined" sx={{ p: 2, maxHeight: 520, overflow: "auto" }}>
            <SectionTitle>Alert history</SectionTitle>
            {history.length === 0 && <Typography variant="body2" color="text.secondary">No alerts.</Typography>}
            <Stack spacing={1}>
              {history.map((a) => (
                <Stack key={a.id} direction="row" spacing={1} alignItems="center">
                  <SeverityChip severity={a.severity} />
                  <Typography variant="body2" sx={{ flex: 1 }} noWrap title={a.message}>{a.message}</Typography>
                  <Chip size="small" variant="outlined" label={a.status} />
                  <Typography variant="caption" color="text.secondary" sx={{ width: 56, textAlign: "right" }}>{timeAgo(a.timestamp)}</Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
        <SectionTitle>Completed walls</SectionTitle>
        <Table size="small">
          <TableHead>
            <TableRow><TableCell>When</TableCell><TableCell>Shift</TableCell><TableCell>Handler</TableCell><TableCell>WQI</TableCell>
              <TableCell>Risk</TableCell><TableCell>Grade</TableCell><TableCell>Findings</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {walls.map((w) => (
              <TableRow key={w.id}>
                <TableCell>{new Date(w.timestamp).toLocaleString()}</TableCell>
                <TableCell>{w.shift}</TableCell>
                <TableCell>{w.handler ?? "–"}</TableCell>
                <TableCell><b>{w.wallScore}</b></TableCell>
                <TableCell>{Math.round(w.collapseRisk * 100)}%</TableCell>
                <TableCell>{w.grade}</TableCell>
                <TableCell sx={{ maxWidth: 360 }}>
                  <Typography variant="caption" color="text.secondary">
                    {Object.entries(w.issueCounts).map(([k, v]) => `${v}× ${k.toLowerCase().replace(/_/g, " ")}`).join(", ") || "none"}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  );
}
