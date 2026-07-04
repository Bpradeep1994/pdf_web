"use client";
import { useEffect, useRef, useState } from "react";
import { X, PenTool, Eraser, Loader2, Send, CheckCircle2, Circle, Upload, MousePointerClick, Save } from "lucide-react";
import { signatureApi } from "@/lib/api";
import toast from "react-hot-toast";

interface Field { id: string; signer_email: string; page_number: number; signed: boolean; }
interface Req { id: string; document_id: string; title?: string; status: string; fields: Field[]; }

export default function SignaturePanel({ documentId, currentPage, onClose, onChanged, onPlace }: {
  documentId: string; currentPage: number; onClose: () => void; onChanged: () => void;
  onPlace?: (dataUrl: string) => void;
}) {
  const padRef  = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [hasInk, setHasInk] = useState(false);
  const [busy, setBusy]     = useState(false);
  const [title, setTitle]   = useState("");
  const [emails, setEmails] = useState("");
  const [requests, setRequests] = useState<Req[]>([]);
  const [saved, setSaved]   = useState<string[]>([]);

  const SAVED_KEY = "saved_signatures";
  useEffect(() => {
    try { setSaved(JSON.parse(localStorage.getItem(SAVED_KEY) || "[]")); } catch { setSaved([]); }
  }, []);
  const persistSaved = (list: string[]) => {
    setSaved(list);
    try { localStorage.setItem(SAVED_KEY, JSON.stringify(list)); } catch {}
  };

  const ctx = () => padRef.current!.getContext("2d")!;
  // Scale display coords â†’ canvas buffer coords so the ink lands under the cursor
  // even though the canvas is rendered at a different CSS width.
  const pos = (e: React.PointerEvent) => {
    const c = padRef.current!; const r = c.getBoundingClientRect();
    return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) };
  };
  const down = (e: React.PointerEvent) => {
    drawing.current = true; (e.target as Element).setPointerCapture?.(e.pointerId);
    const c = ctx(); const p = pos(e); c.beginPath(); c.moveTo(p.x, p.y);
  };
  const move = (e: React.PointerEvent) => {
    if (!drawing.current) return;
    const c = ctx(); const p = pos(e); c.lineWidth = 2.2; c.lineCap = "round"; c.strokeStyle = "#111827";
    c.lineTo(p.x, p.y); c.stroke(); setHasInk(true);
  };
  const up   = () => { drawing.current = false; };
  const clearPad = () => { const c = padRef.current!; ctx().clearRect(0, 0, c.width, c.height); setHasInk(false); };
  const sigData = () => padRef.current!.toDataURL("image/png");

  const uploadSig = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const c = padRef.current!; const cx = ctx();
        cx.clearRect(0, 0, c.width, c.height);
        const scale = Math.min(c.width / img.width, c.height / img.height);
        const w = img.width * scale, h = img.height * scale;
        cx.drawImage(img, (c.width - w) / 2, (c.height - h) / 2, w, h);
        setHasInk(true);
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  };

  const placeOnPage = () => {
    if (!hasInk) { toast.error("Draw or upload a signature first"); return; }
    onPlace?.(sigData());
  };

  const saveSignature = () => {
    if (!hasInk) { toast.error("Draw or upload a signature first"); return; }
    const data = sigData();
    if (saved.includes(data)) { toast("Already saved"); return; }
    persistSaved([data, ...saved].slice(0, 3));   // keep the 3 most recent
    toast.success("Signature saved");
  };

  const loadSaved = (data: string) => {
    const img = new Image();
    img.onload = () => {
      const c = padRef.current!; const cx = ctx();
      cx.clearRect(0, 0, c.width, c.height);
      cx.drawImage(img, 0, 0, c.width, c.height);
      setHasInk(true);
    };
    img.src = data;
  };

  const removeSaved = (data: string) => persistSaved(saved.filter((s) => s !== data));

  const loadRequests = async () => {
    try { setRequests((await signatureApi.listRequests()).data.filter((r: Req) => r.document_id === documentId)); } catch {}
  };
  useEffect(() => { loadRequests(); }, [documentId]);

  const selfSign = async () => {
    if (!hasInk) { toast.error("Draw your signature first"); return; }
    setBusy(true);
    try {
      await signatureApi.apply({ document_id: documentId, signature_base64: sigData(),
        page: currentPage, x: 72, y: 72, width: 150, height: 60 });
      toast.success("Document signed"); onChanged();
    } catch { toast.error("Signing failed"); }
    finally { setBusy(false); }
  };

  const createRequest = async () => {
    const list = emails.split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
    if (list.length === 0) { toast.error("Add at least one signer email"); return; }
    setBusy(true);
    try {
      await signatureApi.createRequest({ document_id: documentId, title: title || undefined,
        fields: list.map((email, i) => ({ signer_email: email, page_number: currentPage,
          x: 72, y: 72 + i * 80, width: 150, height: 60, field_type: "signature" })) });
      toast.success("Signature request created"); setTitle(""); setEmails(""); loadRequests();
    } catch { toast.error("Failed to create request"); }
    finally { setBusy(false); }
  };

  const signField = async (reqId: string, fieldId: string) => {
    if (!hasInk) { toast.error("Draw your signature first"); return; }
    setBusy(true);
    try {
      await signatureApi.signField(reqId, { field_id: fieldId, signature_base64: sigData() });
      toast.success("Field signed"); onChanged(); loadRequests();
    } catch { toast.error("Signing failed"); }
    finally { setBusy(false); }
  };

  return (
    <aside className="w-80 flex-shrink-0 border-l border-slate-200 bg-white flex flex-col h-full overflow-y-auto">
      <div className="flex items-center justify-between px-4 h-12 border-b border-slate-100 sticky top-0 bg-white">
        <span className="font-semibold text-sm flex items-center gap-2"><PenTool className="w-4 h-4" /> Signatures</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-600"><X className="w-4 h-4" /></button>
      </div>

      <div className="p-3 space-y-4">
        {/* Signature pad */}
        <div>
          <p className="text-xs font-medium text-slate-500 mb-1">Draw your signature</p>
          <canvas ref={padRef} width={290} height={110}
            onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up}
            className="border border-slate-300 rounded-lg bg-slate-50 w-full cursor-crosshair touch-none select-none" />
          <div className="flex items-center justify-between mt-1">
            <button onClick={clearPad} className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"><Eraser className="w-3.5 h-3.5" /> Clear</button>
            <button onClick={saveSignature} className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"><Save className="w-3.5 h-3.5" /> Save</button>
            <label className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1 cursor-pointer">
              <Upload className="w-3.5 h-3.5" /> Upload
              <input type="file" accept="image/*" className="hidden" onChange={uploadSig} />
            </label>
          </div>

          {/* Saved signatures (kept in this browser) */}
          {saved.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium text-slate-500 mb-1">Saved signatures</p>
              <div className="flex gap-2">
                {saved.map((s, i) => (
                  <div key={i} className="relative group">
                    <button onClick={() => loadSaved(s)} title="Use this signature"
                      className="block w-20 h-9 border border-slate-200 rounded-md bg-white hover:border-brand-400 overflow-hidden">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={s} alt={`Saved signature ${i + 1}`} className="w-full h-full object-contain" />
                    </button>
                    <button onClick={() => removeSaved(s)} title="Delete saved signature"
                      className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-white border border-slate-200 text-slate-500
                                 hover:text-red-500 items-center justify-center hidden group-hover:flex">
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button onClick={placeOnPage} className="btn-primary w-full text-sm gap-1.5 mt-2">
            <MousePointerClick className="w-4 h-4" /> Place on page (drag to position)
          </button>
          <button onClick={selfSign} disabled={busy} className="btn-secondary w-full text-xs gap-1 mt-2 disabled:opacity-50">
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PenTool className="w-3.5 h-3.5" />} Quick-sign page {currentPage} (top-left)
          </button>
        </div>

        {/* Request signatures */}
        <div className="border-t border-slate-100 pt-3">
          <p className="text-xs font-medium text-slate-500 mb-2">Request signatures</p>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (optional)" className="input text-sm mb-2" />
          <textarea value={emails} onChange={(e) => setEmails(e.target.value)} rows={2}
            placeholder="Signer emails (one per line)" className="input text-sm resize-none mb-2" />
          <button onClick={createRequest} disabled={busy} className="btn-primary text-sm w-full gap-1 disabled:opacity-50">
            <Send className="w-3.5 h-3.5" /> Send request
          </button>
        </div>

        {/* Existing requests */}
        {requests.length > 0 && (
          <div className="border-t border-slate-100 pt-3 space-y-2">
            <p className="text-xs font-medium text-slate-500">Requests</p>
            {requests.map((r) => (
              <div key={r.id} className="border border-slate-200 rounded-lg p-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-700 truncate">{r.title || "Untitled"}</span>
                  <span className={`badge text-[10px] ${r.status === "completed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>{r.status}</span>
                </div>
                <ul className="mt-1 space-y-1">
                  {r.fields.map((f) => (
                    <li key={f.id} className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-1 text-slate-600 truncate">
                        {f.signed ? <CheckCircle2 className="w-3.5 h-3.5 text-green-600" /> : <Circle className="w-3.5 h-3.5 text-slate-300" />}
                        {f.signer_email} <span className="text-slate-500">p.{f.page_number}</span>
                      </span>
                      {!f.signed && (
                        <button onClick={() => signField(r.id, f.id)} disabled={busy} className="text-brand-600 hover:underline disabled:opacity-50">Sign</button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
