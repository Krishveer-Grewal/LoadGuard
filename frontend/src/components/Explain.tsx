import { Box, LinearProgress, List, ListItemButton, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import type { AnalysisResult, Issue, RuleResult } from "../types";
import { RULE_LABEL, RuleStatusChip, SeverityChip } from "./common";
import { scoreColor, sevColor, STATUS } from "../theme";

/** Every issue: what, why (with evidence), risk, and how to fix it. */
export function IssueList({ issues, highlight, onHover, compact = false }: {
  issues: Issue[]; highlight?: number | null; onHover?: (id: number | null) => void; compact?: boolean;
}) {
  if (!issues.length)
    return (
      <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 2, color: STATUS.good }}>
        <CheckCircleIcon />
        <Typography>No structural issues detected. Keep building this way.</Typography>
      </Stack>
    );
  return (
    <List disablePadding sx={{ display: "grid", gap: 1 }}>
      {issues.map((i) => (
        <ListItemButton key={i.id} selected={highlight === i.id} onMouseEnter={() => onHover?.(i.id)} onMouseLeave={() => onHover?.(null)}
          sx={{ display: "block", border: 1, borderColor: "divider", borderLeft: `4px solid ${sevColor(i.severity)}`, borderRadius: 2, py: 1.25 }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Box sx={{ width: 24, height: 24, borderRadius: "50%", bgcolor: "#fff", color: "#111", border: `3px solid ${sevColor(i.severity)}`,
              display: "grid", placeItems: "center", fontSize: 12, fontWeight: 800, flex: "none" }}>{i.id}</Box>
            <Typography fontWeight={700} sx={{ flex: 1 }}>{i.title}</Typography>
            <SeverityChip severity={i.severity} />
          </Stack>
          <Typography variant="body2" color="text.secondary"><b>Why:</b> {i.reason}</Typography>
          {!compact && <Typography variant="body2" color="text.secondary"><b>Risk:</b> {i.risk}</Typography>}
          <Typography variant="body2" sx={{ mt: 0.5 }}><b>Fix:</b> {i.recommendation}</Typography>
        </ListItemButton>
      ))}
    </List>
  );
}

export function RuleTable({ rules }: { rules: RuleResult[] }) {
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Rule</TableCell>
          <TableCell sx={{ width: 140 }}>Score</TableCell>
          <TableCell>Status</TableCell>
          <TableCell sx={{ display: { xs: "none", md: "table-cell" } }}>Evidence</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rules.map((r) => (
          <TableRow key={r.rule}>
            <TableCell><Typography variant="body2" fontWeight={600}>{r.name}</Typography>
              <Typography variant="caption" color="text.secondary">{r.rule}</Typography></TableCell>
            <TableCell>
              {r.score == null ? "–" : (
                <Stack direction="row" spacing={1} alignItems="center">
                  <LinearProgress variant="determinate" value={r.score * 100} sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: "action.hover",
                    "& .MuiLinearProgress-bar": { bgcolor: scoreColor(r.score * 100), borderRadius: 3 } }} />
                  <Typography variant="body2" sx={{ width: 32 }}>{r.score.toFixed(2)}</Typography>
                </Stack>
              )}
            </TableCell>
            <TableCell><RuleStatusChip status={r.status} /></TableCell>
            <TableCell sx={{ display: { xs: "none", md: "table-cell" } }}><Typography variant="body2" color="text.secondary">{r.explanation}</Typography></TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** Where the points went: WQI is never shown without its breakdown. */
export function ScoreBreakdown({ result }: { result: AnalysisResult }) {
  const lost = result.scoreBreakdown.filter((b) => b.pointsLost > 0.05).sort((a, b) => b.pointsLost - a.pointsLost);
  const max = Math.max(1, ...lost.map((b) => b.pointsLost));
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2" gutterBottom>Points lost by rule</Typography>
      {lost.length === 0 && <Typography variant="body2" color="text.secondary">No points lost.</Typography>}
      {lost.map((b) => (
        <Tooltip key={b.rule} title={b.score != null ? `rule score ${b.score} × weight ${(b.weight * 100).toFixed(0)}%` : "3 points per HIGH-severity finding (max 15)"}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.75 }}>
            <Typography variant="body2" sx={{ width: 150, flex: "none" }} noWrap>{RULE_LABEL[b.rule] ?? b.rule}</Typography>
            <Box sx={{ flex: 1, height: 10, bgcolor: "action.hover", borderRadius: 1 }}>
              <Box sx={{ width: `${(b.pointsLost / max) * 100}%`, height: "100%", bgcolor: "primary.main", borderRadius: "0 4px 4px 0" }} />
            </Box>
            <Typography variant="body2" sx={{ width: 44, textAlign: "right" }}>−{b.pointsLost.toFixed(1)}</Typography>
          </Stack>
        </Tooltip>
      ))}
      <Typography variant="subtitle2" sx={{ mt: 2 }} gutterBottom>Risk drivers</Typography>
      <Typography variant="body2" color="text.secondary">
        {result.riskFactors.filter((f) => f.contribution > 0.05).slice(0, 3).map((f) => RULE_LABEL[f.factor] ?? f.factor).join(" · ") || "None significant"}
      </Typography>
    </Paper>
  );
}
