import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import FeatureBoard from "../components/FeatureBoard";
import { Empty, ErrorState, Loading, PageHeader, ProgressBar, STATUS_COLOR, StatusBadge } from "../components/ui";
import { api } from "../lib/api";
import { dateTime, duration, sessionSeconds, usd } from "../lib/format";
import type { Feature, Project } from "../lib/types";

const TABS = ["spec", "board", "dependencies", "history", "tests"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = { spec: "Specification", board: "Feature board", dependencies: "Dependencies", history: "History", tests: "Test results" };

function Spec({ p }: { p: Project }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ description: p.description, specification: p.specification, test_command: p.test_command });
  const save = useMutation({ mutationFn: () => api.updateProject(p.id, form), onSuccess: () => qc.invalidateQueries({ queryKey: ["project", p.id] }) });
  return (
    <form className="max-w-3xl space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div><label className="label" htmlFor="desc">Description</label><input id="desc" className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
      <div><label className="label" htmlFor="spec">Specification</label>
        <textarea id="spec" className="input h-72 font-mono" value={form.specification} onChange={(e) => setForm({ ...form, specification: e.target.value })} />
        <p className="mt-1 text-xs text-zinc-500">{p.initialized ? "Features have been planned from this specification. Editing it does not re-plan; add or edit features on the board." : "When the agent starts, it plans features from this text."}</p></div>
      <div><label className="label" htmlFor="tc">Test command</label><input id="tc" className="input font-mono" placeholder="pytest -q" value={form.test_command} onChange={(e) => setForm({ ...form, test_command: e.target.value })} />
        <p className="mt-1 text-xs text-zinc-500">Run from the project directory. Agents cannot mark a feature complete without a passing run.</p></div>
      {save.isError && <p role="alert" className="text-sm text-red-700">{(save.error as Error).message}</p>}
      <button className="btn btn-primary" disabled={save.isPending}>Save</button>{save.isSuccess && <span className="ml-3 text-sm text-zinc-500">Saved</span>}
    </form>
  );
}

