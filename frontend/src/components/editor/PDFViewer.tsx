"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import {
  ZoomIn, ZoomOut, Loader2, PanelLeft, MoreVertical, FilePlus2, Copy, RotateCw,
  ArrowUp, ArrowDown, FileOutput, Trash2,
} from "lucide-react";
import { documentsApi } from "@/lib/api";
import DrawLayer from "@/components/editor/DrawLayer";
import ImageLayer from "@/components/editor/ImageLayer";
import toast from "react-hot-toast";

export type EditorTool = "text" | "edittext" | "highlight" | "redact" | "draw" | "image" | "rect" | "ellipse" | "line" | null;

interface Span { id: number; text: string; bbox: [number, number, number, number]; size: number; font: string; color: number[]; }

// PDF span font name → a base-14 name we can re-embed, and a CSS family for the editable preview.
const baseFont = (name: string): string => {
  const n = (name || "").toLowerCase(); const b = n.includes("bold");
  if (n.includes("times") || n.includes("serif") || n.includes("georgia")) return b ? "tibo" : "tiro";
  if (n.includes("courier") || n.includes("mono") || n.includes("consol")) return b ? "couB" : "cour";
  return b ? "helvB" : "helv";
};
const cssFont = (name: string): string => {
  const n = (name || "").toLowerCase();
  if (n.includes("times") || n.includes("serif")) return "'Times New Roman', serif";
  if (n.includes("courier") || n.includes("mono")) return "'Courier New', monospace";
  return "Arial, Helvetica, sans-serif";
};

interface Props {
  documentId: string;
  pageCount:  number;
  tool?:      EditorTool;
  reloadSignal?: number;
  textSize?:  number;
  textColor?: string;
  textFont?:  string;
  placeImage?: string;
  onPageChange?: (page: number) => void;
  onExitTool?: () => void;
  onEdited?: () => void;
}

interface DragRect { x0: number; y0: number; x1: number; y1: number; }

const HINTS: Record<string, string> = {
  text:      "Click to add text · drag over existing text to replace it",
  edittext:  "Click any text to edit it in place",
  highlight: "Drag to highlight a region",
  redact:    "Drag to redact (black out) a region",
  draw:      "Draw freehand, then apply",
  image:     "Drag/resize the image, then apply",
  rect:      "Drag to draw a rectangle",
  ellipse:   "Drag to draw a circle / ellipse",
  line:      "Drag to draw a line",
};
const DRAG_THRESHOLD = 5;

const hexToRgb = (hex: string): number[] => {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  return m ? [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255] : [0, 0, 0];
};
const FONT_CSS: Record<string, { family: string; weight: number; style?: string }> = {
  helv:   { family: "Helvetica, Arial, sans-serif", weight: 400 },
  helvB:  { family: "Helvetica, Arial, sans-serif", weight: 700 },
  helvI:  { family: "Helvetica, Arial, sans-serif", weight: 400, style: "italic" },
  helvBI: { family: "Helvetica, Arial, sans-serif", weight: 700, style: "italic" },
  tiro:   { family: "'Times New Roman', Times, serif", weight: 400 },
  tibo:   { family: "'Times New Roman', Times, serif", weight: 700 },
  tiit:   { family: "'Times New Roman', Times, serif", weight: 400, style: "italic" },
  tibi:   { family: "'Times New Roman', Times, serif", weight: 700, style: "italic" },
  cour:   { family: "'Courier New', Courier, monospace", weight: 400 },
  couB:   { family: "'Courier New', Courier, monospace", weight: 700 },
  couI:   { family: "'Courier New', Courier, monospace", weight: 400, style: "italic" },
  couBI:  { family: "'Courier New', Courier, monospace", weight: 700, style: "italic" },
};

