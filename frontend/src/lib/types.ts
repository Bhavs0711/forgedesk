export type FeatureStatus = "pending" | "in_progress" | "completed" | "failed" | "blocked";
export const STATUSES: FeatureStatus[] = ["pending", "in_progress", "completed", "failed", "blocked"];

export interface Progress { pending: number; in_progress: number; completed: number; failed: number; blocked: number; total: number; percent: number }
export interface Project { id: number; name: string; path: string; description: string; specification: string; test_command: string; initialized: boolean; created_at: string; progress?: Progress }
export interface Feature { id: number; project_id: number; title: string; description: string; acceptance_criteria: string[]; priority: number; sequence: number; status: FeatureStatus; attempts: number; failure_reason: string; seconds_spent: number; completed_at: string | null; depends_on: number[] }
export interface Session { id: number; kind: string; status: string; feature_id: number | null; started_at: string; ended_at: string | null; error: string; cost_usd: number; turns: number }
export interface AgentEvent { id: number; session_id: number | null; at: string; level: string; kind: string; message: string }
export interface TestRun { id: number; feature_id: number | null; session_id: number | null; kind: string; command: string; exit_code: number; duration_seconds: number; output_tail: string; at: string }
export interface Approval { id: number; command: string; reason: string; status: string; requested_at: string }
export interface AgentStatus { state: "idle" | "running" | "paused" | "stopping"; session_id: number | null; feature_id: number | null; consecutive_failures: number }
export interface Settings { api_key_configured: boolean; docker_available: boolean; docker_enabled: boolean; workspace_roots: string[]; model: string; max_session_minutes: number; max_turns_per_session: number; max_consecutive_failures: number; auto_commit: boolean }
export interface GitInfo { is_repo: boolean; log: { hash: string; author: string; date: string; subject: string }[]; status: string }
