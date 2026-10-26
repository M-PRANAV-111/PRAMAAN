import { useEffect, useRef, useState } from "react";
import { api, type JobOut } from "../../api/client";
import { isAiStage, stepOf } from "./stages";

export type JobProgressState = {
  job: JobOut | null;
  state: JobOut["state"];
  step: number;
  stageCode: string | null;
  stageLabel: string;
  progress: number;
  error: string | null;
  slow: boolean;
  aiAssisted: boolean;
};

export function useJobProgress(initialJob: JobOut | null): JobProgressState {
  const [job, setJob] = useState<JobOut | null>(initialJob);
  const [slow, setSlow] = useState(false);
  const [aiSeen, setAiSeen] = useState(false);
  const maxStep = useRef(0);
  const lastStageChange = useRef(Date.now());
  const lastStage = useRef("");

  useEffect(() => {
    setJob(initialJob);
    maxStep.current = initialJob ? stepOf(initialJob) : 0;
    lastStageChange.current = Date.now();
    lastStage.current = initialJob?.stage ?? "";
    setSlow(false);
    setAiSeen(initialJob ? isAiStage(initialJob) : false);
  }, [initialJob?.id]);

  useEffect(() => {
    if (!job || (job.state !== "QUEUED" && job.state !== "RUNNING")) return;
    let active = true;

    async function poll() {
      if (!active || !job || document.visibilityState === "hidden") return;
      try {
        const next = await api("getJob", { path: { job_id: job.id } });
        if (!active) return;
        const s = stepOf(next);
        if (s > maxStep.current) maxStep.current = s;
        if (isAiStage(next)) setAiSeen(true);
        if (next.stage !== lastStage.current || next.state !== "RUNNING") {
          lastStage.current = next.stage;
          lastStageChange.current = Date.now();
          setSlow(false);
        } else if (Date.now() - lastStageChange.current >= 4000) {
          setSlow(true);
        }
        setJob(next);
      } catch {
        // Transient network hiccup during poll; keep last known state and retry next tick.
      }
    }

    const timer = setInterval(poll, 1000);
    const onVis = () => { if (document.visibilityState === "visible") void poll(); };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onVis);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onVis);
    };
  }, [job?.id, job?.state]);

  const rawStep = job ? stepOf(job) : 0;
  const step = Math.max(maxStep.current, rawStep);
  const stageCode = (job as (JobOut & { stage_code?: string | null }) | null)?.stage_code ?? null;
  return {
    job,
    state: job?.state ?? "QUEUED",
    step,
    stageCode,
    stageLabel: job?.stage ?? "Reading file",
    progress: job?.progress ?? 0,
    error: job?.error_message ?? job?.error ?? null,
    slow,
    aiAssisted: aiSeen || (job ? isAiStage(job) : false),
  };
}
