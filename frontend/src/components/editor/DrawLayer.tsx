"use client";
import { useEffect, useRef, useState } from "react";
import { Pen, Highlighter, Undo2, Trash2, Check, X, Loader2 } from "lucide-react";

type Mode = "pen" | "marker";

interface Props {
  width:    number;                 // px — matches the rendered page image
  height:   number;
  onApply:  (pngBase64: string) => void;
  onCancel: () => void;
  saving?:  boolean;
}

const COLORS = ["#e11d48", "#2563eb", "#16a34a", "#f59e0b", "#111827"];

/** Freehand drawing surface (fabric.js). Pen = thin opaque, Marker = thick translucent.
 *  On apply, exports a transparent PNG of the strokes for the caller to flatten onto the PDF. */
export default function DrawLayer({ width, height, onApply, onCancel, saving }: Props) {
  const elRef     = useRef<HTMLCanvasElement>(null);
  const fabricRef = useRef<any>(null);
  const [mode, setMode]   = useState<Mode>("pen");
  const [color, setColor] = useState(COLORS[0]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let canvas: any;
    let disposed = false;
    (async () => {
      const fabric: any = await import("fabric");
      if (disposed || !elRef.current) return;
      canvas = new fabric.Canvas(elRef.current, { isDrawingMode: true, width, height });
      const brush = new fabric.PencilBrush(canvas);
      brush.width = 3;
      brush.color = COLORS[0];
      canvas.freeDrawingBrush = brush;
      fabricRef.current = canvas;
      setReady(true);
    })();
    return () => { disposed = true; if (canvas) canvas.dispose(); };
  }, [width, height]);

  // keep the brush in sync with the selected mode / colour
  useEffect(() => {
    const c = fabricRef.current;
    if (!c || !c.freeDrawingBrush) return;
    c.freeDrawingBrush.width = mode === "marker" ? 16 : 3;
    c.freeDrawingBrush.color = mode === "marker" ? color + "80" : color; // 50% alpha for marker
  }, [mode, color, ready]);

  const undo = () => {
    const c = fabricRef.current; if (!c) return;
    const objs = c.getObjects();
    if (objs.length) { c.remove(objs[objs.length - 1]); c.renderAll(); }
  };
  const clear = () => fabricRef.current?.clear();
  const apply = () => {
    const c = fabricRef.current; if (!c) return;
    if (!c.getObjects().length) { onCancel(); return; }
    onApply(c.toDataURL({ format: "png", multiplier: 1 }));
  };

  const toolBtn = (m: Mode, Icon: any, label: string) => (
    <button onClick={() => setMode(m)} title={label}
      className={`p-1.5 rounded ${mode === m ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}>
      <Icon className="w-4 h-4" />
    </button>
  );

  return (
    <div className="absolute inset-0 z-30">
      <canvas ref={elRef} className="absolute inset-0" />
      {/* floating toolbar */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 bg-white rounded-xl shadow-2xl border border-slate-200 px-2 py-1.5">
        {toolBtn("pen", Pen, "Pen")}
        {toolBtn("marker", Highlighter, "Marker")}
        <span className="w-px h-5 bg-slate-200 mx-1" />
        {COLORS.map((c) => (
          <button key={c} onClick={() => setColor(c)}
            className={`w-5 h-5 rounded-full border-2 ${color === c ? "border-slate-800" : "border-transparent"}`}
            style={{ backgroundColor: c }} title={c} />
        ))}
        <span className="w-px h-5 bg-slate-200 mx-1" />
        <button onClick={undo} title="Undo" className="p-1.5 rounded text-slate-600 hover:bg-slate-100"><Undo2 className="w-4 h-4" /></button>
        <button onClick={clear} title="Clear" className="p-1.5 rounded text-slate-600 hover:bg-slate-100"><Trash2 className="w-4 h-4" /></button>
        <span className="w-px h-5 bg-slate-200 mx-1" />
        <button onClick={apply} disabled={saving} title="Apply" className="p-1.5 rounded bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
        </button>
        <button onClick={onCancel} title="Cancel" className="p-1.5 rounded text-slate-600 hover:bg-slate-100"><X className="w-4 h-4" /></button>
      </div>
    </div>
  );
}
