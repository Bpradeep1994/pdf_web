"use client";
import { useState } from "react";
import {
  MousePointer2, TextCursorInput, Type, Pen, Highlighter, Eraser, Stamp, PenTool,
  Square, Circle, Minus, ChevronDown, ImagePlus,
} from "lucide-react";
import { documentsApi } from "@/lib/api";
import toast from "react-hot-toast";

type Tool = "text" | "edittext" | "highlight" | "redact" | "draw" | "image" | "rect" | "ellipse" | "line" | null;

interface Props {
  documentId: string;
  currentPage: number;
  onToolChange?: (tool: Tool) => void;
  onChanged?: () => void;
  onTogglePanel?: (panel: "comments" | "signatures") => void;
}

export default function Toolbar({ documentId, onToolChange, onChanged, onTogglePanel }: Props) {
  const [activeTool, setActiveTool] = useState<Tool>(null);
  const [busy, setBusy]             = useState(false);
  const [shapesOpen, setShapesOpen] = useState(false);
  const SHAPES: [Tool, any, string][] = [
    ["highlight", Highlighter, "Highlight"],
    ["rect", Square, "Rectangle"],
    ["ellipse", Circle, "Circle / Ellipse"],
    ["line", Minus, "Line"],
  ];

  const watermark = async () => {
    const text = window.prompt("Watermark text", "CONFIDENTIAL");
    if (!text) return;
    setBusy(true);
    try { await documentsApi.watermark(documentId, { text }); toast.success("Watermark applied"); onChanged?.(); }
    catch { toast.error("Watermark failed"); }
    finally { setBusy(false); }
  };

  const selectTool = (tool: Tool) => {
    const next = activeTool === tool ? null : tool;
    setActiveTool(next);
    onToolChange?.(next);
  };

  const toolBtn = (tool: Tool, Icon: any, label: string) => (
    <button onClick={() => selectTool(tool)} title={label}
      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
        activeTool === tool ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}>
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );

  const actionBtn = (onClick: () => void, Icon: any, label: string) => (
    <button onClick={onClick} disabled={busy} title={label}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap text-slate-600 hover:bg-slate-100 transition-colors disabled:opacity-50">
      <Icon className="w-4 h-4" />
      {label}
    </button>
  );

  const sep = <div className="w-px h-6 bg-slate-200 mx-1 flex-shrink-0" />;

  return (
    <div className="w-full flex items-center gap-0.5 px-3 py-2 bg-white border-b border-slate-200 overflow-x-auto flex-shrink-0">
      {toolBtn(null, MousePointer2, "Select")}
      {sep}
      {toolBtn("edittext",  TextCursorInput, "Edit Text")}
      {toolBtn("text",      Type,            "Add Text")}
      {sep}
      {toolBtn("draw",      Pen,         "Draw")}
      {toolBtn("image",     ImagePlus,   "Image")}

      {/* Highlight + shapes dropdown */}
      <div className="relative">
        <button onClick={() => setShapesOpen((o) => !o)} title="Highlight & shapes"
          className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-sm whitespace-nowrap transition-colors ${
            ["highlight", "rect", "ellipse", "line"].includes(activeTool as string) ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}>
          <Highlighter className="w-4 h-4" /> Highlight <ChevronDown className="w-3 h-3" />
        </button>
        {shapesOpen && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setShapesOpen(false)} />
            <div className="absolute left-0 mt-1 w-44 bg-white rounded-xl shadow-xl border border-slate-100 py-1 z-40">
              {SHAPES.map(([t, Ic, lbl]) => (
                <button key={lbl} onClick={() => { selectTool(t); setShapesOpen(false); }}
                  className={`flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-slate-50 ${activeTool === t ? "text-brand-700" : "text-slate-700"}`}>
                  <Ic className="w-4 h-4" /> {lbl}
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {toolBtn("redact",    Eraser,      "Redact")}
      {actionBtn(watermark, Stamp,       "Stamp")}
      {sep}
      {onTogglePanel && actionBtn(() => onTogglePanel("signatures"), PenTool, "Sign")}
    </div>
  );
}
