import { Box, Button, Card, CardActionArea, CardContent, Chip, Grid2 as Grid, LinearProgress, Paper, Stack, Tooltip, Typography } from "@mui/material";
import LocalShippingIcon from "@mui/icons-material/LocalShipping";
import SpeedIcon from "@mui/icons-material/Speed";
import NotificationsIcon from "@mui/icons-material/NotificationsActive";
import ViewQuiltIcon from "@mui/icons-material/ViewQuilt";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, frameUrl } from "../api";
import { useInterval, useLive } from "../live";
import { Kpi, RiskBar, ScoreRing, SectionTitle, SeverityChip, StatusChip, timeAgo } from "../components/common";
import { statusColor } from "../theme";
import type { TrailerSummary } from "../types";

interface Overview {
  activeTrailers: number; totalTrailers: number; fleetScore: number | null; hazardTrailers: number; warningTrailers: number;
  activeAlerts: number; wallsToday: number; avgScore7d: number | null; avgScorePrev7d: number | null; hazardousWalls7d: number;
  seeding: { state: string; progress: number };
}

/** Refreshing still frame — avoids holding one HTTP connection per MJPEG stream on a busy dashboard. */
function LiveThumb({ tid }: { tid: string }) {
  const [t, setT] = useState(Date.now());
  useInterval(() => setT(Date.now()), 1500, [tid]);
  return (
    <Box sx={{ aspectRatio: "4 / 3", bgcolor: "#000", overflow: "hidden" }}>
      <img src={frameUrl(tid, { annotated: true, t })} alt={`Trailer ${tid}`} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0")} onLoad={(e) => ((e.target as HTMLImageElement).style.opacity = "1")} />
    </Box>
  );
}

function TrailerCard({ t }: { t: TrailerSummary }) {
  const nav = useNavigate();
  return (
    <Card sx={{ borderTop: `4px solid ${statusColor(t.status)}`, height: "100%" }}>
      <CardActionArea onClick={() => nav(`/trailers/${t.trailerId}`)} sx={{ height: "100%" }}>
        <LiveThumb tid={t.trailerId} />
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={2}>
            <ScoreRing score={t.wallScore} size={72} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between">
                <Typography variant="h6" noWrap>Trailer {t.trailerId}</Typography>
                <StatusChip status={t.status} />
              </Stack>
              <Typography variant="body2" color="text.secondary" noWrap>
                Door {t.door} · {t.handler?.name ?? "Unassigned"}
              </Typography>
              <Box sx={{ mt: 1 }}><RiskBar risk={t.collapseRisk} /></Box>
            </Box>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: "wrap", rowGap: 1 }}>
            {t.highCount > 0 && <SeverityChip severity="HIGH" />}
            <Chip size="small" label={`${t.issueCount} issue${t.issueCount === 1 ? "" : "s"}`} variant="outlined" />
            <Chip size="small" label={`${t.packages} pkgs`} variant="outlined" />
            {t.activeAlerts > 0 && <Chip size="small" color="error" label={`${t.activeAlerts} alert${t.activeAlerts > 1 ? "s" : ""}`} />}
          </Stack>
          <Typography variant="body2" sx={{ mt: 1, minHeight: 20 }} noWrap color={t.topIssue ? "text.primary" : "text.secondary"}>
            {t.topIssue ? `Top issue: ${t.topIssue}` : t.online ? "No issues" : t.sourceError ?? "Waiting for camera…"}
          </Typography>
          {t.progress != null && (
            <Tooltip title="Wall build progress">
              <LinearProgress variant="determinate" value={t.progress * 100} sx={{ mt: 1, height: 4, borderRadius: 2 }} />
            </Tooltip>
          )}
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

/** Dock door status map: one tile per door, colour + icon + label so state never relies on colour alone. */
function DockMap({ trailers }: { trailers: TrailerSummary[] }) {
  const nav = useNavigate();
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <SectionTitle>Trailer status map</SectionTitle>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(92px, 1fr))", gap: 1 }}>
        {trailers.map((t) => (
          <Tooltip key={t.trailerId} title={`${t.status} · WQI ${t.wallScore ?? "–"} · ${t.topIssue ?? "no issues"}`}>
            <Box onClick={() => nav(`/trailers/${t.trailerId}`)} sx={{
              cursor: "pointer", borderRadius: 2, p: 1, border: 2, borderColor: statusColor(t.status),
              bgcolor: `${statusColor(t.status)}22`, textAlign: "center", "&:hover": { bgcolor: `${statusColor(t.status)}44` },
            }}>
              <Typography variant="caption" color="text.secondary">DOOR {t.door}</Typography>
              <Typography fontWeight={800}>{t.trailerId}</Typography>
              <Typography variant="caption" fontWeight={700} sx={{ color: statusColor(t.status) }}>
                {t.status === "Hazard" ? "▲ " : t.status === "Warning" ? "● " : t.status === "Good" ? "✓ " : "○ "}{t.status}
              </Typography>
            </Box>
          </Tooltip>
        ))}
      </Box>
    </Paper>
  );
}

