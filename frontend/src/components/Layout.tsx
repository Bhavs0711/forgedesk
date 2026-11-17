import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../lib/api";

const link = ({ isActive }: { isActive: boolean }) =>
  `block truncate rounded px-2 py-1.5 text-sm ${isActive ? "bg-zinc-200 font-medium text-zinc-900" : "text-zinc-600 hover:bg-zinc-100"}`;

export default function Layout() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="shrink-0 border-b border-zinc-200 bg-white p-3 md:w-56 md:border-b-0 md:border-r">
        <div className="mb-3 px-2 font-mono text-sm font-semibold tracking-tight">forgedesk</div>
        <nav className="flex gap-1 md:flex-col" aria-label="Main">
          <NavLink to="/" end className={link}>Dashboard</NavLink>
          <NavLink to="/settings" className={link}>Settings</NavLink>
        </nav>
        <div className="mt-4 hidden md:block">
          <div className="label px-2">Projects</div>
          {projects.isLoading && <p className="px-2 text-xs text-zinc-400">Loading…</p>}
          {projects.data?.length === 0 && <p className="px-2 text-xs text-zinc-400">None yet</p>}
          <nav className="flex flex-col gap-0.5" aria-label="Projects">
            {projects.data?.map((p) => <NavLink key={p.id} to={`/projects/${p.id}`} className={link}>{p.name}</NavLink>)}
          </nav>
        </div>
      </aside>
      <main className="min-w-0 flex-1"><Outlet /></main>
    </div>
  );
}
