import {
  Alert as MuiAlert, Box, Button, Grid2 as Grid, LinearProgress, Paper, Slider, Stack, Tab, Tabs, Typography,
} from "@mui/material";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import DataObjectIcon from "@mui/icons-material/DataObject";
import { useState } from "react";
import { api } from "../api";
import { RiskBar, ScoreRing, SectionTitle } from "../components/common";
import { WallViewer } from "../components/WallViewer";
import { IssueList, RuleTable, ScoreBreakdown } from "../components/Explain";
import { ScoreLine } from "../components/Charts";
import type { AnalysisResult } from "../types";

interface VideoResult { frames: number; avgScore: number; timeline: { t: number; score: number }[]; worst: AnalysisResult }

export default function Analyze() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [video, setVideo] = useState<VideoResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [skill, setSkill] = useState(0.3);
  const [hover, setHover] = useState<number | null>(null);
  const [tab, setTab] = useState(0);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const upload = (file: File) =>
    run(async () => {
      const fd = new FormData();
      fd.append("file", file);
      if (file.type.startsWith("video/")) {
        fd.append("every_s", "1");
        const v = await api.form<VideoResult>("/api/analyze/video", fd);
        setVideo(v);
        setResult(v.worst);
      } else {
        setVideo(null);
        setResult(await api.form<AnalysisResult>("/api/analyze", fd));
      }
    });

  const sample = () =>
    run(async () => {
      const fd = new FormData();
      fd.append("skill", String(skill));
      setVideo(null);
      setResult(await api.form<AnalysisResult>("/api/analyze/sample", fd));
    });

  const json = result ? { ...result, image: undefined, annotatedImage: undefined } : null;

  return (
    <Stack spacing={2.5}>
      <Box>
        <Typography variant="h4">Analyze an image or video</Typography>
        <Typography color="text.secondary">Upload a photo of a wall face (or a recorded loading video) and get the full structural analysis.</Typography>
      </Box>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <SectionTitle>Upload</SectionTitle>
            <Button variant="contained" component="label" startIcon={<UploadFileIcon />} disabled={busy}>
              Choose image or video
              <input hidden type="file" accept="image/*,video/*" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </Button>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              JPEG/PNG or MP4/MOV. For best results the camera faces the wall squarely. Without calibration, scale is estimated
              from typical package size and flush-face analysis is skipped (it needs depth).
            </Typography>
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
            <SectionTitle>No camera? Generate a simulated wall</SectionTitle>
            <Typography variant="body2" color="text.secondary">Handler skill: {skill < 0.35 ? "untrained" : skill < 0.7 ? "average" : "expert"} ({skill.toFixed(2)})</Typography>
            <Slider value={skill} min={0} max={1} step={0.05} onChange={(_, v) => setSkill(v as number)} sx={{ maxWidth: 360 }} />
            <Button variant="outlined" startIcon={<AutoAwesomeIcon />} onClick={sample} disabled={busy}>Simulate & analyze</Button>
          </Paper>
        </Grid>
      </Grid>
      {busy && <LinearProgress />}
      {err && <MuiAlert severity="error">{err}</MuiAlert>}
      {video && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <SectionTitle>Video timeline — {video.frames} sampled frames, avg WQI {video.avgScore}</SectionTitle>
          <ScoreLine data={video.timeline.map((p) => ({ ...p, time: `${p.t}s` }))} xKey="time" series={[{ key: "score", name: "WQI" }]} height={200} />
          <Typography variant="body2" color="text.secondary">Showing the lowest-scoring frame below.</Typography>
        </Paper>
      )}
      {result && (
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 7 }}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 1 }}>
                <Tab label="Interactive" /><Tab label="Rendered overlay" /><Tab icon={<DataObjectIcon />} iconPosition="start" label="JSON" />
              </Tabs>
              {tab === 0 && result.image && <WallViewer src={result.image} result={result} highlight={hover} onHover={setHover} />}
              {tab === 1 && result.annotatedImage && <img src={result.annotatedImage} alt="Annotated" style={{ width: "100%", borderRadius: 8 }} />}
              {tab === 2 && (
                <Box component="pre" sx={{ m: 0, p: 1.5, bgcolor: "action.hover", borderRadius: 2, maxHeight: 560, overflow: "auto", fontSize: 12 }}>
                  {JSON.stringify(json, null, 2)}
                </Box>
              )}
              <Typography variant="body2" sx={{ mt: 1.5 }}>{result.summary}</Typography>
            </Paper>
          </Grid>
          <Grid size={{ xs: 12, lg: 5 }}>
            <Stack spacing={2}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" spacing={2} alignItems="center">
                  <ScoreRing score={result.wallScore} size={104} />
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="h6">{result.grade}</Typography>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      {result.detections.length} packages · {result.timing.totalMs.toFixed(0)} ms
                    </Typography>
                    <RiskBar risk={result.collapseRisk} />
                  </Box>
                </Stack>
              </Paper>
              <ScoreBreakdown result={result} />
              <Paper variant="outlined" sx={{ p: 2, maxHeight: 480, overflow: "auto" }}>
                <SectionTitle>Issues & corrective actions</SectionTitle>
                <IssueList issues={result.issues} highlight={hover} onHover={setHover} />
              </Paper>
            </Stack>
          </Grid>
          <Grid size={12}>
            <Paper variant="outlined" sx={{ p: 2, overflowX: "auto" }}>
              <SectionTitle>Rule breakdown</SectionTitle>
              <RuleTable rules={result.rules} />
            </Paper>
          </Grid>
        </Grid>
      )}
    </Stack>
  );
}
