"use client";
import { useEffect, useRef, useState } from "react";
import { ImagePlus, RotateCw, Trash2, Crop, Check, X, Loader2 } from "lucide-react";

interface Props {
  width:    number;   // px — matches the rendered page image
  height:   number;
  onApply:  (pngBase64: string) => void;
  onCancel: () => void;
  saving?:  boolean;
  initialImage?: string;   // preload an image (e.g. a signature) ready to drag/resize
}

/** Interactive image placement (fabric.js v6). Upload → drag / resize / rotate with
 *  native selection handles, then flatten the whole layer to a transparent PNG that
 *  the caller stamps full-page onto the PDF. */
export default function ImageLayer({ width, height, onApply, onCancel, saving, initialImage }: Props) {
  const elRef     = useRef<HTMLCanvasElement>(null);
  const fabricRef = useRef<any>(null);
  const imgObjRef = useRef<any>(null);
  const cropRectRef = useRef<any>(null);
  const [hasImg, setHasImg]   = useState(false);
  const [cropping, setCropping] = useState(false);

  const loadDataUrl = async (dataUrl: string) => {
    const fabric: any = await import("fabric");
    const img: any = await fabric.FabricImage.fromURL(dataUrl);
    const c = fabricRef.current; if (!c) return;
    const scale = Math.min((width * 0.4) / img.width, (height * 0.4) / img.height, 1);
    img.set({ left: width * 0.3, top: height * 0.3, scaleX: scale, scaleY: scale });
    c.add(img); c.setActiveObject(img); c.renderAll();
    imgObjRef.current = img;
    setHasImg(true);
  };

  useEffect(() => {
    let canvas: any;
    let disposed = false;
    (async () => {
      const fabric: any = await import("fabric");
      if (disposed || !elRef.current) return;
      canvas = new fabric.Canvas(elRef.current, { width, height, selection: true });
      fabricRef.current = canvas;
      if (initialImage) await loadDataUrl(initialImage);
    })();
    return () => { disposed = true; if (canvas) canvas.dispose(); };
  }, [width, height]);   // eslint-disable-line react-hooks/exhaustive-deps

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const dataUrl: string = await new Promise((res) => {
      const r = new FileReader(); r.onload = () => res(r.result as string); r.readAsDataURL(file);
    });
    await loadDataUrl(dataUrl);
  };

  const rotate = () => {
    const c = fabricRef.current; const o = c?.getActiveObject() ?? imgObjRef.current;
    if (o) { o.rotate(((o.angle || 0) + 15) % 360); c.renderAll(); }
  };
  const del = () => {
    const c = fabricRef.current; if (!c) return;
    // fall back to the placed image when nothing is selected (e.g. right after a crop)
    const o = c.getActiveObject() ?? imgObjRef.current;
    if (!o || o === cropRectRef.current) return;
    c.remove(o);
    if (o === imgObjRef.current) imgObjRef.current = null;
    setHasImg(c.getObjects().some((x: any) => x !== cropRectRef.current));
    c.renderAll();
  };

  // Crop: toggle a draggable/resizable rectangle, then clip the image to it.
  const toggleCrop = async () => {
    const c = fabricRef.current; const img = imgObjRef.current;
    if (!c || !img) return;
    if (!cropping) {
      const fabric: any = await import("fabric");
      const b = img.getBoundingRect();
      const rect = new fabric.Rect({
        left: b.left + b.width * 0.15, top: b.top + b.height * 0.15,
        width: b.width * 0.7, height: b.height * 0.7,
        fill: "rgba(37,99,235,0.12)", stroke: "#2563eb", strokeDashArray: [6, 4], strokeWidth: 1,
      });
      cropRectRef.current = rect; c.add(rect); c.setActiveObject(rect); c.renderAll();
      setCropping(true);
    } else {
      const fabric: any = await import("fabric");
      const r = cropRectRef.current; const b = r.getBoundingRect();
      img.clipPath = new fabric.Rect({ left: b.left, top: b.top, width: b.width, height: b.height, absolutePositioned: true });
      c.remove(r); cropRectRef.current = null; c.discardActiveObject(); c.renderAll();
      setCropping(false);
    }
  };

  const apply = () => {
    const c = fabricRef.current;
    if (!c || !imgObjRef.current) { onCancel(); return; }
    if (cropRectRef.current) { c.remove(cropRectRef.current); cropRectRef.current = null; }
    c.discardActiveObject(); c.renderAll();
    onApply(c.toDataURL({ format: "png", multiplier: 1 }));
  };

  return (
    <div className="absolute inset-0 z-30">
      <canvas ref={elRef} className="absolute inset-0" />
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 bg-white rounded-xl shadow-2xl border border-slate-200 px-2 py-1.5">
        <label className="p-1.5 rounded text-slate-600 hover:bg-slate-100 cursor-pointer" title="Upload image">
          <ImagePlus className="w-4 h-4" />
          <input type="file" accept="image/*" className="hidden" onChange={onFile} />
        </label>
        <button onClick={rotate} disabled={!hasImg} title="Rotate 15°" className="p-1.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-40"><RotateCw className="w-4 h-4" /></button>
        <button onClick={toggleCrop} disabled={!hasImg} title={cropping ? "Apply crop" : "Crop"}
          className={`p-1.5 rounded disabled:opacity-40 ${cropping ? "bg-brand-100 text-brand-700" : "text-slate-600 hover:bg-slate-100"}`}><Crop className="w-4 h-4" /></button>
        <button onClick={del} disabled={!hasImg} title="Delete" className="p-1.5 rounded text-slate-600 hover:bg-slate-100 disabled:opacity-40"><Trash2 className="w-4 h-4" /></button>
        <span className="w-px h-5 bg-slate-200 mx-1" />
        <button onClick={apply} disabled={saving || !hasImg} title="Apply" className="p-1.5 rounded bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
        </button>
        <button onClick={onCancel} title="Cancel" className="p-1.5 rounded text-slate-600 hover:bg-slate-100"><X className="w-4 h-4" /></button>
      </div>
    </div>
  );
}
