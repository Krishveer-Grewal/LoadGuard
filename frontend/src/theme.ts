import { createTheme, PaletteMode } from "@mui/material";

// Status colours are reserved for state (never reused as a data series) and always paired
// with an icon + label. Series colours come from a CVD-validated categorical order.
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;

export const SERIES = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c"],
};

export const sevColor = (s: string) =>
  s === "HIGH" ? STATUS.critical : s === "MEDIUM" ? STATUS.serious : STATUS.warning;

export const scoreColor = (score: number | null | undefined) =>
  score == null ? "#8a8f98" : score >= 75 ? STATUS.good : score >= 50 ? STATUS.warning : STATUS.critical;

export const statusColor = (s: string) =>
  s === "Good" ? STATUS.good : s === "Warning" ? STATUS.warning : s === "Hazard" ? STATUS.critical : "#8a8f98";

export function makeTheme(mode: PaletteMode) {
  const dark = mode === "dark";
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? "#3987e5" : "#2a78d6" },
      success: { main: STATUS.good },
      warning: { main: STATUS.warning },
      error: { main: STATUS.critical },
      background: dark ? { default: "#121418", paper: "#1b1e24" } : { default: "#f4f5f7", paper: "#ffffff" },
      text: dark ? { primary: "#f0efec", secondary: "#a9adb5" } : { primary: "#0b0b0b", secondary: "#52514e" },
      divider: dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)",
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: '"Inter", "Segoe UI", Roboto, system-ui, -apple-system, sans-serif',
      h4: { fontWeight: 700, letterSpacing: -0.5 },
      h5: { fontWeight: 700, letterSpacing: -0.3 },
      h6: { fontWeight: 650 },
      overline: { fontWeight: 600, letterSpacing: 1 },
    },
    components: {
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
      MuiCard: {
        defaultProps: { variant: "outlined" },
        styleOverrides: { root: { borderRadius: 12 } },
      },
      MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { textTransform: "none", fontWeight: 600 } } },
      MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
      MuiTableCell: { styleOverrides: { root: { borderColor: dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" } } },
    },
  });
}
