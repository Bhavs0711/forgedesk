import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import NewProjectModal from "../components/NewProjectModal";
import { Empty, ErrorState, Loading, PageHeader, ProgressBar, STATUS_COLOR, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { STATUSES } from "../lib/types";
import type { Project } from "../lib/types";

function AgentCell({ id }: { id: number }) {
  const q = useQuery({ queryKey: ["agent", id], queryFn: () => api.agent(id), refetchInterval: 10000 });
  return q.data ? <StatusBadge status={q.data.state} /> : <span className="text-zinc-400">–</span>;
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return <div className="card px-4 py-3"><div className="label mb-0">{label}</div><div className="mt-1 font-mono text-2xl">{value}</div></div>;
}

export default function Dashboard() {
  const [creating, setCreating] = useState(false);
  const q = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const projects: Project[] = q.data ?? [];
  const totals = projects.reduce((a, p) => ({ features: a.features + (p.progress?.total ?? 0), done: a.done + (p.progress?.completed ?? 0) }), { features: 0, done: 0 });
  const chart = projects.filter((p) => p.progress?.total).map((p) => ({ name: p.name, ...p.progress }));

  return (
    <>
      <PageHeader title="Dashboard" actions={<button className="btn btn-primary" onClick={() => setCreating(true)}>New project</button>} />
      <div className="space-y-6 p-6">
        {q.isLoading && <Loading />}
        {q.isError && <ErrorState error={q.error} retry={() => q.refetch()} />}
        {q.isSuccess && projects.length === 0 && (
          <Empty title="No projects yet">Create a project with a specification and ForgeDesk will plan its features.</Empty>
        )}
        {projects.length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Projects" value={projects.length} />
              <Stat label="Features" value={totals.features} />
              <Stat label="Completed" value={totals.done} />
              <Stat label="Overall" value={totals.features ? `${Math.round((100 * totals.done) / totals.features)}%` : "–"} />
            </div>
            {chart.length > 0 && (
              <section className="card p-4" aria-label="Feature status by project">
                <h2 className="mb-3 text-sm font-semibold">Features by status</h2>
                <ResponsiveContainer width="100%" height={Math.max(120, chart.length * 44 + 50)}>
                  <BarChart data={chart} layout="vertical" margin={{ left: 8 }}>
                    <CartesianGrid horizontal={false} stroke="#e4e4e7" />
                    <XAxis type="number" allowDecimals={false} fontSize={12} />
                    <YAxis type="category" dataKey="name" width={110} fontSize={12} />
                    <Tooltip />
                    <Legend />
                    {STATUSES.map((s) => <Bar key={s} dataKey={s} stackId="a" fill={STATUS_COLOR[s]} name={s.replace("_", " ")} />)}
                  </BarChart>
                </ResponsiveContainer>
              </section>
            )}
            <section className="card overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                  <tr><th className="px-4 py-2">Project</th><th className="px-4 py-2">Agent</th><th className="px-4 py-2 w-1/3">Progress</th><th className="px-4 py-2">Done</th></tr>
                </thead>
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id} className="border-b border-zinc-100 last:border-0">
                      <td className="px-4 py-2"><Link className="font-medium hover:underline" to={`/projects/${p.id}`}>{p.name}</Link>
                        <div className="truncate font-mono text-xs text-zinc-400">{p.path}</div></td>
                      <td className="px-4 py-2"><AgentCell id={p.id} /></td>
                      <td className="px-4 py-2">{p.progress && p.progress.total > 0 ? <ProgressBar progress={p.progress} /> : <span className="text-xs text-zinc-400">not planned yet</span>}</td>
                      <td className="px-4 py-2 font-mono">{p.progress ? `${p.progress.completed}/${p.progress.total}` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>
      {creating && <NewProjectModal onClose={() => setCreating(false)} />}
    </>
  );
}
