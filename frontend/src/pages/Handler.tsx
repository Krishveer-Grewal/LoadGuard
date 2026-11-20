import {
  Box, Button, Dialog, DialogContent, MenuItem, Paper, Stack, TextField, Typography,
} from "@mui/material";
import ReportIcon from "@mui/icons-material/Report";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CameraAltIcon from "@mui/icons-material/CameraAlt";
import StopCircleIcon from "@mui/icons-material/StopCircle";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, frameUrl } from "../api";
import { useInterval, useLive } from "../live";
import { ScoreRing } from "../components/common";
import { scoreColor, sevColor, STATUS } from "../theme";
import type { Alert, AnalysisResult } from "../types";

/** Short audible cue so the alert is noticed on a loud dock floor. */
function beep() {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    [0, 0.25].forEach((t) => {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = 880;
      g.gain.setValueAtTime(0.25, ctx.currentTime + t);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.2);
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + t);
      o.stop(ctx.currentTime + t + 0.2);
    });
  } catch {
    /* audio blocked until user interacts */
  }
}

/** Streams this device's camera to a `push` trailer (Zebra handheld / phone). */
function useCameraPush(tid: string, enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let stream: MediaStream | null = null;
    let timer: number | undefined;
    let busy = false;
    const canvas = document.createElement("canvas");
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false })
      .then((s) => {
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
          void videoRef.current.play();
        }
        timer = window.setInterval(() => {
          const v = videoRef.current;
          if (!v || !v.videoWidth || busy) return;
          canvas.width = v.videoWidth;
          canvas.height = v.videoHeight;
          canvas.getContext("2d")!.drawImage(v, 0, 0);
          busy = true;
          canvas.toBlob((b) => {
            if (!b) return void (busy = false);
            const fd = new FormData();
            fd.append("file", b, "frame.jpg");
            fetch(`/api/trailers/${tid}/frames`, { method: "POST", body: fd })
              .then((r) => (r.ok ? setErr(null) : r.json().then((j) => setErr(j.detail))))
              .finally(() => (busy = false));
          }, "image/jpeg", 0.75);
        }, 700);
      })
      .catch((e) => setErr(`Camera unavailable: ${e.message ?? e}`));
    return () => {
      window.clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [tid, enabled]);
  return { videoRef, err };
}

