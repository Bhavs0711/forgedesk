import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export type SocketState = "connecting" | "open" | "closed";
export interface LiveMessage { type: string; project_id: number; data: Record<string, unknown> }

/** Subscribes to a project's live feed, reconnects with backoff, and invalidates the matching queries. */
export function useProjectSocket(projectId: number, onMessage?: (m: LiveMessage) => void): SocketState {
  const qc = useQueryClient();
  const [state, setState] = useState<SocketState>("connecting");
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/projects/${projectId}`);
      setState("connecting");
      ws.onopen = () => { attempt = 0; setState("open"); };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as LiveMessage;
        handler.current?.(msg);
        const keys: Record<string, (string | number)[][]> = {
          agent_status: [["agent", projectId]],
          features_changed: [["features", projectId], ["project", projectId], ["projects"]],
          progress: [["project", projectId], ["projects"], ["sessions", projectId]],
          test_result: [["tests", projectId]],
          approval_requested: [["approvals", projectId]],
          approval_resolved: [["approvals", projectId]],
        };
        for (const k of keys[msg.type] ?? []) qc.invalidateQueries({ queryKey: k });
      };
      ws.onclose = () => {
        setState("closed");
        if (disposed) return;
        attempt += 1;
        timer = window.setTimeout(connect, Math.min(15000, 500 * 2 ** attempt));
      };
    };
    connect();
    return () => { disposed = true; window.clearTimeout(timer); ws?.close(); };
  }, [projectId, qc]);

  return state;
}
