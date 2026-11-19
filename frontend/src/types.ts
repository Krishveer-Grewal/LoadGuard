export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type TrailerStatus = "Good" | "Warning" | "Hazard" | "Offline";

export interface BBox { x: number; y: number; width: number; height: number }

export interface Detection {
  id: number;
  class: string;
  confidence: number;
  bbox: BBox;
  angle: number;
  source: string;
  protrusion?: number;
}

export interface Issue {
  id: number;
  rule: string;
  code: string;
  severity: Severity;
  key: string;
  region: BBox;
  marker: { x: number; y: number };
  arrow?: { x1: number; y1: number; x2: number; y2: number };
  packageIds: number[];
  data: Record<string, unknown>;
  title: string;
  issue: string;
  reason: string;
  risk: string;
  recommendation: string;
  shortMessage: string;
}

export interface RuleResult {
  rule: string;
  name: string;
  score: number | null;
  status: "PASS" | "WARNING" | "FAIL" | "N/A";
  metrics: Record<string, unknown>;
  issueCount: number;
  weight: number;
  explanation: string;
}

export interface Seam { x: number; yTop: number; yBottom: number; layers: number; packageIds: number[] }
export interface Void { id: number; area: number; kind: string; severity: Severity; bbox: BBox; relativeSize: number }

export interface WallModel {
  rows: { index: number; packageIds: number[]; topY: number; bottomY: number }[];
  columns: { index: number; packageIds: number[]; x: number }[];
  packages: (Detection & { layer: number; supportRatio: number; supportedBy: number[]; onFloor: boolean })[];
  seams: Seam[];
  voids: Void[];
  metrics: Record<string, number | boolean | number[]>;
}

export interface AnalysisResult {
  trailerId?: string;
  timestamp: number;
  imageSize: { width: number; height: number };
  detections: Detection[];
  wall: WallModel;
  rules: RuleResult[];
  issues: Issue[];
  wallScore: number;
  grade: string;
  status: TrailerStatus;
  collapseRisk: number;
  scoreBreakdown: { rule: string; weight: number; score: number | null; pointsLost: number }[];
  riskFactors: { factor: string; contribution: number }[];
  summary: string;
  meta: { wall_seq?: number; placed?: number; total?: number; complete?: boolean };
  timing: { detectMs: number; analyzeMs: number; totalMs: number };
  image?: string;
  annotatedImage?: string;
}

export interface Handler { id: number; name: string; badge: string }

export interface TrailerSummary {
  trailerId: string;
  door: number;
  handlerId: number | null;
  handler?: Handler | null;
  sourceType: string;
  sourceUri?: string | null;
  simSkill?: number;
  active?: boolean;
  online: boolean;
  sourceError?: string | null;
  wallScore: number | null;
  grade: string | null;
  status: TrailerStatus;
  collapseRisk: number | null;
  issueCount: number;
  highCount: number;
  topIssue: string | null;
  activeAlerts: number;
  packages: number;
  wallSeq: number | null;
  progress: number | null;
  latencyMs: number | null;
  updatedAt: number | null;
  latest?: AnalysisResult | null;
}

export interface Alert {
  id: number;
  trailerId: string;
  handlerId: number | null;
  timestamp: string;
  severity: Severity;
  rule: string;
  code: string;
  message: string;
  detail: Issue;
  status: "active" | "acknowledged" | "resolved";
  wallScore: number;
  acknowledgedAt: string | null;
  acknowledgedBy: string | null;
  resolvedAt: string | null;
  hasSnapshot: boolean;
}
