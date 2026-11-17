import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ErrorState, Loading, PageHeader } from "../components/ui";
import { api } from "../lib/api";
import type { Settings } from "../lib/types";

export default function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<Settings | null>(null);
  useEffect(() => { if (q.data) setForm(q.data); }, [q.data]);
  const save = useMutation({
    mutationFn: (s: Settings) => api.saveSettings({ model: s.model, max_session_minutes: s.max_session_minutes, max_turns_per_session: s.max_turns_per_session, max_consecutive_failures: s.max_consecutive_failures, auto_commit: s.auto_commit }),
    onSuccess: (s) => qc.setQueryData(["settings"], s),
  });
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data || !form) return <ErrorState error={q.error} retry={() => q.refetch()} />;
  const num = (k: "max_session_minutes" | "max_turns_per_session" | "max_consecutive_failures", label: string) => (
    <div><label className="label" htmlFor={k}>{label}</label>
      <input id={k} type="number" min={1} className="input font-mono" value={form[k]} onChange={(e) => setForm({ ...form, [k]: Number(e.target.value) })} /></div>
  );
  return (
    <>
      <PageHeader title="Settings" />
      <div className="max-w-2xl space-y-6 p-6">
        <section className="card p-4">
          <h2 className="mb-2 text-sm font-semibold">Anthropic authentication</h2>
          <p className="text-sm">API key: <span className={`font-mono ${q.data.api_key_configured ? "text-green-700" : "text-red-700"}`}>{q.data.api_key_configured ? "configured" : "not configured"}</span></p>
          <p className="mt-2 text-xs text-zinc-500">The key is read from the server's <code className="font-mono">ANTHROPIC_API_KEY</code> environment variable and is never sent to the browser. Set it in <code className="font-mono">.env</code> and restart the backend. Claude subscription credentials are not used.</p>
        </section>
        <section className="card p-4">
          <h2 className="mb-2 text-sm font-semibold">Security</h2>
          <p className="text-sm">Docker isolation: <span className="font-mono">{q.data.docker_enabled ? (q.data.docker_available ? "enabled" : "enabled, but docker not found; falling back to host") : "disabled"}</span></p>
          {!q.data.docker_enabled || !q.data.docker_available ? <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">Test commands run directly on this host. Path confinement and command approval reduce risk but are not a sandbox.</p> : <p className="mt-2 text-xs text-zinc-500">Project test commands run in a container with networking disabled. Agent shell commands still run on the host under the approval policy.</p>}
          <p className="label mt-3">Authorized workspace roots</p>
          <ul className="font-mono text-xs">{q.data.workspace_roots.map((r) => <li key={r}>{r}</li>)}</ul>
          <p className="mt-1 text-xs text-zinc-500">Change with <code className="font-mono">FORGEDESK_WORKSPACE_ROOTS</code>.</p>
        </section>
        <form className="card space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); save.mutate(form); }}>
          <h2 className="text-sm font-semibold">Execution</h2>
          <div><label className="label" htmlFor="model">Model</label><input id="model" className="input font-mono" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {num("max_session_minutes", "Minutes per feature")}{num("max_turns_per_session", "Max turns")}{num("max_consecutive_failures", "Failures before stop")}
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.auto_commit} onChange={(e) => setForm({ ...form, auto_commit: e.target.checked })} />Commit to git after each completed feature</label>
          {save.isError && <p role="alert" className="text-sm text-red-700">{(save.error as Error).message}</p>}
          <div className="flex items-center gap-3"><button className="btn btn-primary" disabled={save.isPending}>Save</button>{save.isSuccess && <span className="text-sm text-zinc-500">Saved</span>}</div>
        </form>
      </div>
    </>
  );
}
