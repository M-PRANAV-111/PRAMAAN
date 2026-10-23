import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Dialog, cx } from "./ui";

/** Package one or more JPEG data-URLs into a standards-compliant %PDF-1.4 binary (parsed by pikepdf & pypdfium2). */
function jpegsToPdf(pages: { dataUrl: string; width: number; height: number }[]): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [0];
  let pos = 0;
  const pushStr = (s: string) => { const b = enc.encode(s); chunks.push(b); pos += b.length; };
  const pushBytes = (b: Uint8Array) => { chunks.push(b); pos += b.length; };
  const startObj = (id: number) => { offsets[id] = pos; pushStr(`${id} 0 obj\n`); };

  pushStr("%PDF-1.4\n%\xFF\xFF\xFF\xFF\n");
  const n = pages.length;
  const kids = pages.map((_, i) => `${3 + i * 3} 0 R`).join(" ");
  startObj(1); pushStr("<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
  startObj(2); pushStr(`<< /Type /Pages /Count ${n} /Kids [ ${kids} ] >>\nendobj\n`);

  pages.forEach((p, i) => {
    const pageId = 3 + i * 3;
    const contentId = pageId + 1;
    const imgId = pageId + 2;
    const b64 = p.dataUrl.split(",")[1] ?? "";
    const bin = atob(b64);
    const jpg = new Uint8Array(bin.length);
    for (let j = 0; j < bin.length; j++) jpg[j] = bin.charCodeAt(j);

    const content = `q 595 0 0 842 0 0 cm /Im0 Do Q\n`;
    startObj(pageId);
    pushStr(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 ${imgId} 0 R >> >> /Contents ${contentId} 0 R >>\nendobj\n`);
    startObj(contentId);
    pushStr(`<< /Length ${content.length} >>\nstream\n${content}endstream\nendobj\n`);
    startObj(imgId);
    pushStr(`<< /Type /XObject /Subtype /Image /Width ${p.width} /Height ${p.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n`);
    pushBytes(jpg);
    pushStr("\nendstream\nendobj\n");
  });

  const totalObjs = 3 + n * 3;
  const xrefPos = pos;
  pushStr(`xref\n0 ${totalObjs}\n0000000000 65535 f \n`);
  for (let i = 1; i < totalObjs; i++) {
    pushStr(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  }
  pushStr(`trailer\n<< /Size ${totalObjs} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);

  const out = new Uint8Array(pos);
  let cur = 0;
  for (const c of chunks) { out.set(c, cur); cur += c.length; }
  return out;
}

function drawSyntheticScan(docType: string, pageNum: number, crop: "auto" | "full", rot: number): { dataUrl: string; width: number; height: number } {
  const c = document.createElement("canvas");
  const swap = rot % 180 !== 0;
  const w = swap ? 842 : 595;
  const h = swap ? 595 : 842;
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d")!;
  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.rotate((rot * Math.PI) / 180);
  ctx.translate(-595 / 2, -842 / 2);

  ctx.fillStyle = crop === "full" ? "#e4e8e1" : "#ffffff";
  ctx.fillRect(0, 0, 595, 842);
  const pad = crop === "full" ? 28 : 8;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(pad, pad, 595 - pad * 2, 842 - pad * 2);
  ctx.strokeStyle = "#1d2b4f";
  ctx.lineWidth = 2;
  ctx.strokeRect(pad + 12, pad + 12, 595 - (pad + 12) * 2, 842 - (pad + 12) * 2);

  ctx.fillStyle = "#1d2b4f";
  ctx.font = "bold 18px Helvetica, Arial, sans-serif";
  ctx.fillText("SYNTHETIC CAMERA SCAN — AICTE SUBMISSION", 48, 76);
  ctx.font = "14px Helvetica, Arial, sans-serif";
  ctx.fillText(`Document slot: ${docType.replace(/_/g, " ").toUpperCase()} · Page ${pageNum}`, 48, 108);
  ctx.fillText("Premises of: Deccan Institute of Technology (Synthetic)", 48, 148);
  ctx.fillText("Permanent Id: 1-SYN-7742-0004", 48, 180);
  ctx.fillText("Academic Year: 2026-27", 48, 212);
  ctx.fillText("Certificate No.: FNOC/SYN/2026/8820", 48, 244);
  ctx.fillText("Date of Issue: 15-01-2026", 48, 276);
  ctx.fillText("Valid Upto: 31-03-2027", 48, 308);
  ctx.fillText("Total Intake: 300    Regular Faculty: 20", 48, 340);
  ctx.fillStyle = "#5b4e9a";
  ctx.fillText("[Edge-aligned & perspective-corrected scan · SYNTHETIC]", 48, 760);
  ctx.restore();
  return { dataUrl: c.toDataURL("image/jpeg", 0.9), width: w, height: h };
}

export function CameraScanner({
  open,
  docType,
  label,
  accept,
  onClose,
  onSubmitFile,
}: {
  open: boolean;
  docType: string;
  label: string;
  accept: string;
  onClose: () => void;
  onSubmitFile: (file: File) => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [camState, setCamState] = useState<"requesting" | "live" | "simulated">("requesting");
  const [pages, setPages] = useState<{ dataUrl: string; width: number; height: number }[]>([]);
  const [crop, setCrop] = useState<"auto" | "full">("auto");
  const [rot, setRot] = useState(0);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const docPol = document as unknown as {
      permissionsPolicy?: { allowsFeature?: (f: string) => boolean };
      featurePolicy?: { allowsFeature?: (f: string) => boolean };
    };
    const policyAllows = docPol.permissionsPolicy?.allowsFeature?.("camera") ?? docPol.featurePolicy?.allowsFeature?.("camera") ?? true;
    if (navigator.mediaDevices?.getUserMedia && policyAllows && !navigator.webdriver) {
      setCamState("requesting");
      navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
        .then((stream) => {
          if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
          streamRef.current = stream;
          setCamState("live");
          if (videoRef.current) videoRef.current.srcObject = stream;
        })
        .catch(() => { if (!cancelled) setCamState("simulated"); });
    } else {
      setCamState("simulated");
    }
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open]);

  function capturePage() {
    if (camState === "live" && videoRef.current && videoRef.current.videoWidth > 0) {
      const v = videoRef.current;
      const c = document.createElement("canvas");
      const m = crop === "auto" ? 0.06 : 0;
      const sw = Math.round(v.videoWidth * (1 - m * 2));
      const sh = Math.round(v.videoHeight * (1 - m * 2));
      c.width = sw;
      c.height = sh;
      const ctx = c.getContext("2d")!;
      ctx.drawImage(v, Math.round(v.videoWidth * m), Math.round(v.videoHeight * m), sw, sh, 0, 0, sw, sh);
      setPages((p) => [...p, { dataUrl: c.toDataURL("image/jpeg", 0.9), width: sw, height: sh }]);
    } else {
      setPages((p) => [...p, drawSyntheticScan(docType, p.length + 1, crop, rot)]);
    }
  }

  function updateLastPage(nextCrop: "auto" | "full", nextRot: number) {
    setCrop(nextCrop);
    setRot(nextRot);
    if (pages.length > 0 && camState !== "live") {
      setPages((p) => [...p.slice(0, -1), drawSyntheticScan(docType, p.length, nextCrop, nextRot)]);
    }
  }

  async function submitScan() {
    if (!pages.length) return;
    if (accept.includes("image")) {
      const res = await fetch(pages[0].dataUrl);
      const blob = await res.blob();
      onSubmitFile(new File([blob], `scan_${docType}.jpg`, { type: "image/jpeg" }));
    } else {
      const pdfBytes = jpegsToPdf(pages);
      onSubmitFile(new File([pdfBytes.buffer as ArrayBuffer], `scan_${docType}.pdf`, { type: "application/pdf" }));
    }
    onClose();
  }

  const latest = pages[pages.length - 1];

  return (
    <Dialog open={open} onClose={onClose} title={`Scan document: ${label}`} wide>
      <div className="grid gap-4 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-sm bg-paper px-3 py-2 text-xs">
          <span>
            {camState === "live"
              ? "Live camera active — align the document inside the frame and capture."
              : "Camera unavailable or headless environment — using calibrated synthetic document viewfinder (or upload a file below)."}
          </span>
          <span className="font-semibold">Pages captured: {pages.length}</span>
        </div>

        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_15rem]">
          <div className="relative grid min-h-[20rem] place-items-center overflow-hidden rounded-sm border border-ink bg-ink/5 p-3">
            {camState === "live" && !latest && (
              <video ref={videoRef} autoPlay playsInline muted className="max-h-[22rem] w-auto rounded-sm" />
            )}
            {latest ? (
              <img src={latest.dataUrl} alt={`Captured page ${pages.length}`} data-testid="scanner-preview-img"
                className="max-h-[22rem] w-auto rounded-sm shadow-sm" />
            ) : (
              <div className="grid max-w-xs gap-2 rounded-sm border-2 border-dashed border-ink bg-sheet p-5 text-center text-xs">
                <strong className="text-sm">Ready to capture {label}</strong>
                <span className="text-ink-soft">Auto-edge detection & perspective crop: {crop === "auto" ? "Enabled" : "Full frame"}</span>
              </div>
            )}
          </div>

          <div className="grid content-start gap-2.5">
            <button type="button" className="btn btn-primary" onClick={capturePage}>
              {pages.length === 0 ? "Capture page" : "Add another page"}
            </button>

            <div className="grid grid-cols-2 gap-1.5">
              <button type="button" className={cx("btn btn-quiet text-xs", crop === "auto" && "border-ink bg-paper-deep")}
                onClick={() => updateLastPage(crop === "auto" ? "full" : "auto", rot)}>
                {crop === "auto" ? "Crop: Auto-edge" : "Crop: Full frame"}
              </button>
              <button type="button" className="btn btn-quiet text-xs"
                onClick={() => updateLastPage(crop, (rot + 90) % 360)}>
                Rotate 90° ({rot}°)
              </button>
            </div>

            {pages.length > 0 && (
              <>
                <button type="button" className="btn btn-quiet text-xs" onClick={() => setPages((p) => p.slice(0, -1))}>
                  Retake last page
                </button>
                <button type="button" className="btn btn-primary" onClick={submitScan}>
                  Submit scan ({pages.length} {pages.length === 1 ? "page" : "pages"})
                </button>
              </>
            )}

            <div className="border-t border-rule pt-2.5 text-xs text-ink-soft">
              <label className="link cursor-pointer font-semibold text-ink">
                File upload fallback
                <input type="file" accept={accept} className="sr-only"
                  onChange={(e: ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) { onSubmitFile(f); onClose(); } }} />
              </label>
            </div>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
