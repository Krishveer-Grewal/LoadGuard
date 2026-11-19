import { useTheme } from "@mui/material";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { SERIES, STATUS } from "../theme";

function useChartTokens() {
  const t = useTheme();
  const dark = t.palette.mode === "dark";
  return {
    series: dark ? SERIES.dark : SERIES.light,
    grid: dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.07)",
    axis: t.palette.text.secondary,
    tooltip: {
      contentStyle: { background: t.palette.background.paper, border: `1px solid ${t.palette.divider}`, borderRadius: 8, fontSize: 13 },
      labelStyle: { color: t.palette.text.primary, fontWeight: 600 },
      itemStyle: { color: t.palette.text.primary },
    },
  };
}

const axisProps = (color: string) => ({ stroke: color, tick: { fill: color, fontSize: 12 }, tickLine: false, axisLine: false });

/** WQI over time on a fixed 0–100 axis with the grade thresholds (50 / 75) as references. */
export function ScoreLine({ data, xKey, height = 240, series }: {
  data: Record<string, unknown>[]; xKey: string; height?: number;
  series: { key: string; name: string }[];
}) {
  const c = useChartTokens();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey={xKey} {...axisProps(c.axis)} minTickGap={24} />
        <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} {...axisProps(c.axis)} />
        <ReferenceLine y={75} stroke={STATUS.good} strokeDasharray="4 4" strokeOpacity={0.6} />
        <ReferenceLine y={50} stroke={STATUS.critical} strokeDasharray="4 4" strokeOpacity={0.6} />
        <Tooltip {...c.tooltip} cursor={{ stroke: c.axis, strokeDasharray: "3 3" }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {series.map((s, i) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={c.series[i % c.series.length]} strokeWidth={2}
            dot={false} activeDot={{ r: 5 }} connectNulls isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function RiskLine({ data, xKey, height = 160 }: { data: Record<string, unknown>[]; xKey: string; height?: number }) {
  const c = useChartTokens();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey={xKey} {...axisProps(c.axis)} minTickGap={24} />
        <YAxis domain={[0, 100]} unit="%" ticks={[0, 50, 100]} {...axisProps(c.axis)} />
        <Tooltip {...c.tooltip} formatter={(v: number) => `${v}%`} />
        <Line type="monotone" dataKey="riskPct" name="Collapse risk" stroke={c.series[1]} strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Horizontal bars for counts by category (one series → no legend; title names it). */
export function CountBars({ data, height = 240, color }: { data: { name: string; value: number }[]; height?: number; color?: string }) {
  const c = useChartTokens();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 8 }} barCategoryGap={6}>
        <CartesianGrid stroke={c.grid} horizontal={false} />
        <XAxis type="number" {...axisProps(c.axis)} allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={150} {...axisProps(c.axis)} />
        <Tooltip {...c.tooltip} cursor={{ fill: c.grid }} />
        <Bar dataKey="value" name="Count" fill={color ?? c.series[0]} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Stacked daily walls by grade band (status colours, legend always shown). */
export function GradeStack({ data, height = 220 }: { data: Record<string, unknown>[]; height?: number }) {
  const c = useChartTokens();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -12 }} barCategoryGap="20%">
        <CartesianGrid stroke={c.grid} vertical={false} />
        <XAxis dataKey="label" {...axisProps(c.axis)} minTickGap={16} />
        <YAxis {...axisProps(c.axis)} allowDecimals={false} />
        <Tooltip {...c.tooltip} cursor={{ fill: c.grid }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="hazardous" name="Hazardous (<50)" stackId="g" fill={STATUS.critical} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
        <Bar dataKey="ok" name="50–89" stackId="g" fill={STATUS.warning} stroke="var(--surface)" strokeWidth={1} isAnimationActive={false} />
        <Bar dataKey="excellent" name="Excellent (90+)" stackId="g" fill={STATUS.good} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