export default function HandlerApp() {
  const { id } = useParams();
  const nav = useNavigate();
  const { trailers, activeAlerts, onAlert, ackAlert, connected } = useLive();
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem("lg-handler-name") ?? "";
    } catch {
      return "";
    }
  });
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [t, setT] = useState(Date.now());
  const [takeover, setTakeover] = useState<Alert | null>(null);
  const [camOn, setCamOn] = useState(false);
  const trailer = id ? trailers[id] : undefined;
  const { videoRef, err: camErr } = useCameraPush(id ?? "", camOn && !!id);

  useInterval(() => {
    if (!id) return;
    api.get<AnalysisResult>(`/api/trailers/${id}/latest`).then((r) => {
      setResult(r);
      setT(Date.now());
    }).catch(() => undefined);
  }, 1200, [id]);

  useEffect(() => onAlert((a, isNew) => {
    if (!isNew || a.trailerId !== id) return;
    setTakeover(a);
    navigator.vibrate?.([300, 120, 300]);
    beep();
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
      new Notification(`Trailer ${a.trailerId}: ${a.message}`, { body: a.detail.recommendation, tag: `lg-${a.id}` });
    }
  }), [onAlert, id]);

  const saveName = (v: string) => {
    setName(v);
    try {
      localStorage.setItem("lg-handler-name", v);
    } catch {
      /* ignore */
    }
  };
  const ack = async (a: Alert) => {
    await ackAlert(a.id, name || "handler");
    setTakeover(null);
  };

  const mine = activeAlerts.filter((a) => a.trailerId === id && a.status === "active");
  const steps = (result?.issues ?? []).slice(0, 3);

  return (
    <Box sx={{ maxWidth: 520, mx: "auto", p: 1.5, pb: 6, minHeight: "100vh", overflowX: "hidden" }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
        <img src="/icon.svg" width={30} height={30} alt="" />
        <Typography variant="h6" sx={{ flex: 1, fontWeight: 800 }}>Load<Box component="span" sx={{ color: "primary.main" }}>Guard</Box></Typography>
        <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: connected ? "success.main" : "error.main" }} />
      </Stack>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 1.5 }}>
        <TextField select fullWidth label="My trailer" value={id ?? ""} onChange={(e) => nav(`/handler/${e.target.value}`)}
          SelectProps={{ sx: { fontSize: 20, fontWeight: 700 } }}>
          {Object.values(trailers).sort((a, b) => a.door - b.door).map((tr) => (
            <MenuItem key={tr.trailerId} value={tr.trailerId}>{tr.trailerId} · Door {tr.door}</MenuItem>
          ))}
        </TextField>
        <TextField label="My name" value={name} onChange={(e) => saveName(e.target.value)} sx={{ width: { xs: "100%", sm: 170 }, flex: "none" }} />
      </Stack>

      {!id && <Typography color="text.secondary" sx={{ p: 2 }}>Pick your trailer to get live guidance.</Typography>}

      {id && (
        <Stack spacing={1.5}>
          {"Notification" in window && Notification.permission === "default" && (
            <Button variant="outlined" startIcon={<NotificationsActiveIcon />} onClick={() => Notification.requestPermission()} size="large">
              Enable alert notifications
            </Button>
          )}

          {mine.length > 2 && (
            <Typography fontWeight={700} color="error.main">{mine.length} open alerts — fix the top ones first</Typography>
          )}
          {mine.slice(0, 2).map((a) => (
            <Paper key={a.id} sx={{ p: 2, bgcolor: sevColor(a.severity), color: "#111" }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <ReportIcon />
                <Typography fontWeight={800} sx={{ flex: 1, fontSize: 18 }}>{a.message}</Typography>
              </Stack>
              <Typography sx={{ mt: 0.5 }}>{a.detail.recommendation}</Typography>
              <Button fullWidth variant="contained" size="large" onClick={() => ack(a)}
                sx={{ mt: 1.5, bgcolor: "#111", color: "#fff", "&:hover": { bgcolor: "#333" }, py: 1.5, fontSize: 18 }}>
                Got it — fixing now
              </Button>
            </Paper>
          ))}

          <Paper variant="outlined" sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={2} alignItems="center">
              <ScoreRing score={result?.wallScore ?? trailer?.wallScore ?? null} size={92} />
              <Box sx={{ flex: 1 }}>
                <Typography variant="h5" sx={{ color: scoreColor(result?.wallScore) }}>{result?.grade ?? "–"}</Typography>
                <Typography color="text.secondary">
                  {result ? `${result.detections.length} packages · risk ${Math.round(result.collapseRisk * 100)}%` : "Waiting for camera…"}
                </Typography>
              </Box>
            </Stack>
          </Paper>

          <Box sx={{ borderRadius: 2, overflow: "hidden", bgcolor: "#000" }}>
            <img src={frameUrl(id, { annotated: true, t })} alt="Annotated wall" style={{ width: "100%", display: "block" }} />
          </Box>

          <Paper variant="outlined" sx={{ p: 1.5 }}>
            <Typography variant="overline" color="text.secondary">Do this next</Typography>
            {!result ? (
              <Typography color="text.secondary" sx={{ py: 1 }}>Waiting for the first analysis…</Typography>
            ) : steps.length === 0 ? (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ color: STATUS.good, py: 1 }}>
                <CheckCircleIcon fontSize="large" />
                <Typography fontSize={20} fontWeight={700}>Wall looks good. Keep going.</Typography>
              </Stack>
            ) : (
              <Stack spacing={1.25}>
                {steps.map((s) => (
                  <Stack key={s.id} direction="row" spacing={1.25} alignItems="flex-start"
                    sx={{ p: 1.25, borderRadius: 2, border: 2, borderColor: sevColor(s.severity) }}>
                    <Box sx={{ width: 34, height: 34, borderRadius: "50%", bgcolor: "#fff", color: "#111", border: `4px solid ${sevColor(s.severity)}`,
                      display: "grid", placeItems: "center", fontWeight: 900, flex: "none" }}>{s.id}</Box>
                    <Box>
                      <Typography fontWeight={800} fontSize={18}>{s.recommendation}</Typography>
                      <Typography variant="body2" color="text.secondary">{s.title}: {s.reason}</Typography>
                    </Box>
                  </Stack>
                ))}
              </Stack>
            )}
          </Paper>

          {trailer?.sourceType === "push" && (
            <Paper variant="outlined" sx={{ p: 1.5 }}>
              <Typography variant="overline" color="text.secondary">Device camera</Typography>
              <video ref={videoRef} muted playsInline style={{ width: "100%", borderRadius: 8, display: camOn ? "block" : "none" }} />
              {camErr && <Typography color="error" variant="body2">{camErr}</Typography>}
              <Button fullWidth size="large" variant={camOn ? "outlined" : "contained"} startIcon={camOn ? <StopCircleIcon /> : <CameraAltIcon />}
                onClick={() => setCamOn(!camOn)} sx={{ mt: 1, py: 1.5 }}>
                {camOn ? "Stop camera" : "Use this device's camera"}
              </Button>
            </Paper>
          )}
        </Stack>
      )}

      <Dialog open={!!takeover} fullScreen onClose={() => setTakeover(null)}>
        {takeover && (
          <DialogContent sx={{ bgcolor: sevColor(takeover.severity), color: "#111", display: "flex", flexDirection: "column", justifyContent: "center", gap: 2 }}>
            <ReportIcon sx={{ fontSize: 72 }} />
            <Typography variant="h4" fontWeight={900}>{takeover.message}</Typography>
            <Typography fontSize={20}><b>Fix:</b> {takeover.detail.recommendation}</Typography>
            <Typography>{takeover.detail.reason}</Typography>
            {takeover.hasSnapshot && <img src={`/api/alerts/${takeover.id}/snapshot.jpg`} alt="Where" style={{ width: "100%", borderRadius: 8 }} />}
            <Button variant="contained" size="large" onClick={() => ack(takeover)}
              sx={{ bgcolor: "#111", color: "#fff", py: 2, fontSize: 20, "&:hover": { bgcolor: "#333" } }}>Got it — fixing now</Button>
            <Button onClick={() => setTakeover(null)} sx={{ color: "#111" }}>Dismiss</Button>
          </DialogContent>
        )}
      </Dialog>
    </Box>
  );
}
