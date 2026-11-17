import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorState, Loading, PageHeader, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { clock, dateTime, duration, sessionSeconds, usd } from "../lib/format";
import type { AgentEvent } from "../lib/types";
import { useProjectSocket } from "../lib/useProjectSocket";

const LEVEL: Record<string, string> = { info: "text-zinc-300", warn: "text-amber-300", error: "text-red-400" };

export default function AgentMonitor() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.project(id) });
  const agent = useQuery({ queryKey: ["agent", id], queryFn: () => api.agent(id) });
  const features = useQuery({ queryKey: ["features", id], queryFn: () => api.features(id) });
  const sessions = useQuery({ queryKey: ["sessions", id], queryFn: () => api.sessions(id) });
  const approvals = useQuery({ queryKey: ["approvals", id], queryFn: () => api.approvals(id) });
  const history = useQuery({ queryKey: ["events", id], queryFn: () => api.events(id), staleTime: Infinity });
  const [live, setLive] = useState<AgentEvent[]>([]);
  const [follow, setFollow] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  const socket = useProjectSocket(id, (m) => {
    if (m.type === "log" || m.type === "test_result" || m.type === "approval_requested") {
      const d = m.data as unknown as AgentEvent;
      setLive((cur) => [...cur.slice(-499), d]);
    }
  });
  const control = useMutation({
    mutationFn: (a: "start" | "pause" | "resume" | "stop") => api.agentAction(id, a),
    onSettled: () => qc.invalidateQueries({ queryKey: ["agent", id] }),
  });
  const decide = useMutation({ mutationFn: (v: { id: number; d: "approve" | "deny" }) => api.decide(v.id, v.d), onSettled: () => qc.invalidateQueries({ queryKey: ["approvals", id] }) });

  const seen = new Set((history.data ?? []).map((e) => e.id));
  const events = [...(history.data ?? []), ...live.filter((e) => !seen.has(e.id))];
  useEffect(() => { if (follow && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [events.length, follow]);

  if (project.isLoading || agent.isLoading) return <Loading />;
  if (project.isError || agent.isError || !agent.data || !project.data) return <ErrorState error={project.error ?? agent.error} />;
  const st = agent.data.state;
  const current = features.data?.find((f) => f.id === agent.data!.feature_id);

  return (
    <>
      <PageHeader title={`${project.data.name} · agent`} subtitle={<Link className="hover:underline" to={`/projects/${id}`}>← Workspace</Link>}
        actions={<>
          <span className={`font-mono text-xs ${socket === "open" ? "text-green-700" : "text-amber-700"}`} aria-label={`Live connection ${socket}`}>● {socket === "open" ? "live" : socket}</span>
          <StatusBadge status={st} />
          {st === "idle" && <button className="btn btn-primary" disabled={control.isPending} onClick={() => control.mutate("start")}>Start</button>}
          {st === "running" && <button className="btn" onClick={() => control.mutate("pause")}>Pause</button>}
          {st === "paused" && <button className="btn" onClick={() => control.mutate("resume")}>Resume</button>}
          {(st === "running" || st === "paused") && <button className="btn btn-danger" onClick={() => control.mutate("stop")}>Stop</button>}
        </>} />
      <div className="space-y-4 p-6">
        {control.isError && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{(control.error as Error).message}</p>}

        {(approvals.data ?? []).map((a) => (
          <div key={a.id} role="alertdialog" aria-label="Approval required" className="rounded border border-amber-300 bg-amber-50 p-4">
            <p className="text-sm font-medium text-amber-900">The agent wants to run a command that needs your approval</p>
            <p className="mt-1 text-xs text-amber-800">{a.reason}</p>
            <pre className="mt-2 overflow-x-auto rounded bg-white p-2 font-mono text-xs">{a.command}</pre>
            <div className="mt-3 flex gap-2"><button className="btn btn-primary" onClick={() => decide.mutate({ id: a.id, d: "approve" })}>Approve</button><button className="btn" onClick={() => decide.mutate({ id: a.id, d: "deny" })}>Deny</button></div>
          </div>))}

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="card p-3 md:col-span-2"><div className="label">Current activity</div>
            <p className="text-sm">{current ? <>#{current.id} {current.title} <span className="font-mono text-xs text-zinc-500">attempt {current.attempts}</span></> : st === "idle" ? "Idle" : "Between features"}</p></div>
          <div className="card p-3"><div className="label">Consecutive failures</div><p className="font-mono text-lg">{agent.data.consecutive_failures}</p></div>
        </div>

        <section className="card overflow-hidden" aria-label="Execution log">
          <div className="flex items-center justify-between border-b border-zinc-200 px-3 py-2"><h2 className="text-sm font-semibold">Execution log</h2>
            <label className="flex items-center gap-1.5 text-xs text-zinc-500"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />Follow</label></div>
          <div ref={logRef} className="h-96 overflow-auto bg-zinc-900 p-3 font-mono text-xs leading-5" role="log">
            {history.isLoading && <p className="text-zinc-500">Loading…</p>}
            {history.isError && <p className="text-red-400">Could not load history: {(history.error as Error).message}</p>}
            {history.isSuccess && events.length === 0 && <p className="text-zinc-500">No activity recorded yet.</p>}
            {events.map((e) => <div key={e.id} className={`whitespace-pre-wrap break-words ${LEVEL[e.level] ?? LEVEL.info}`}><span className="text-zinc-500">{clock(e.at)} {e.kind.padEnd(9)}</span> {e.message}</div>)}
          </div>
        </section>

        <section><h2 className="mb-2 text-sm font-semibold">Session history</h2>
          {sessions.isLoading ? <Loading /> : (sessions.data ?? []).length === 0 ? <p className="text-sm text-zinc-500">No sessions yet.</p> : (
            <div className="card overflow-x-auto"><table className="w-full text-left text-sm"><tbody>{sessions.data!.slice(0, 15).map((s) => (
              <tr key={s.id} className="border-b border-zinc-100 last:border-0"><td className="px-3 py-1.5 font-mono">#{s.id}</td><td className="px-3 py-1.5">{s.kind}</td><td className="px-3 py-1.5"><StatusBadge status={s.status} /></td><td className="px-3 py-1.5 truncate text-xs">{features.data?.find((f) => f.id === s.feature_id)?.title ?? ""}</td><td className="px-3 py-1.5 font-mono text-xs">{dateTime(s.started_at)}</td><td className="px-3 py-1.5 font-mono text-xs">{duration(sessionSeconds(s))}</td><td className="px-3 py-1.5 font-mono text-xs">{usd(s.cost_usd)}</td></tr>))}</tbody></table></div>)}
        </section>
      </div>
    </>
  );
}
