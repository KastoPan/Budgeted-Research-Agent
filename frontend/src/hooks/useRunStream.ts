import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { runsApi } from "../lib/api";
import type { ActionRecord, StoredRun } from "../lib/types";

export type StreamState = "idle" | "connecting" | "connected" | "reconnecting";

export function useRunStream(runId: string, enabled: boolean): StreamState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<StreamState>(enabled ? "connecting" : "idle");

  useEffect(() => {
    if (!runId || !enabled) {
      setState("idle");
      return;
    }

    setState("connecting");
    const source = new EventSource(runsApi.eventsStreamUrl(runId));

    source.onopen = () => setState("connected");
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) {
        setState("reconnecting");
      }
    };
    source.addEventListener("run", (event) => {
      const run = parseEvent<StoredRun>(event);
      if (!run) return;
      queryClient.setQueryData(["runs", runId], run);
      queryClient.setQueryData<StoredRun[]>(["runs"], (current) =>
        current?.map((item) => (item.run_id === runId ? run : item)),
      );
      if (run.status !== "pending" && run.status !== "running") {
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
        void queryClient.invalidateQueries({ queryKey: ["runs", runId, "evidence"] });
        void queryClient.invalidateQueries({ queryKey: ["runs", runId, "report"] });
      }
    });
    source.addEventListener("action", (event) => {
      const action = parseEvent<ActionRecord>(event);
      if (!action) return;
      queryClient.setQueryData<ActionRecord[]>(
        ["runs", runId, "events"],
        (current = []) => {
          const withoutDuplicate = current.filter(
            (item) => item.sequence !== action.sequence,
          );
          return [...withoutDuplicate, action].sort(
            (left, right) => left.sequence - right.sequence,
          );
        },
      );
    });

    return () => source.close();
  }, [enabled, queryClient, runId]);

  return state;
}

function parseEvent<T>(event: Event): T | null {
  try {
    return JSON.parse((event as MessageEvent<string>).data) as T;
  } catch {
    return null;
  }
}