function AddFeature({ projectId }: { projectId: number }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const add = useMutation({
    mutationFn: () => api.addFeature(projectId, { title, description: "", acceptance_criteria: [] }),
    onSuccess: () => { setTitle(""); qc.invalidateQueries({ queryKey: ["features", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); },
  });
  return (
    <form className="mb-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (title.trim()) add.mutate(); }}>
      <input aria-label="New feature title" className="input max-w-sm" placeholder="Add a feature" value={title} onChange={(e) => setTitle(e.target.value)} />
      <button className="btn" disabled={add.isPending || !title.trim()}>Add</button>
      {add.isError && <span role="alert" className="self-center text-sm text-red-700">{(add.error as Error).message}</span>}
    </form>
  );
}

function Dependencies({ features, projectId }: { features: Feature[]; projectId: number }) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["features", projectId] });
  const add = useMutation({ mutationFn: (v: { f: number; d: number }) => api.addDep(projectId, v.f, v.d), onSettled: refresh });
  const remove = useMutation({ mutationFn: (v: { f: number; d: number }) => api.removeDep(projectId, v.f, v.d), onSettled: refresh });
  if (features.length === 0) return <Empty title="No features to connect" />;
  const byId = new Map(features.map((f) => [f.id, f]));
  const ready = (f: Feature) => f.status === "pending" && f.depends_on.every((d) => byId.get(d)?.status === "completed");
  return (
    <div className="space-y-2">
      {add.isError && <p role="alert" className="text-sm text-red-700">{(add.error as Error).message}</p>}
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr><th className="px-3 py-2">Feature</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Depends on</th><th className="px-3 py-2">Schedule</th></tr></thead>
          <tbody>
            {features.map((f) => (
              <tr key={f.id} className="border-b border-zinc-100 align-top last:border-0">
                <td className="px-3 py-2">{f.title}</td>
                <td className="px-3 py-2"><StatusBadge status={f.status} /></td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap items-center gap-1">
                    {f.depends_on.map((d) => (
                      <span key={d} className="inline-flex items-center gap-1 rounded bg-zinc-100 px-1.5 py-0.5 text-xs">{byId.get(d)?.title ?? `#${d}`}
                        <button aria-label={`Remove dependency on ${byId.get(d)?.title}`} className="text-zinc-400 hover:text-red-700" onClick={() => remove.mutate({ f: f.id, d })}>✕</button></span>
                    ))}
                    <select aria-label={`Add dependency for ${f.title}`} className="input !w-auto text-xs" value="" onChange={(e) => e.target.value && add.mutate({ f: f.id, d: Number(e.target.value) })}>
                      <option value="">+ add</option>
                      {features.filter((o) => o.id !== f.id && !f.depends_on.includes(o.id)).map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
                    </select>
                  </div>
                </td>
                <td className="px-3 py-2 text-xs text-zinc-500">{ready(f) ? "ready" : f.status === "pending" ? "waiting on dependencies" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function History({ projectId, features }: { projectId: number; features: Feature[] }) {
  const sessions = useQuery({ queryKey: ["sessions", projectId], queryFn: () => api.sessions(projectId) });
  const git = useQuery({ queryKey: ["git", projectId], queryFn: () => api.git(projectId) });
  const timed = features.filter((f) => f.seconds_spent > 0).map((f) => ({ name: f.title, seconds: Math.round(f.seconds_spent), status: f.status }));
  return (
    <div className="space-y-6">
      <section className="card p-4"><h2 className="mb-3 text-sm font-semibold">Time spent per feature</h2>
        {timed.length === 0 ? <Empty title="No agent time recorded yet" /> : (
          <ResponsiveContainer width="100%" height={Math.max(120, timed.length * 32 + 40)}>
            <BarChart data={timed} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid horizontal={false} stroke="#e4e4e7" /><XAxis type="number" fontSize={12} tickFormatter={(v) => duration(v)} /><YAxis type="category" dataKey="name" width={140} fontSize={12} />
              <Tooltip formatter={(v: number) => duration(v)} />
              <Bar dataKey="seconds" name="time">{timed.map((t) => <Cell key={t.name} fill={STATUS_COLOR[t.status]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>)}
      </section>
      <section><h2 className="mb-2 text-sm font-semibold">Agent sessions</h2>
        {sessions.isLoading ? <Loading /> : sessions.isError ? <ErrorState error={sessions.error} /> : sessions.data!.length === 0 ? <Empty title="No sessions yet" /> : (
          <div className="card overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-zinc-200 text-xs uppercase text-zinc-500"><tr><th className="px-3 py-2">#</th><th className="px-3 py-2">Kind</th><th className="px-3 py-2">Feature</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Started</th><th className="px-3 py-2">Duration</th><th className="px-3 py-2">Turns</th><th className="px-3 py-2">Cost</th></tr></thead>
            <tbody>{sessions.data!.map((s) => (
              <tr key={s.id} className="border-b border-zinc-100 last:border-0"><td className="px-3 py-2 font-mono">{s.id}</td><td className="px-3 py-2">{s.kind}</td><td className="px-3 py-2">{features.find((f) => f.id === s.feature_id)?.title ?? "–"}</td>
                <td className="px-3 py-2"><StatusBadge status={s.status} />{s.error && <div className="mt-1 max-w-xs truncate text-xs text-red-700" title={s.error}>{s.error}</div>}</td>
                <td className="px-3 py-2 text-xs">{dateTime(s.started_at)}</td><td className="px-3 py-2 font-mono text-xs">{duration(sessionSeconds(s))}</td><td className="px-3 py-2 font-mono">{s.turns}</td><td className="px-3 py-2 font-mono">{usd(s.cost_usd)}</td></tr>))}</tbody></table></div>)}
      </section>
      <section><h2 className="mb-2 text-sm font-semibold">Git history</h2>
        {git.isLoading ? <Loading /> : git.isError ? <ErrorState error={git.error} /> : !git.data!.is_repo ? (
          <Empty title="Not a git repository"><button className="btn mt-1" onClick={() => api.gitInit(projectId).then(() => git.refetch())}>git init</button></Empty>
        ) : git.data!.log.length === 0 ? <Empty title="No commits yet" /> : (
          <ul className="card divide-y divide-zinc-100 font-mono text-xs">{git.data!.log.map((c) => <li key={c.hash} className="flex gap-3 px-3 py-1.5"><span className="text-zinc-400">{c.hash}</span><span className="flex-1 truncate">{c.subject}</span><span className="text-zinc-400">{c.author}</span></li>)}</ul>)}
      </section>
    </div>
  );
}

function Tests({ projectId, hasCommand }: { projectId: number; hasCommand: boolean }) {
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["tests", projectId], queryFn: () => api.tests(projectId) });
  const [open, setOpen] = useState<number | null>(null);
  const run = useMutation({ mutationFn: () => api.runRegression(projectId), onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["tests", projectId] }); setOpen(r.id); } });
  const data = [...(runs.data ?? [])].reverse().map((r) => ({ id: `#${r.id}`, seconds: r.duration_seconds, ok: r.exit_code === 0 }));
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3"><button className="btn" disabled={!hasCommand || run.isPending} onClick={() => run.mutate()}>{run.isPending ? "Running…" : "Run regression suite"}</button>
        {!hasCommand && <span className="text-xs text-zinc-500">Set a test command in the Specification tab first.</span>}
        {run.isError && <span role="alert" className="text-sm text-red-700">{(run.error as Error).message}</span>}</div>
      {runs.isLoading ? <Loading /> : runs.isError ? <ErrorState error={runs.error} /> : data.length === 0 ? <Empty title="No test runs recorded" /> : (
        <>
          <section className="card p-4"><h2 className="mb-3 text-sm font-semibold">Duration per run (green passed, red failed)</h2>
            <ResponsiveContainer width="100%" height={160}><BarChart data={data}><CartesianGrid vertical={false} stroke="#e4e4e7" /><XAxis dataKey="id" fontSize={11} /><YAxis fontSize={11} unit="s" /><Tooltip />
              <Bar dataKey="seconds" name="duration (s)">{data.map((d) => <Cell key={d.id} fill={d.ok ? STATUS_COLOR.completed : STATUS_COLOR.failed} />)}</Bar></BarChart></ResponsiveContainer></section>
          <ul className="card divide-y divide-zinc-100 text-sm">{runs.data!.map((r) => (
            <li key={r.id}><button className="flex w-full items-center gap-3 px-3 py-2 text-left" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>
              <span className={`font-mono text-xs ${r.exit_code === 0 ? "text-green-700" : "text-red-700"}`}>{r.exit_code === 0 ? "PASS" : `FAIL ${r.exit_code}`}</span><span className="text-xs text-zinc-500">{r.kind}</span><span className="flex-1 truncate font-mono text-xs">{r.command}</span><span className="font-mono text-xs text-zinc-400">{duration(r.duration_seconds)} · {dateTime(r.at)}</span></button>
              {open === r.id && <pre className="max-h-80 overflow-auto bg-zinc-900 p-3 font-mono text-xs text-zinc-100">{r.output_tail || "(no output)"}</pre>}</li>))}</ul>
        </>)}
    </div>
  );
}

export default function Workspace() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t === params.get("tab")) ?? "board") as Tab;
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.project(id) });
  const features = useQuery({ queryKey: ["features", id], queryFn: () => api.features(id) });
  const agent = useQuery({ queryKey: ["agent", id], queryFn: () => api.agent(id) });
  useEffect(() => { document.title = project.data ? `${project.data.name} · ForgeDesk` : "ForgeDesk"; }, [project.data]);

  if (project.isLoading) return <Loading />;
  if (project.isError || !project.data) return <ErrorState error={project.error} retry={() => project.refetch()} />;
  const p = project.data;
  return (
    <>
      <PageHeader title={p.name} subtitle={<span className="font-mono text-xs">{p.path}</span>}
        actions={<>{agent.data && <StatusBadge status={agent.data.state} />}<Link className="btn" to={`/projects/${id}/agent`}>Agent monitor</Link>
          <a className="btn" href={`/api/projects/${id}/report?format=md`}>Export report</a></>} />
      {p.progress && p.progress.total > 0 && (
        <div className="border-b border-zinc-200 bg-white px-6 pb-3"><div className="mb-1 flex justify-between font-mono text-xs text-zinc-500"><span>{p.progress.completed}/{p.progress.total} completed · {p.progress.failed} failed · {p.progress.blocked} blocked</span><span>{p.progress.percent}%</span></div><ProgressBar progress={p.progress} /></div>)}
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-zinc-200 bg-white px-6">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setParams({ tab: t })}
          className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === t ? "border-zinc-900 font-medium" : "border-transparent text-zinc-500 hover:text-zinc-900"}`}>{TAB_LABEL[t]}</button>)}
      </div>
      <div className="p-6" role="tabpanel">
        {tab === "spec" && <Spec key={p.id} p={p} />}
        {tab !== "spec" && tab !== "tests" && (features.isLoading ? <Loading /> : features.isError ? <ErrorState error={features.error} retry={() => features.refetch()} /> : (
          <>
            {tab === "board" && <><AddFeature projectId={id} /><FeatureBoard features={features.data!} projectId={id} /></>}
            {tab === "dependencies" && <Dependencies features={features.data!} projectId={id} />}
            {tab === "history" && <History projectId={id} features={features.data!} />}
          </>))}
        {tab === "tests" && <Tests projectId={id} hasCommand={!!p.test_command.trim()} />}
      </div>
    </>
  );
}
