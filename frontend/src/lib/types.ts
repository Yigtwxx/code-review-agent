/**
 * Mirrors the backend response schemas (`backend/app/schemas/`).
 * Kept hand-written rather than generated so the shapes the UI actually
 * consumes stay small and readable.
 */

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type Origin = 'static' | 'llm' | 'hybrid';
export type FindingStatus = 'open' | 'resolved' | 'dismissed';
export type ReviewStatus = 'queued' | 'running' | 'completed' | 'failed';
export type Layer = 'frontend' | 'backend' | 'database' | 'config_infra' | 'generic';
export type Lens = 'security' | 'quality';

export interface UserPreferences {
  llm_model: string | undefined;
  min_severity: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  preferences: UserPreferences;
  has_github_token: boolean;
}

export interface ReviewSource {
  kind: 'upload' | 'paste' | 'pull_request' | 'ci';
  label: string;
  repo: string | undefined;
  pr_number: number | undefined;
  commit_sha: string | undefined;
}

export interface ReviewStats {
  total_findings: number;
  by_severity: Record<string, number>;
  by_layer: Record<string, number>;
  by_origin: Record<string, number>;
  files_analysed: number;
  suppressed_low_confidence: number;
}

export interface ReviewSummary {
  id: string;
  status: ReviewStatus;
  source: ReviewSource;
  llm_model: string;
  risk_score: number;
  stats: ReviewStats;
  error: string | undefined;
  duration_ms: number | undefined;
  created_at: string;
  finished_at: string | undefined;
}

export interface ReviewFileSummary {
  path: string;
  language: string;
  layers: string[];
  line_count: number;
  truncated: boolean;
  finding_count: number;
}

export interface ReviewDetail extends ReviewSummary {
  files: ReviewFileSummary[];
}

export interface Finding {
  id: string;
  file_path: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  category: string;
  title: string;
  explanation: string;
  suggested_fix: string | undefined;
  owasp: string | undefined;
  cwe: string | undefined;
  origin: Origin;
  tool: string | undefined;
  rule_id: string | undefined;
  agent: string | undefined;
  lens: Lens | undefined;
  layer: Layer | undefined;
  confidence: number;
  corroborated_by: string[];
  status: FindingStatus;
}

export interface DiffHunk {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  changed_lines: number[];
}

export interface FileContent {
  path: string;
  language: string;
  layers: string[];
  content: string;
  hunks: DiffHunk[] | undefined;
  truncated: boolean;
}

export interface Patch {
  file_path: string;
  refactored_code: string;
  unified_diff: string;
  addresses_findings: number;
  validated: boolean;
  validation_output: string;
}

export interface Capabilities {
  default_model: string;
  available_models: string[];
  ollama_reachable: boolean;
  static_analysers: string[];
  max_upload_mb: number;
  max_files_per_review: number;
}

export type ReviewEventType =
  | 'review_started'
  | 'node_started'
  | 'node_finished'
  | 'finding'
  | 'patch'
  | 'review_completed'
  | 'review_failed';

export interface ReviewEvent {
  type: ReviewEventType;
  review_id: string;
  stage: string;
  message: string;
  payload: Record<string, unknown>;
}
