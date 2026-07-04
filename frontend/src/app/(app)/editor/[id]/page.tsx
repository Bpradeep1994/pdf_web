"use client";
import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2, ChevronRight, Check, Download, FileOutput, Share2, History } from "lucide-react";
import { documentsApi, conversionApi } from "@/lib/api";
import PDFViewer, { type EditorTool } from "@/components/editor/PDFViewer";
import Toolbar from "@/components/editor/Toolbar";
import VersionHistory from "@/components/editor/VersionHistory";
import CommentsPanel from "@/components/editor/CommentsPanel";
import SignaturePanel from "@/components/editor/SignaturePanel";
import toast from "react-hot-toast";

interface Doc {
  id:            string;
  original_name: string;
  s3_key?:       string;
  page_count:    number | null;
  status:        string;
}

export default function EditorPage() {
  const { id }  = useParams<{ id: string }>();
  const router  = useRouter();
  const [doc, setDoc]               = useState<Doc | null>(null);
  const [loading, setLoading]       = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [tool, setTool]             = useState<EditorTool>(null);
  const [docChanged, setDocChanged] = useState(0);
  const [showVersions, setShowVersions] = useState(false);
  const [panel, setPanel]           = useState<"comments" | "signatures" | null>(null);
  const [textSize, setTextSize]     = useState(11);
  const [textColor, setTextColor]   = useState("#111827");
  const [textFont, setTextFont]     = useState("helv");
  const [placeImage, setPlaceImage] = useState<string | undefined>();
  const [savedFlash, setSavedFlash] = useState(false);
  const [showConvert, setShowConvert] = useState(false);
  const [converting, setConverting] = useState(false);
  const [sharing, setSharing]       = useState(false);

  const CONVERT_FORMATS = ["docx", "xlsx", "pptx", "png", "jpg", "txt"];

  const download = async () => {
    try { const { data } = await documentsApi.download(id); window.open(data.url, "_blank"); }
    catch { toast.error("Download failed"); }
  };
  const share = async () => {
    setSharing(true);
    try {
      const { data } = await documentsApi.share(id, { permission: "view" });
      await navigator.clipboard.writeText(data.share_url).catch(() => {});
      toast.success("Share link copied");
    } catch { toast.error("Failed to create share link"); }
    finally { setSharing(false); }
  };
  const convert = async (fmt: string) => {
    setShowConvert(false); setConverting(true);
    try {
      const { data } = await conversionApi.convert({
        s3_key: doc?.s3_key ?? "", source_format: "pdf", target_format: fmt, document_id: id });
      window.open(data.download_url, "_blank");
      toast.success(`Converted to ${fmt.toUpperCase()}`);
    } catch { toast.error("Conversion failed"); }
    finally { setConverting(false); }
  };

  const flashSaved = () => { setDocChanged((n) => n + 1); setSavedFlash(true); setTimeout(() => setSavedFlash(false), 1800); };
  const markChanged = flashSaved;

  // one history op at a time — holding Ctrl+Z auto-repeats keydown events
  const historyBusy = useRef(false);
  const undo = async () => {
    if (historyBusy.current) return;
    historyBusy.current = true;
    try { await documentsApi.undo(id); toast.success("Undone"); flashSaved(); }
    catch (e: any) { toast(e?.response?.data?.detail ?? "Nothing to undo"); }
    finally { historyBusy.current = false; }
  };
  const redo = async () => {
    if (historyBusy.current) return;
    historyBusy.current = true;
    try { await documentsApi.redo(id); toast.success("Redone"); flashSaved(); }
    catch (e: any) { toast(e?.response?.data?.detail ?? "Nothing to redo"); }
    finally { historyBusy.current = false; }
  };

  // Keyboard undo/redo: Ctrl/Cmd+Z, Ctrl/Cmd+Y, Ctrl/Cmd+Shift+Z.
  // Skipped while typing in a text box so the browser's native text-undo still works there.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    documentsApi.get(id)
      .then(({ data }) => setDoc(data))
      .catch(() => { toast.error("Document not found"); router.push("/dashboard"); })
      .finally(() => setLoading(false));
  }, [id, router]);

  // refetch after edits — page operations change page_count and the rail must follow
  useEffect(() => {
    if (!docChanged) return;
    documentsApi.get(id).then(({ data }) => setDoc(data)).catch(() => {});
  }, [docChanged, id]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
      </div>
    );
  }
  if (!doc) return null;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <header className="flex items-center gap-4 px-4 py-3 bg-white border-b border-slate-200 flex-shrink-0">
        <Link href="/dashboard" className="btn-ghost p-1.5">
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Link href="/dashboard" className="hover:text-slate-800">Documents</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-900 font-medium truncate max-w-xs">{doc.original_name}</span>
        </div>

        {/* Text options (only when the text tool is active) */}
        {tool === "text" && (
          <div className="flex items-center gap-2 ml-2 pl-3 border-l border-slate-200">
            <select value={textFont} onChange={(e) => setTextFont(e.target.value)}
              className="input py-0.5 px-1 text-sm" title="Font">
              <optgroup label="Helvetica (sans-serif)">
                <option value="helv">Helvetica</option>
                <option value="helvB">Helvetica Bold</option>
                <option value="helvI">Helvetica Italic</option>
                <option value="helvBI">Helvetica Bold Italic</option>
              </optgroup>
              <optgroup label="Times (serif)">
                <option value="tiro">Times</option>
                <option value="tibo">Times Bold</option>
                <option value="tiit">Times Italic</option>
                <option value="tibi">Times Bold Italic</option>
              </optgroup>
              <optgroup label="Courier (monospace)">
                <option value="cour">Courier</option>
                <option value="couB">Courier Bold</option>
                <option value="couI">Courier Italic</option>
                <option value="couBI">Courier Bold Italic</option>
              </optgroup>
            </select>
            <label className="text-xs text-slate-500">Size</label>
            <input type="number" min={6} max={96} value={textSize}
              onChange={(e) => setTextSize(Math.max(6, Math.min(96, +e.target.value || 11)))}
              className="input py-0.5 px-1 w-14 text-sm" />
            <input type="color" value={textColor} onChange={(e) => setTextColor(e.target.value)}
              className="w-7 h-7 rounded border border-slate-200 cursor-pointer" title="Text color" />
          </div>
        )}

        {(tool === "rect" || tool === "ellipse" || tool === "line") && (
          <div className="flex items-center gap-2 ml-2 pl-3 border-l border-slate-200">
            <label className="text-xs text-slate-500">Shape color</label>
            <input type="color" value={textColor} onChange={(e) => setTextColor(e.target.value)}
              className="w-7 h-7 rounded border border-slate-200 cursor-pointer" title="Shape color" />
          </div>
        )}

        <span className="ml-auto flex items-center gap-1 text-xs text-slate-500 mr-2">
          <Check className={`w-3.5 h-3.5 ${savedFlash ? "text-green-500" : "text-slate-300"}`} />
          {savedFlash ? "Saved" : "Auto-saved"}
        </span>

        {/* Document actions — always visible */}
        <div className="flex items-center gap-1">
          <button onClick={() => setShowVersions(true)} className="btn-ghost gap-1.5 text-sm px-2.5 py-1.5" title="Version history">
            <History className="w-4 h-4" /> History
          </button>
          <button onClick={share} disabled={sharing} className="btn-ghost gap-1.5 text-sm px-2.5 py-1.5 disabled:opacity-50">
            {sharing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />} Share
          </button>
          <div className="relative">
            <button onClick={() => setShowConvert((s) => !s)} disabled={converting}
              className="btn-secondary gap-1.5 text-sm px-2.5 py-1.5 disabled:opacity-50">
              {converting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileOutput className="w-4 h-4" />} Convert
            </button>
            {showConvert && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setShowConvert(false)} />
                <div className="absolute right-0 mt-1 w-32 bg-white rounded-xl shadow-xl border border-slate-100 py-1 z-40">
                  {CONVERT_FORMATS.map((f) => (
                    <button key={f} onClick={() => convert(f)}
                      className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 uppercase font-medium">{f}</button>
                  ))}
                </div>
              </>
            )}
          </div>
          <button onClick={download} className="btn-primary gap-1.5 text-sm px-3 py-1.5" title="Download PDF">
            <Download className="w-4 h-4" /> Save
          </button>
        </div>
      </header>

      {/* Horizontal tool bar (top) */}
      <Toolbar
        documentId={id}
        currentPage={currentPage}
        onToolChange={setTool}
        onChanged={markChanged}
        onTogglePanel={(p) => setPanel((cur) => (cur === p ? null : p))}
      />

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <PDFViewer
            documentId={id}
            pageCount={doc.page_count ?? 1}
            tool={tool}
            reloadSignal={docChanged}
            textSize={textSize}
            textColor={textColor}
            textFont={textFont}
            placeImage={placeImage}
            onPageChange={setCurrentPage}
            onExitTool={() => { setTool(null); setPlaceImage(undefined); }}
            onEdited={markChanged}
          />
        </div>

        {panel === "comments" && (
          <CommentsPanel documentId={id} currentPage={currentPage} onClose={() => setPanel(null)} />
        )}
        {panel === "signatures" && (
          <SignaturePanel documentId={id} currentPage={currentPage} onClose={() => setPanel(null)}
            onChanged={markChanged}
            onPlace={(dataUrl) => { setPlaceImage(dataUrl); setTool("image"); setPanel(null); toast("Drag the signature into place, then click ✓"); }} />
        )}
      </div>

      {showVersions && (
        <VersionHistory
          documentId={id}
          onClose={() => setShowVersions(false)}
          onRestored={() => setDocChanged((n) => n + 1)}
        />
      )}
    </div>
  );
}
