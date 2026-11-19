import {
  Alert as MuiAlert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, MenuItem, Paper, Slider, Stack, Switch, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/EditOutlined";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useLive } from "../live";
import { StatusChip } from "../components/common";
import type { Handler, TrailerSummary } from "../types";

const SOURCES = [
  { v: "simulator", label: "Simulator (demo)" },
  { v: "rtsp", label: "RTSP / HTTP stream" },
  { v: "webcam", label: "Webcam (device index)" },
  { v: "video", label: "Recorded video file (server path)" },
  { v: "push", label: "Pushed frames (handheld camera)" },
];

interface Form {
  id: string; door: number; source_type: string; source_uri: string; sim_skill: number; handler_id: number | "";
  calibration: string;
}
const blank: Form = { id: "", door: 107, source_type: "simulator", source_uri: "", sim_skill: 0.5, handler_id: "", calibration: "" };

export default function Cameras() {
  const { trailers, refreshTrailers } = useLive();
  const [handlers, setHandlers] = useState<Handler[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  useEffect(() => void api.get<Handler[]>("/api/handlers").then(setHandlers), []);
  const list = Object.values(trailers).sort((a, b) => a.door - b.door);

  const openEdit = (t: TrailerSummary) => {
    setEditing(true);
    setForm({
      id: t.trailerId, door: t.door, source_type: t.sourceType, source_uri: t.sourceUri ?? "", sim_skill: t.simSkill ?? 0.5,
      handler_id: t.handlerId ?? "", calibration: "",
    });
  };

  const save = async () => {
    if (!form) return;
    setErr(null);
    let calibration: unknown = undefined;
    if (form.calibration.trim()) {
      try {
        calibration = JSON.parse(form.calibration);
      } catch {
        setErr("Calibration must be valid JSON");
        return;
      }
    }
    const body = {
      door: Number(form.door), source_type: form.source_type, source_uri: form.source_uri || null, sim_skill: form.sim_skill,
      handler_id: form.handler_id === "" ? null : form.handler_id, ...(calibration ? { calibration } : {}),
    };
    try {
      if (editing) await api.patch(`/api/trailers/${form.id}`, body);
      else await api.post("/api/trailers", { id: form.id, ...body });
      setForm(null);
      await refreshTrailers();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const toggle = async (t: TrailerSummary) => {
    await api.patch(`/api/trailers/${t.trailerId}`, { active: !t.active });
    await refreshTrailers();
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center">
        <Box sx={{ flex: 1 }}>
          <Typography variant="h4">Trailers & cameras</Typography>
          <Typography color="text.secondary">Connect a camera per trailer: RTSP stream, webcam, recorded video, a handheld pushing frames, or the simulator.</Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => { setEditing(false); setForm(blank); }}>Add trailer</Button>
      </Stack>
      <Paper variant="outlined" sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow><TableCell>Trailer</TableCell><TableCell>Door</TableCell><TableCell>Source</TableCell><TableCell>Handler</TableCell>
              <TableCell>Status</TableCell><TableCell>Latency</TableCell><TableCell>Monitoring</TableCell><TableCell /></TableRow>
          </TableHead>
          <TableBody>
            {list.map((t) => (
              <TableRow key={t.trailerId}>
                <TableCell><b>{t.trailerId}</b></TableCell>
                <TableCell>{t.door}</TableCell>
                <TableCell>{t.sourceType}{t.sourceUri ? ` · ${t.sourceUri}` : t.sourceType === "simulator" ? ` · skill ${t.simSkill?.toFixed(2)}` : ""}
                  {t.sourceError && <Typography variant="caption" color="error" display="block">{t.sourceError}</Typography>}</TableCell>
                <TableCell>{t.handler?.name ?? "–"}</TableCell>
                <TableCell><StatusChip status={t.status} /></TableCell>
                <TableCell>{t.latencyMs != null ? `${t.latencyMs.toFixed(0)} ms` : "–"}</TableCell>
                <TableCell><Switch checked={t.active !== false} onChange={() => toggle(t)} /></TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  <Tooltip title="Edit"><IconButton onClick={() => openEdit(t)}><EditIcon /></IconButton></Tooltip>
                  <Tooltip title="Delete"><IconButton onClick={() => setConfirmDel(t.trailerId)}><DeleteIcon /></IconButton></Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>Calibration (optional, per camera)</Typography>
        <Typography variant="body2" color="text.secondary">
          JSON: <code>{`{"roi":[x0,y0,x1,y1],"floor_y":690,"px_per_inch":6.2,"trailer_height_in":108}`}</code>. ROI is the wall face in
          pixels, floor_y the trailer floor line, px_per_inch converts to physical units. Without it the system infers the floor from
          the lowest packages and estimates scale from typical package size.
        </Typography>
      </Paper>

      <Dialog open={!!form} onClose={() => setForm(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? `Edit trailer ${form?.id}` : "Add trailer"}</DialogTitle>
        {form && (
          <DialogContent>
            <Stack spacing={2} sx={{ mt: 1 }}>
              {err && <MuiAlert severity="error">{err}</MuiAlert>}
              <TextField label="Trailer ID" value={form.id} disabled={editing} onChange={(e) => setForm({ ...form, id: e.target.value })} required />
              <TextField label="Dock door" type="number" value={form.door} onChange={(e) => setForm({ ...form, door: Number(e.target.value) })} />
              <TextField select label="Camera source" value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value })}>
                {SOURCES.map((s) => <MenuItem key={s.v} value={s.v}>{s.label}</MenuItem>)}
              </TextField>
              {["rtsp", "webcam", "video"].includes(form.source_type) && (
                <TextField label={form.source_type === "rtsp" ? "Stream URL" : form.source_type === "webcam" ? "Device index" : "File path on server"}
                  placeholder={form.source_type === "rtsp" ? "rtsp://user:pass@10.0.0.20:554/stream1" : form.source_type === "webcam" ? "0" : "/data/videos/load.mp4"}
                  value={form.source_uri} onChange={(e) => setForm({ ...form, source_uri: e.target.value })} />
              )}
              {form.source_type === "simulator" && (
                <Box>
                  <Typography variant="body2" color="text.secondary">Simulated handler skill: {form.sim_skill.toFixed(2)}</Typography>
                  <Slider value={form.sim_skill} min={0} max={1} step={0.05} onChange={(_, v) => setForm({ ...form, sim_skill: v as number })} />
                </Box>
              )}
              {form.source_type === "push" && (
                <MuiAlert severity="info">Open the Handler app on the device and tap "Use this device's camera", or POST JPEG frames to
                  <code> /api/trailers/{form.id || "ID"}/frames</code>.</MuiAlert>
              )}
              <TextField select label="Handler" value={form.handler_id} onChange={(e) => setForm({ ...form, handler_id: e.target.value === "" ? "" : Number(e.target.value) })}>
                <MenuItem value="">Unassigned</MenuItem>
                {handlers.map((h) => <MenuItem key={h.id} value={h.id}>{h.name} ({h.badge})</MenuItem>)}
              </TextField>
              <TextField label="Calibration JSON (optional)" multiline minRows={2} value={form.calibration}
                onChange={(e) => setForm({ ...form, calibration: e.target.value })} />
            </Stack>
          </DialogContent>
        )}
        <DialogActions>
          <Button onClick={() => setForm(null)}>Cancel</Button>
          <Button variant="contained" onClick={save} disabled={!form?.id}>Save</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!confirmDel} onClose={() => setConfirmDel(null)}>
        <DialogTitle>Delete trailer {confirmDel}?</DialogTitle>
        <DialogContent><Typography>This stops monitoring and deletes its analysis and alert history.</Typography></DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDel(null)}>Cancel</Button>
          <Button color="error" variant="contained" onClick={async () => {
            await api.del(`/api/trailers/${confirmDel}`);
            setConfirmDel(null);
            await refreshTrailers();
          }}>Delete</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
