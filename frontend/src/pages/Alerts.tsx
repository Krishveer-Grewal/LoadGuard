import {
  Box, Button, Dialog, DialogContent, DialogTitle, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TablePagination, TableRow,
  TextField, Typography,
} from "@mui/material";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useInterval, useLive } from "../live";
import { SeverityChip } from "../components/common";
import type { Alert } from "../types";

const fmtDur = (a?: string | null, b?: string | null) => {
  if (!a || !b) return "–";
  const s = (new Date(b).getTime() - new Date(a).getTime()) / 1000;
  return s < 90 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m`;
};

export default function Alerts() {
  const { ackAlert, trailers } = useLive();
  const [status, setStatus] = useState("");
  const [trailer, setTrailer] = useState("");
  const [severity, setSeverity] = useState("");
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [sel, setSel] = useState<Alert | null>(null);
  const per = 25;

  const load = () => {
    const p = new URLSearchParams({ limit: String(per), offset: String(page * per) });
    if (status) p.set("status", status);
    if (trailer) p.set("trailer_id", trailer);
    if (severity) p.set("severity", severity);
    api.get<{ total: number; alerts: Alert[] }>(`/api/alerts?${p}`).then((r) => {
      setRows(r.alerts);
      setTotal(r.total);
    }).catch(() => undefined);
  };
  useInterval(load, 4000, [status, trailer, severity, page]);

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h4">Alert history</Typography>
        <Typography color="text.secondary">Alerts fire only after a HIGH-severity issue persists across consecutive frames, and auto-resolve when fixed.</Typography>
      </Box>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <TextField select size="small" label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem><MenuItem value="active">Active</MenuItem>
          <MenuItem value="acknowledged">Acknowledged</MenuItem><MenuItem value="resolved">Resolved</MenuItem>
        </TextField>
        <TextField select size="small" label="Trailer" value={trailer} onChange={(e) => { setTrailer(e.target.value); setPage(0); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem>
          {Object.keys(trailers).map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Severity" value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(0); }} sx={{ minWidth: 160 }}>
          <MenuItem value="">All</MenuItem><MenuItem value="HIGH">High</MenuItem><MenuItem value="MEDIUM">Medium</MenuItem>
        </TextField>
      </Stack>
      <Paper variant="outlined" sx={{ overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell><TableCell>Trailer</TableCell><TableCell>Severity</TableCell><TableCell>Alert</TableCell>
              <TableCell>WQI</TableCell><TableCell>Status</TableCell><TableCell>Time to ack</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((a) => (
              <TableRow key={a.id} hover onClick={() => setSel(a)} sx={{ cursor: "pointer" }}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{new Date(a.timestamp).toLocaleString()}</TableCell>
                <TableCell><Link to={`/trailers/${a.trailerId}`} onClick={(e) => e.stopPropagation()}>{a.trailerId}</Link></TableCell>
                <TableCell><SeverityChip severity={a.severity} /></TableCell>
                <TableCell>{a.message}</TableCell>
                <TableCell>{a.wallScore}</TableCell>
                <TableCell sx={{ textTransform: "capitalize" }}>{a.status}</TableCell>
                <TableCell>{fmtDur(a.timestamp, a.acknowledgedAt)}</TableCell>
                <TableCell>
                  {a.status === "active" && (
                    <Button size="small" onClick={(e) => { e.stopPropagation(); ackAlert(a.id).then(load); }}>Acknowledge</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && <TableRow><TableCell colSpan={8}><Typography color="text.secondary">No alerts match.</Typography></TableCell></TableRow>}
          </TableBody>
        </Table>
        <TablePagination component="div" count={total} page={page} rowsPerPage={per} rowsPerPageOptions={[per]} onPageChange={(_, p) => setPage(p)} />
      </Paper>
      <Dialog open={!!sel} onClose={() => setSel(null)} maxWidth="md" fullWidth>
        {sel && (
          <>
            <DialogTitle>Trailer {sel.trailerId} — {sel.detail.title}</DialogTitle>
            <DialogContent>
              {sel.hasSnapshot && <img src={`/api/alerts/${sel.id}/snapshot.jpg`} alt="Alert snapshot" style={{ width: "100%", borderRadius: 8, marginBottom: 12 }} />}
              <Typography gutterBottom><b>Issue:</b> {sel.detail.issue}</Typography>
              <Typography gutterBottom><b>Why:</b> {sel.detail.reason}</Typography>
              <Typography gutterBottom><b>Risk:</b> {sel.detail.risk}</Typography>
              <Typography gutterBottom><b>Recommendation:</b> {sel.detail.recommendation}</Typography>
              <Typography variant="body2" color="text.secondary">
                Raised {new Date(sel.timestamp).toLocaleString()} · {sel.acknowledgedBy ? `acknowledged by ${sel.acknowledgedBy}` : "not acknowledged"}
                {sel.resolvedAt && ` · resolved ${new Date(sel.resolvedAt).toLocaleTimeString()}`}
              </Typography>
            </DialogContent>
          </>
        )}
      </Dialog>
    </Stack>
  );
}