function AlertFeed() {
  const { activeAlerts, ackAlert } = useLive();
  const list = activeAlerts.slice(0, 8);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <SectionTitle action={<Button size="small" component={Link} to="/alerts">View all</Button>}>Live alerts</SectionTitle>
      {list.length === 0 && <Typography color="text.secondary" variant="body2">No open alerts.</Typography>}
      <Stack spacing={1}>
        {list.map((a) => (
          <Box key={a.id} sx={{ p: 1.25, border: 1, borderColor: "divider", borderRadius: 2, opacity: a.status === "acknowledged" ? 0.65 : 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <SeverityChip severity={a.severity} />
              <Typography variant="body2" fontWeight={700} component={Link} to={`/trailers/${a.trailerId}`} sx={{ color: "inherit" }}>
                {a.trailerId}
              </Typography>
              <Box sx={{ flex: 1 }} />
              <Typography variant="caption" color="text.secondary">{timeAgo(a.timestamp)}</Typography>
            </Stack>
            <Typography variant="body2" sx={{ mt: 0.5 }}>{a.message}</Typography>
            {a.status === "active" ? (
              <Button size="small" onClick={() => ackAlert(a.id)} sx={{ mt: 0.5, px: 0 }}>Acknowledge</Button>
            ) : (
              <Typography variant="caption" color="text.secondary">Acknowledged by {a.acknowledgedBy}</Typography>
            )}
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}

export default function Dashboard() {
  const { trailers } = useLive();
  const [ov, setOv] = useState<Overview | null>(null);
  useInterval(() => void api.get<Overview>("/api/analytics/overview").then(setOv).catch(() => undefined), 5000);
  const list = Object.values(trailers).sort((a, b) => (a.wallScore ?? 101) - (b.wallScore ?? 101));
  useEffect(() => void 0, []);
  const delta = ov?.avgScore7d != null && ov?.avgScorePrev7d != null ? ov.avgScore7d - ov.avgScorePrev7d : null;

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">Operations overview</Typography>
        <Typography color="text.secondary">Real-time wall quality across active trailers, worst first.</Typography>
      </Box>
      {ov?.seeding.state === "running" && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="body2" color="text.secondary">Building demo history… {(ov.seeding.progress * 100).toFixed(0)}%</Typography>
          <LinearProgress variant="determinate" value={ov.seeding.progress * 100} sx={{ mt: 1 }} />
        </Paper>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 6, md: 3 }}><Kpi icon={<SpeedIcon fontSize="small" />} label="Fleet WQI (live)" value={ov?.fleetScore ?? "–"}
          sub={`${ov?.hazardTrailers ?? 0} hazard · ${ov?.warningTrailers ?? 0} warning`} /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi icon={<LocalShippingIcon fontSize="small" />} label="Trailers online"
          value={`${ov?.activeTrailers ?? 0}/${ov?.totalTrailers ?? 0}`} sub="cameras reporting" /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi icon={<NotificationsIcon fontSize="small" />} label="Open alerts" value={ov?.activeAlerts ?? "–"}
          sub="unacknowledged" /></Grid>
        <Grid size={{ xs: 6, md: 3 }}><Kpi icon={<ViewQuiltIcon fontSize="small" />} label="7-day avg WQI" value={ov?.avgScore7d ?? "–"}
          sub={delta == null ? `${ov?.wallsToday ?? 0} walls today` : `${delta >= 0 ? "▲" : "▼"} ${Math.abs(delta).toFixed(1)} vs prior week`} /></Grid>
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 9 }}>
          <Grid container spacing={2}>
            {list.map((t) => (
              <Grid key={t.trailerId} size={{ xs: 12, sm: 6, xl: 4 }}><TrailerCard t={t} /></Grid>
            ))}
            {list.length === 0 && <Typography color="text.secondary" sx={{ p: 2 }}>No trailers configured. Add one under Trailers & cameras.</Typography>}
          </Grid>
        </Grid>
        <Grid size={{ xs: 12, lg: 3 }}>
          <Stack spacing={2}>
            <DockMap trailers={[...list].sort((a, b) => a.door - b.door)} />
            <AlertFeed />
          </Stack>
        </Grid>
      </Grid>
    </Stack>
  );
}
