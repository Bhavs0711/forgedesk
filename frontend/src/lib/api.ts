import type { AgentEvent, AgentStatus, Approval, Feature, FeatureStatus, GitInfo, Project, Session, Settings, TestRun } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try { const body = await res.json(); detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail); } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  projects: () => req<Project[]>("/api/projects"),
  project: (id: number) => req<Project>(`/api/projects/${id}`),
  createProject: (b: { name: string; path: string; description: string; specification: string; test_command: string; import_existing: boolean }) => req<Project>("/api/projects", json("POST", b)),
  updateProject: (id: number, b: Partial<Pick<Project, "description" | "specification" | "test_command">>) => req<Project>(`/api/projects/${id}`, json("PATCH", b)),
  deleteProject: (id: number) => req<void>(`/api/projects/${id}`, json("DELETE")),
  features: (id: number) => req<Feature[]>(`/api/projects/${id}/features`),
  addFeature: (id: number, b: { title: string; description: string; acceptance_criteria: string[] }) => req<Feature>(`/api/projects/${id}/features`, json("POST", b)),
  setStatus: (id: number, fid: number, status: FeatureStatus) => req<Feature>(`/api/projects/${id}/features/${fid}/status`, json("PUT", { status })),
  addDep: (id: number, fid: number, dep: number) => req<void>(`/api/projects/${id}/features/${fid}/dependencies/${dep}`, json("PUT")),
  removeDep: (id: number, fid: number, dep: number) => req<void>(`/api/projects/${id}/features/${fid}/dependencies/${dep}`, json("DELETE")),
  sessions: (id: number) => req<Session[]>(`/api/projects/${id}/sessions`),
  events: (id: number) => req<AgentEvent[]>(`/api/projects/${id}/events?limit=300`),
  tests: (id: number) => req<TestRun[]>(`/api/projects/${id}/tests`),
  runRegression: (id: number) => req<TestRun>(`/api/projects/${id}/regression`, json("POST")),
  git: (id: number) => req<GitInfo>(`/api/projects/${id}/git`),
  gitInit: (id: number) => req<void>(`/api/projects/${id}/git/init`, json("POST")),
  agent: (id: number) => req<AgentStatus>(`/api/projects/${id}/agent`),
  agentAction: (id: number, action: "start" | "pause" | "resume" | "stop") => req<AgentStatus>(`/api/projects/${id}/agent/${action}`, json("POST")),
  approvals: (id: number) => req<Approval[]>(`/api/projects/${id}/approvals`),
  decide: (approvalId: number, decision: "approve" | "deny") => req<void>(`/api/approvals/${approvalId}/${decision}`, json("POST")),
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (b: Partial<Settings>) => req<Settings>("/api/settings", json("PUT", b)),
};
