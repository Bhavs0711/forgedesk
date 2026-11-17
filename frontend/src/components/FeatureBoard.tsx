import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";
import { duration } from "../lib/format";
import { STATUSES } from "../lib/types";
import type { Feature, FeatureStatus } from "../lib/types";
import { Empty, StatusBadge } from "./ui";

export function groupByStatus(features: Feature[]): Record<FeatureStatus, Feature[]> {
  const out = Object.fromEntries(STATUSES.map((s) => [s, [] as Feature[]])) as Record<FeatureStatus, Feature[]>;
  for (const f of features) out[f.status].push(f);
  return out;
}

function Card({ f, projectId, titles }: { f: Feature; projectId: number; titles: Map<number, string> }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const set = useMutation({
    mutationFn: (s: FeatureStatus) => api.setStatus(projectId, f.id, s),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["features", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); },
  });
  return (
    <li className="rounded border border-zinc-200 bg-white p-2.5 text-sm">
      <button className="w-full text-left font-medium" aria-expanded={open} onClick={() => setOpen(!open)}>{f.title}</button>
      <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[11px] text-zinc-500">
        <span>#{f.id}</span><span>p{f.priority}</span>{f.attempts > 0 && <span>{f.attempts} attempt{f.attempts > 1 ? "s" : ""}</span>}
        {f.seconds_spent > 0 && <span>{duration(f.seconds_spent)}</span>}
      </div>
      {f.failure_reason && <p className="mt-1 text-xs text-red-700">{f.failure_reason}</p>}
      {open && (
        <div className="mt-2 space-y-2 border-t border-zinc-100 pt-2">
          {f.description && <p className="text-xs text-zinc-700">{f.description}</p>}
          {f.acceptance_criteria.length > 0 && <ul className="list-disc pl-4 text-xs text-zinc-600">{f.acceptance_criteria.map((c, i) => <li key={i}>{c}</li>)}</ul>}
          {f.depends_on.length > 0 && <p className="text-xs text-zinc-500">Needs: {f.depends_on.map((d) => titles.get(d) ?? `#${d}`).join(", ")}</p>}
          {f.status !== "in_progress" && (
            <select aria-label={`Set status of ${f.title}`} className="input !w-auto text-xs" value={f.status}
              onChange={(e) => set.mutate(e.target.value as FeatureStatus)} disabled={set.isPending}>
              {STATUSES.filter((s) => s !== "in_progress").map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
            </select>
          )}
          {set.isError && <p role="alert" className="text-xs text-red-700">{(set.error as Error).message}</p>}
        </div>
      )}
    </li>
  );
}

export default function FeatureBoard({ features, projectId }: { features: Feature[]; projectId: number }) {
  if (features.length === 0) return <Empty title="No features yet">Start the agent to plan features from the specification, or add one manually.</Empty>;
  const groups = groupByStatus(features);
  const titles = new Map(features.map((f) => [f.id, f.title]));
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {STATUSES.map((s) => (
        <section key={s} aria-label={`${s} features`} className="min-w-0 rounded bg-zinc-100 p-2">
          <h3 className="mb-2 flex items-center justify-between px-1 text-xs"><StatusBadge status={s} /><span className="font-mono text-zinc-500">{groups[s].length}</span></h3>
          <ul className="space-y-2">{groups[s].map((f) => <Card key={f.id} f={f} projectId={projectId} titles={titles} />)}</ul>
        </section>
      ))}
    </div>
  );
}
