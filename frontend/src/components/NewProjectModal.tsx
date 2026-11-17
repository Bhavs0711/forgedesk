import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Modal } from "./ui";

export default function NewProjectModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", path: "", description: "", specification: "", test_command: "", import_existing: false });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const create = useMutation({
    mutationFn: () => api.createProject(form),
    onSuccess: (p) => { qc.invalidateQueries({ queryKey: ["projects"] }); onClose(); nav(`/projects/${p.id}`); },
  });

  return (
    <Modal title="New project" onClose={onClose}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div><label className="label" htmlFor="np-name">Name</label>
          <input id="np-name" className="input" required value={form.name} onChange={(e) => set("name", e.target.value)} /></div>
        <div><label className="label" htmlFor="np-path">Directory</label>
          <input id="np-path" className="input font-mono" required placeholder="/path/inside/a/workspace/root" value={form.path} onChange={(e) => set("path", e.target.value)} />
          <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={form.import_existing} onChange={(e) => set("import_existing", e.target.checked)} />Import existing (don't create)</label></div>
        <div><label className="label" htmlFor="np-spec">Specification</label>
          <textarea id="np-spec" className="input h-32" placeholder="What should be built? The agent plans features from this." value={form.specification} onChange={(e) => set("specification", e.target.value)} /></div>
        <div><label className="label" htmlFor="np-test">Test command</label>
          <input id="np-test" className="input font-mono" placeholder="pytest -q" value={form.test_command} onChange={(e) => set("test_command", e.target.value)} /></div>
        {create.error && <p role="alert" className="text-sm text-red-700">{(create.error as Error).message}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}
