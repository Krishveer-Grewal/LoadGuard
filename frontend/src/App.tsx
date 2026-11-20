import {
  AppBar, Badge, Box, CssBaseline, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, PaletteMode,
  Snackbar, Alert as MuiAlert, Stack, ThemeProvider, Toolbar, Tooltip, Typography, useMediaQuery,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/SpaceDashboard";
import NotificationsIcon from "@mui/icons-material/NotificationsActive";
import InsightsIcon from "@mui/icons-material/Insights";
import UploadIcon from "@mui/icons-material/ImageSearch";
import VideocamIcon from "@mui/icons-material/Videocam";
import PhoneAndroidIcon from "@mui/icons-material/PhoneAndroid";
import MenuIcon from "@mui/icons-material/Menu";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import { useEffect, useMemo, useState } from "react";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { LiveProvider, useLive } from "./live";
import { makeTheme } from "./theme";
import Dashboard from "./pages/Dashboard";
import TrailerDetail from "./pages/TrailerDetail";
import Alerts from "./pages/Alerts";
import Analytics from "./pages/Analytics";
import Analyze from "./pages/Analyze";
import Cameras from "./pages/Cameras";
import HandlerApp from "./pages/Handler";
import type { Alert } from "./types";

const NAV = [
  { to: "/", label: "Dashboard", icon: <DashboardIcon /> },
  { to: "/alerts", label: "Alerts", icon: <NotificationsIcon /> },
  { to: "/analytics", label: "Analytics", icon: <InsightsIcon /> },
  { to: "/analyze", label: "Analyze image", icon: <UploadIcon /> },
  { to: "/cameras", label: "Trailers & cameras", icon: <VideocamIcon /> },
  { to: "/handler", label: "Handler app", icon: <PhoneAndroidIcon /> },
];
const DRAWER = 228;

function readMode(): PaletteMode {
  try {
    const v = localStorage.getItem("lg-theme");
    if (v === "light" || v === "dark") return v;
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function Shell({ mode, setMode }: { mode: PaletteMode; setMode: (m: PaletteMode) => void }) {
  const { activeAlerts, connected, onAlert } = useLive();
  const loc = useLocation();
  const nav = useNavigate();
  const wide = useMediaQuery("(min-width:900px)");
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<Alert | null>(null);
  const active = activeAlerts.filter((a) => a.status === "active").length;

  useEffect(() => onAlert((a, isNew) => isNew && setToast(a)), [onAlert]);

  const drawer = (
    <Box sx={{ pt: 1 }}>
      <List>
        {NAV.map((n) => (
          <ListItemButton key={n.to} component={Link} to={n.to} selected={n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to)}
            onClick={() => setOpen(false)} sx={{ mx: 1, borderRadius: 2 }}>
            <ListItemIcon sx={{ minWidth: 38 }}>
              {n.to === "/alerts" ? <Badge color="error" badgeContent={active}>{n.icon}</Badge> : n.icon}
            </ListItemIcon>
            <ListItemText primary={n.label} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <AppBar position="fixed" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: "divider", zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          {!wide && <IconButton edge="start" onClick={() => setOpen(true)} aria-label="menu"><MenuIcon /></IconButton>}
          <Stack direction="row" alignItems="center" spacing={1} component={Link} to="/" sx={{ color: "inherit", textDecoration: "none", flex: 1 }}>
            <img src="/icon.svg" width={28} height={28} alt="" />
            <Typography variant="h6" sx={{ fontWeight: 800 }}>Load<Box component="span" sx={{ color: "primary.main" }}>Guard</Box></Typography>
          </Stack>
          <Tooltip title={connected ? "Live updates connected" : "Reconnecting…"}>
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mr: 1.5 }}>
              <Box sx={{ width: 9, height: 9, borderRadius: "50%", bgcolor: connected ? "success.main" : "error.main" }} />
              <Typography variant="body2" color="text.secondary" sx={{ display: { xs: "none", sm: "block" } }}>{connected ? "Live" : "Offline"}</Typography>
            </Stack>
          </Tooltip>
          <Tooltip title="Toggle light/dark">
            <IconButton onClick={() => setMode(mode === "dark" ? "light" : "dark")}>{mode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}</IconButton>
          </Tooltip>
          <IconButton onClick={() => nav("/alerts")} aria-label="alerts">
            <Badge color="error" badgeContent={active}><NotificationsIcon /></Badge>
          </IconButton>
        </Toolbar>
      </AppBar>
      <Drawer variant={wide ? "permanent" : "temporary"} open={wide || open} onClose={() => setOpen(false)}
        sx={{ width: DRAWER, flexShrink: 0, "& .MuiDrawer-paper": { width: DRAWER, boxSizing: "border-box", borderRight: 1, borderColor: "divider" } }}>
        <Toolbar />
        {drawer}
      </Drawer>
      <Box component="main" sx={{ flex: 1, minWidth: 0, p: { xs: 2, md: 3 }, pt: { xs: 10, md: 11 } }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/trailers/:id" element={<TrailerDetail />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/cameras" element={<Cameras />} />
        </Routes>
      </Box>
      <Snackbar open={!!toast} autoHideDuration={6000} onClose={() => setToast(null)} anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <MuiAlert severity={toast?.severity === "HIGH" ? "error" : "warning"} variant="filled" onClose={() => setToast(null)}
          onClick={() => toast && nav(`/trailers/${toast.trailerId}`)} sx={{ cursor: "pointer" }}>
          <b>Trailer {toast?.trailerId}:</b> {toast?.message}
        </MuiAlert>
      </Snackbar>
    </Box>
  );
}

export default function App() {
  const [mode, setModeState] = useState<PaletteMode>(readMode);
  const theme = useMemo(() => makeTheme(mode), [mode]);
  const loc = useLocation();
  const setMode = (m: PaletteMode) => {
    setModeState(m);
    try {
      localStorage.setItem("lg-theme", m);
    } catch {
      /* ignore */
    }
  };
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.setProperty("--surface", theme.palette.background.paper);
  }, [mode, theme]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <LiveProvider>
        {loc.pathname.startsWith("/handler") ? (
          <Routes>
            <Route path="/handler" element={<HandlerApp />} />
            <Route path="/handler/:id" element={<HandlerApp />} />
          </Routes>
        ) : (
          <Shell mode={mode} setMode={setMode} />
        )}
      </LiveProvider>
    </ThemeProvider>
  );
}