export default function PDFViewer({
  documentId, pageCount, tool = null, reloadSignal = 0,
  textSize = 11, textColor = "#111827", textFont = "helv", placeImage,
  onPageChange, onExitTool, onEdited,
}: Props) {
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1);

  const [zoom, setZoom]           = useState(1.4);
  const [reloadKey, setReloadKey] = useState(0);
  const [activePage, setActivePage] = useState(1);
  const [dims, setDims]           = useState<Record<number, { w: number; h: number }>>({});
  const [saving, setSaving]       = useState(false);
  const [drag, setDrag]           = useState<DragRect | null>(null);
  const [showThumbs, setShowThumbs] = useState(true);
  const [pageMenu, setPageMenu]     = useState<number | null>(null);
  const [inlineEdit, setInlineEdit] = useState<
    { px0: number; py0: number; pw: number; ph: number; x0: number; y0: number; x1: number; y1: number; isClick: boolean } | null
  >(null);
  const [inlineVal, setInlineVal] = useState("");
  const [spans, setSpans]         = useState<Span[]>([]);

  const scrollRef = useRef<HTMLDivElement>(null);
  const imgEls    = useRef<Record<number, HTMLImageElement | null>>({});
  const pageWraps = useRef<Record<number, HTMLDivElement | null>>({});
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const inlineRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { onPageChange?.(activePage); }, [activePage, onPageChange]);
  useEffect(() => { if (reloadSignal) setReloadKey((k) => k + 1); }, [reloadSignal]);

  // Edit-text mode: load the editable spans for the active page (and after each edit).
  useEffect(() => {
    if (tool !== "edittext") { setSpans([]); return; }
    let cancel = false;
    documentsApi.textSpans(documentId, activePage)
      .then(({ data }) => { if (!cancel) setSpans(data.spans ?? []); })
      .catch(() => { if (!cancel) setSpans([]); });
    return () => { cancel = true; };
  }, [tool, activePage, documentId, reloadKey]);

  const commitSpan = async (s: Span, val: string) => {
    if (val === s.text) return;
    setSaving(true);
    try {
      await documentsApi.replaceText(documentId, {
        page: activePage, rect: s.bbox, text: val, font: baseFont(s.font), size: s.size, color: s.color });
      setReloadKey((k) => k + 1); onEdited?.();   // re-render page + reload spans
    } catch { toast.error("Edit failed"); }
    finally { setSaving(false); }
  };
  useEffect(() => { setInlineEdit(null); setInlineVal(""); }, [tool, activePage]);
  useEffect(() => { if (inlineEdit) inlineRef.current?.focus(); }, [inlineEdit]);

  // Active page = the one whose centre is closest to the viewport centre.
  const onScroll = useCallback(() => {
    const cont = scrollRef.current; if (!cont) return;
    const r = cont.getBoundingClientRect();
    const mid = r.top + r.height / 2;
    let best = activePage, bestDist = Infinity;
    for (const p of pages) {
      const el = pageWraps.current[p]; if (!el) continue;
      const pr = el.getBoundingClientRect();
      const dist = Math.abs(pr.top + pr.height / 2 - mid);
      if (dist < bestDist) { bestDist = dist; best = p; }
    }
    if (best !== activePage) setActivePage(best);
  }, [activePage, pages]);

  const scrollToPage = (p: number) => pageWraps.current[p]?.scrollIntoView({ behavior: "smooth", block: "center" });

  const zoomIn  = () => setZoom((z) => Math.min(3, +(z + 0.2).toFixed(2)));
  const zoomOut = () => setZoom((z) => Math.max(0.5, +(z - 0.2).toFixed(2)));

  // Map a screen pixel on the active page → that page's pixel space.
  const offsetOf = (clientX: number, clientY: number) => {
    const img = imgEls.current[activePage];
    if (!img) return { x: 0, y: 0 };
    const r = img.getBoundingClientRect();
    return { x: clientX - r.left, y: clientY - r.top };
  };

  const refreshAfterEdit = () => { setReloadKey((k) => k + 1); onEdited?.(); };

  // Per-page operations from the thumbnail menu.
  const pageOp = async (fn: () => Promise<unknown>, msg: string) => {
    setPageMenu(null); setSaving(true);
    try { await fn(); toast.success(msg); refreshAfterEdit(); }
    catch (e: any) { toast.error(e?.response?.data?.detail ?? "Operation failed"); }
    finally { setSaving(false); }
  };
  const movePage = (p: number, dir: -1 | 1) => {
    const order = pages.slice();                         // [1..n]
    [order[p - 1], order[p - 1 + dir]] = [order[p - 1 + dir], order[p - 1]];
    return documentsApi.reorderPages(documentId, order);
  };

  // Self-heal failed page loads (e.g. transient 429/503): retry with backoff instead
  // of leaving a permanently broken <img>.
  const retryImage = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const n = Number(img.dataset.retry || 0);
    if (n >= 4) return;
    img.dataset.retry = String(n + 1);
    const base = img.src.split("&retry=")[0];
    setTimeout(() => { img.src = `${base}&retry=${n + 1}`; }, 1500 * (n + 1));
  };
  const cancelInline = () => { setInlineEdit(null); setInlineVal(""); };

  const commitInline = async () => {
    const ed = inlineEdit; const val = inlineVal.trim();
    setInlineEdit(null); setInlineVal("");
    if (!ed || !val) return;
    setSaving(true);
    try {
      if (ed.isClick) {
        await documentsApi.editText(documentId, { page: activePage, x: ed.x0, y: ed.y0 + textSize * 0.8, text: val, font: textFont, size: textSize, color: hexToRgb(textColor) });
        toast.success("Text added");
      } else {
        // Replace: white-out the selected box and auto-fit the new text to that line
        // (no fixed size) so it sits exactly where the old text was.
        await documentsApi.replaceText(documentId, { page: activePage, rect: [ed.x0, ed.y0, ed.x1, ed.y1], text: val, font: textFont, color: hexToRgb(textColor) });
        toast.success("Text replaced");
      }
      refreshAfterEdit();
    } catch { toast.error("Edit failed"); }
    finally { setSaving(false); }
  };

  const handleDrawApply = async (pngBase64: string) => {
    const d = dims[activePage]; if (!d) return;
    setSaving(true);
    try {
      await documentsApi.addImage(documentId, {
        page: activePage, image_base64: pngBase64, x: 0, y: 0, width: d.w / zoom, height: d.h / zoom });
      toast.success("Applied");
      refreshAfterEdit(); onExitTool?.();
    } catch { toast.error("Failed to apply"); }
    finally { setSaving(false); }
  };

  const onMouseDown = (e: React.MouseEvent) => {
    if (saving) return;
    const o = offsetOf(e.clientX, e.clientY);
    dragStart.current = o;
    setDrag({ x0: o.x, y0: o.y, x1: o.x, y1: o.y });
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragStart.current) return;
    const o = offsetOf(e.clientX, e.clientY);
    setDrag({ x0: dragStart.current.x, y0: dragStart.current.y, x1: o.x, y1: o.y });
  };
  const onMouseUp = async () => {
    const d = drag; dragStart.current = null; setDrag(null);
    if (!d || saving || !tool) return;
    const px0 = Math.min(d.x0, d.x1), py0 = Math.min(d.y0, d.y1);
    const px1 = Math.max(d.x0, d.x1), py1 = Math.max(d.y0, d.y1);
    const isClick = (px1 - px0) < DRAG_THRESHOLD && (py1 - py0) < DRAG_THRESHOLD;
    const x0 = px0 / zoom, y0 = py0 / zoom, x1 = px1 / zoom, y1 = py1 / zoom;

    if (tool === "text") {
      setInlineVal("");
      setInlineEdit({ px0, py0, pw: Math.max(px1 - px0, 140), ph: Math.max(py1 - py0, Math.ceil(textSize * zoom * 1.5)), x0, y0, x1, y1, isClick });
      return;
    }
    if (isClick) return;
    setSaving(true);
    try {
      if (tool === "highlight") {
        await documentsApi.highlight(documentId, { page: activePage, quads: [[x0, y0, x1, y0, x0, y1, x1, y1]] });
        toast.success("Highlight added");
      } else if (tool === "redact") {
        await documentsApi.redact(documentId, { page: activePage, rects: [[x0, y0, x1, y1]] });
        toast.success("Region redacted");
      } else if (tool === "rect" || tool === "ellipse" || tool === "line") {
        await documentsApi.addShape(documentId, { page: activePage, shape: tool, x0, y0, x1, y1, color: hexToRgb(textColor), width: 2 });
        toast.success("Shape added");
      }
      refreshAfterEdit();
    } catch { toast.error("Edit failed"); }
    finally { setSaving(false); }
  };

  const dragMode = tool === "text" || tool === "highlight" || tool === "redact" || tool === "rect" || tool === "ellipse" || tool === "line";

  return (
    <div className="flex h-full">
      {/* Thumbnail rail */}
      {showThumbs && (
        <div className="w-32 flex-shrink-0 overflow-y-auto bg-slate-100 border-r border-slate-200 p-2 space-y-2">
          {pages.map((p) => (
            <div key={p} className="relative group">
              <button onClick={() => scrollToPage(p)}
                className={`block w-full rounded border-2 transition-colors ${p === activePage ? "border-brand-500" : "border-transparent hover:border-slate-300"}`}>
                <img src={documentsApi.renderPage(documentId, p, 0.5) + `&_=${reloadKey}`} alt={`Page ${p}`} loading="lazy" onError={retryImage} className="w-full block bg-white" />
                <span className="block text-[10px] text-center text-slate-500 py-0.5">{p}</span>
              </button>

              {/* page actions */}
              <button onClick={() => setPageMenu(pageMenu === p ? null : p)} title={`Page ${p} actions`}
                className="absolute top-1 right-1 w-5 h-5 rounded bg-white/90 border border-slate-200 shadow-sm flex items-center justify-center
                           text-slate-500 hover:text-slate-800 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity">
                <MoreVertical className="w-3.5 h-3.5" />
              </button>
              {pageMenu === p && (
                <>
                  <div className="fixed inset-0 z-30" onClick={() => setPageMenu(null)} />
                  <div className="absolute left-full top-0 ml-1 w-44 bg-white rounded-xl shadow-xl border border-slate-100 z-40 py-1 text-left">
                    <button onClick={() => pageOp(() => documentsApi.addPage(documentId, p), "Blank page added")}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                      <FilePlus2 className="w-3.5 h-3.5" /> Add blank page after
                    </button>
                    <button onClick={() => pageOp(() => documentsApi.duplicatePages(documentId, [p]), "Page duplicated")}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                      <Copy className="w-3.5 h-3.5" /> Duplicate page
                    </button>
                    <button onClick={() => pageOp(() => documentsApi.rotatePages(documentId, [p], 90), "Page rotated")}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                      <RotateCw className="w-3.5 h-3.5" /> Rotate 90°
                    </button>
                    {p > 1 && (
                      <button onClick={() => pageOp(() => movePage(p, -1), "Page moved up")}
                        className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                        <ArrowUp className="w-3.5 h-3.5" /> Move up
                      </button>
                    )}
                    {p < pageCount && (
                      <button onClick={() => pageOp(() => movePage(p, 1), "Page moved down")}
                        className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                        <ArrowDown className="w-3.5 h-3.5" /> Move down
                      </button>
                    )}
                    <button onClick={() => pageOp(() => documentsApi.extractPages(documentId, [p]), "Extracted to a new document (see Dashboard)")}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50">
                      <FileOutput className="w-3.5 h-3.5" /> Extract to new PDF
                    </button>
                    {pageCount > 1 && (
                      <button onClick={() => pageOp(() => documentsApi.deletePages(documentId, [p]), "Page deleted")}
                        className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-red-500 hover:bg-red-50">
                        <Trash2 className="w-3.5 h-3.5" /> Delete page
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col h-full flex-1 min-w-0">
        {/* Controls */}
        <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-slate-200 bg-white">
          <div className="flex items-center gap-2">
            <button onClick={() => setShowThumbs((s) => !s)} title="Toggle thumbnails" className="btn-ghost p-1.5"><PanelLeft className="w-4 h-4" /></button>
            <span className="text-sm text-slate-600 min-w-[64px] text-center">{activePage} / {pageCount}</span>
          </div>

          {tool && <span className="text-xs text-brand-600 font-medium hidden lg:block">{HINTS[tool]}</span>}

          <div className="flex items-center gap-2">
            <button onClick={zoomOut} className="btn-ghost p-1.5"><ZoomOut className="w-4 h-4" /></button>
            <span className="text-sm text-slate-500 w-12 text-center">{Math.round(zoom * 100)}%</span>
            <button onClick={zoomIn} className="btn-ghost p-1.5"><ZoomIn className="w-4 h-4" /></button>
          </div>
        </div>

        {/* Continuous scroll of all pages */}
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-auto bg-slate-700 p-6 flex flex-col items-center gap-6">
          {pages.map((p) => {
            const d = dims[p];
            const isActive = p === activePage;
            return (
              <div key={p} ref={(el) => { pageWraps.current[p] = el; }} className="relative shadow-2xl bg-white">
                {saving && isActive && (
                  <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/70"><Loader2 className="w-8 h-8 animate-spin text-brand-500" /></div>
                )}
                <img
                  ref={(el) => { imgEls.current[p] = el; }}
                  src={documentsApi.renderPage(documentId, p, zoom) + `&_=${reloadKey}`}
                  onLoad={(e) => { const i = e.currentTarget; i.dataset.retry = "0"; setDims((dd) => ({ ...dd, [p]: { w: i.naturalWidth, h: i.naturalHeight } })); }}
                  onError={retryImage}
                  alt={`Page ${p}`} draggable={false} loading="lazy"
                  className="block max-w-none select-none"
                />

                {/* Editing overlays render only on the active page */}
                {isActive && tool === "draw" && d && (
                  <DrawLayer width={d.w} height={d.h} saving={saving} onApply={handleDrawApply} onCancel={() => onExitTool?.()} />
                )}
                {isActive && tool === "image" && d && (
                  <ImageLayer width={d.w} height={d.h} saving={saving} initialImage={placeImage} onApply={handleDrawApply} onCancel={() => onExitTool?.()} />
                )}

                {/* In-place text editing — an editable box over every text span */}
                {isActive && tool === "edittext" && spans.map((s) => {
                  const [x0, y0, x1, y1] = s.bbox;
                  return (
                    // key = reload + position + text: span lists change after every edit, and
                    // index-only keys made React reuse inputs → stale text at shifted positions
                    <input key={`${reloadKey}:${s.id}:${x0},${y0}:${s.text}`} defaultValue={s.text}
                      onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") { e.currentTarget.value = s.text; e.currentTarget.blur(); } }}
                      onBlur={(e) => commitSpan(s, e.target.value)}
                      spellCheck={false}
                      style={{
                        position: "absolute", left: x0 * zoom, top: y0 * zoom,
                        width: (x1 - x0) * zoom + 10, height: (y1 - y0) * zoom + 4,
                        fontSize: s.size * zoom, lineHeight: 1, padding: 0,
                        color: `rgb(${s.color.map((c) => Math.round(c * 255)).join(",")})`,
                        fontFamily: cssFont(s.font), fontWeight: s.font.toLowerCase().includes("bold") ? 700 : 400,
                      }}
                      className="absolute bg-white border border-dashed border-brand-300 hover:border-brand-400 focus:border-brand-600 focus:bg-white outline-none z-30" />
                  );
                })}
                {isActive && dragMode && (
                  <div className="absolute inset-0 z-10" style={{ cursor: "crosshair" }}
                    onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp}>
                    {drag && (
                      <div className={
                        tool === "redact" ? "absolute bg-slate-900/70 border border-slate-900"
                        : tool === "text" ? "absolute bg-brand-300/30 border border-dashed border-brand-500"
                        : tool === "highlight" ? "absolute bg-yellow-300/40 border border-yellow-400"
                        : tool === "ellipse" ? "absolute border-2 border-blue-500 rounded-full"
                        : "absolute border-2 border-blue-500"}
                        style={{ left: Math.min(drag.x0, drag.x1), top: Math.min(drag.y0, drag.y1), width: Math.abs(drag.x1 - drag.x0), height: Math.abs(drag.y1 - drag.y0) }} />
                    )}
                    {inlineEdit && (
                      <textarea ref={inlineRef} value={inlineVal} onChange={(e) => setInlineVal(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitInline(); } else if (e.key === "Escape") cancelInline(); }}
                        onBlur={commitInline}
                        style={{ position: "absolute", left: inlineEdit.px0, top: inlineEdit.py0, width: inlineEdit.pw, height: inlineEdit.ph, fontSize: textSize * zoom, color: textColor, lineHeight: 1.15, fontFamily: (FONT_CSS[textFont] ?? FONT_CSS.helv).family, fontWeight: (FONT_CSS[textFont] ?? FONT_CSS.helv).weight, fontStyle: (FONT_CSS[textFont] ?? FONT_CSS.helv).style ?? "normal" }}
                        className="z-40 border border-brand-500 bg-white/90 outline-none resize-none p-0 leading-tight" />
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
