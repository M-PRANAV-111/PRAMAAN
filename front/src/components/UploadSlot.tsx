import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { api, ApiError, uploadDocument, type JobOut } from "../api/client";
import { invalidate } from "../lib/query";
import { CameraScanner } from "./CameraScanner";
import { cx, useToast } from "./ui";

type State =
  | { kind: "idle" }
  | { kind: "uploading"; fraction: number; name: string }
  | { kind: "processing"; job: JobOut; name: string }
  | { kind: "error"; message: string };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function UploadSlot({ applicationId, docType, label, accept, replacing, onJob }:
  { applicationId: string; docType: string; label: string; accept: string; replacing: boolean; onJob?: (job: JobOut, docId: string, replacing: boolean) => void }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [over, setOver] = useState(false);
  const [scanning, setScanning] = useState(false);
  const input = useRef<HTMLInputElement | null>(null);
  const toast = useToast();

  async function send(file: File) {
    setState({ kind: "uploading", fraction: 0, name: file.name });
    try {
      const res = await uploadDocument(applicationId, docType, file, (f) => setState({ kind: "uploading", fraction: f, name: file.name }));
      let job = res.job;
      onJob?.(job, res.document.id, replacing);
      invalidate(`application:${applicationId}`);
      while (job.state === "QUEUED" || job.state === "RUNNING") {
        setState({ kind: "processing", job, name: file.name });
        await sleep(700);
        job = await api("getJob", { path: { job_id: job.id } });
      }
      invalidate(`application:${applicationId}`);
      invalidate(`findings:${applicationId}`);
      invalidate(`plan:${applicationId}`);
      invalidate(`verifications:${applicationId}`);
      invalidate(`runs:${applicationId}`);
      if (job.state === "FAILED") setState({ kind: "error", message: "The file was stored but could not be read. Try a clearer copy or a different export of the PDF." });
      else { setState({ kind: "idle" }); toast(`${label} checked`); }
    } catch (e) {
      setState({ kind: "error", message: e instanceof ApiError ? e.message : "Upload failed." });
    } finally {
      if (input.current) input.current.value = "";
    }
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void send(f);
  };

  const busy = state.kind === "uploading" || state.kind === "processing";
  return (
    <div onDragOver={(e: DragEvent<HTMLDivElement>) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
      className={cx("rounded-sm border border-dashed px-3 py-2.5 transition-colors", over ? "border-ink bg-sheet" : "border-rule-strong")}>
      <input ref={input} type="file" accept={accept} className="sr-only" id={`up-${docType}`}
        onChange={(e: ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) void send(f); }} disabled={busy} />
      {state.kind === "idle" && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          <label htmlFor={`up-${docType}`} className="btn btn-quiet min-h-9 cursor-pointer px-3">{replacing ? "Replace file" : "Choose file"}</label>
          <button type="button" className="btn btn-quiet min-h-9 px-3" onClick={() => setScanning(true)}>Scan document</button>
          <span className="text-ink-soft">or drop it here. {accept.includes("pdf") ? "PDF" : "PNG or JPEG"}, up to 10 MB.</span>
        </div>
      )}
      {scanning && (
        <CameraScanner open={scanning} docType={docType} label={label} accept={accept}
          onClose={() => setScanning(false)} onSubmitFile={(f) => void send(f)} />
      )}
      {busy && (
        <div className="grid gap-1.5 text-sm" aria-live="polite">
          <div className="flex justify-between gap-3">
            <span className="truncate font-semibold">{state.name}</span>
            <span className="shrink-0 text-ink-soft">
              {state.kind === "uploading" ? `Uploading ${Math.round(state.fraction * 100)}%` : state.job.stage}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-rule">
            <div className="h-full rounded-full bg-ink transition-[width] duration-300"
              style={{ width: `${state.kind === "uploading" ? state.fraction * 30 : 30 + state.job.progress * 0.7}%` }} />
          </div>
        </div>
      )}
      {state.kind === "error" && (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-tape">{state.message}</span>
          <button className="btn btn-quiet min-h-9 px-3" onClick={() => setState({ kind: "idle" })}>Choose another file</button>
        </div>
      )}
    </div>
  );
}
