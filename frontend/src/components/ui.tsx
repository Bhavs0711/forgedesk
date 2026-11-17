import type { ReactNode } from "react";
import { ApiError } from "../lib/api";
import type { FeatureStatus, Progress } from "../lib/types";

const BADGE: Record<string, string> = {
  pending: "border-zinc-300 bg-zinc-100 text-zinc-700",
  in_progress: "border-blue-300 bg-blue-50 text-blue-800",
  completed: "border-green-300 bg-green-50 text-green-800",
  failed: "border-red-300 bg-red-50 text-red-800",
  blocked: "border-amber-300 bg-amber-50 text-amber-800",
  running: "border-blue-300 bg-blue-50 text-blue-800",
  paused: "border-amber-300 bg-amber-50 text-amber-800",
  idle: "border-zinc-300 bg-zinc-100 text-zinc-700",
  stopping: "border-amber-300 bg-amber-50 text-amber-800",
  stopped: "border-zinc-300 bg-zinc-100 text-zinc-700",
  interrupted: "border-amber-300 bg-amber-50 text-amber-800",
};

export const STATUS_COLOR: Record<FeatureStatus, string> = {
  completed: "#16a34a", in_progress: "#2563eb", pending: "#a1a1aa", failed: "#dc2626", blocked: "#d97706",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 font-mono text-[11px] leading-4 ${BADGE[status] ?? BADGE.idle}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function ProgressBar({ progress }: { progress: Progress }) {
  const pct = (n: number) => (progress.total ? (100 * n) / progress.total : 0);
  return (
    <div role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}
      className="flex h-2 w-full overflow-hidden rounded bg-zinc-200">
      <div style={{ width: `${pct(progress.completed)}%`, background: STATUS_COLOR.completed }} />
      <div style={{ width: `${pct(progress.in_progress)}%`, background: STATUS_COLOR.in_progress }} />
      <div style={{ width: `${pct(progress.failed)}%`, background: STATUS_COLOR.failed }} />
      <div style={{ width: `${pct(progress.blocked)}%`, background: STATUS_COLOR.blocked }} />
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p className="p-6 text-sm text-zinc-500" role="status">{label}…</p>;
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof ApiError || error instanceof Error ? error.message : "Unknown error";
  return (
    <div role="alert" className="m-4 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1 font-mono text-xs">{msg}</p>
      {retry && <button className="btn mt-3" onClick={retry}>Retry</button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-zinc-300 p-8 text-center">
      <p className="text-sm font-medium text-zinc-700">{title}</p>
      {children && <div className="mt-2 text-sm text-zinc-500">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200 bg-white px-6 py-4">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold">{title}</h1>
        {subtitle && <div className="mt-0.5 text-sm text-zinc-500">{subtitle}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-20 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16" role="dialog" aria-modal="true" aria-label={title}>
      <div className="card w-full max-w-xl p-5 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button className="text-zinc-500 hover:text-zinc-900" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}
