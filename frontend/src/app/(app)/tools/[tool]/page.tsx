"use client";
import { useParams, useRouter } from "next/navigation";
import { useState, useCallback } from "react";
import Link from "next/link";
import {
  PenLine, Combine, Scissors, Minimize2, ScanText, FileType2, PenTool,
  FileText, FileSpreadsheet, Presentation, Image as ImageIcon,
  Lock, Unlock, ScanLine, Languages,
  Upload, Loader2, Download, ArrowLeft, X, CheckCircle2,
} from "lucide-react";
import { documentsApi, conversionApi, ocrApi } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import toast from "react-hot-toast";

type ToolKey =
  | "edit" | "merge" | "split" | "compress" | "ocr" | "convert" | "sign"
  | "word-to-pdf" | "excel-to-pdf" | "ppt-to-pdf" | "image-to-pdf" | "html-to-pdf"
  | "protect" | "unlock" | "scan" | "translate";

// must mirror TRANSLATE_LANGS in the conversion service
const LANGS: Record<string, string> = {
  auto: "Detect language", en: "English", hi: "Hindi", bn: "Bengali", ur: "Urdu",
  te: "Telugu", ta: "Tamil", fr: "French", de: "German", es: "Spanish",
};

interface ToolDef {
  title: string; desc: string; icon: any; multiple: boolean; cta: string;
  formats?: string[];
  accept?: string;   // file input accept (default: application/pdf)
  toPdf?: boolean;    // convert uploaded file → PDF via /convert/file
  kind?: "protect" | "unlock" | "scan";
  needsPassword?: boolean;
}

const TOOLS: Record<ToolKey, ToolDef> = {
  edit:     { title: "Edit & Annotate", desc: "Add text, highlight, redact, draw, and insert images.", icon: PenLine,   multiple: false, cta: "Open in editor" },
  merge:    { title: "Merge PDF",       desc: "Combine multiple PDFs into one document.",               icon: Combine,   multiple: true,  cta: "Merge PDFs" },
  split:    { title: "Split PDF",       desc: "Break a PDF into pages or custom ranges.",                icon: Scissors,  multiple: false, cta: "Split PDF" },
  compress: { title: "Compress PDF",    desc: "Shrink file size while keeping quality.",                 icon: Minimize2, multiple: false, cta: "Compress PDF" },
  ocr:      { title: "OCR",             desc: "Make scanned documents searchable & selectable.",         icon: ScanText,  multiple: false, cta: "Run OCR" },
  convert:  { title: "Convert PDF",     desc: "PDF → Word, Excel, PowerPoint, or images.",               icon: FileType2, multiple: false, cta: "Convert", formats: ["docx", "xlsx", "pptx", "png", "jpg", "txt"] },
  sign:     { title: "E-Signature",     desc: "Sign documents or request signatures with an audit trail.", icon: PenTool, multiple: false, cta: "Open to sign" },
  "word-to-pdf":  { title: "Word to PDF",  desc: "Convert Word documents (.doc, .docx) to PDF.",  icon: FileText,        multiple: false, cta: "Convert to PDF", toPdf: true, accept: ".doc,.docx,.odt,.rtf" },
  "excel-to-pdf": { title: "Excel to PDF", desc: "Convert spreadsheets (.xls, .xlsx) to PDF.",     icon: FileSpreadsheet, multiple: false, cta: "Convert to PDF", toPdf: true, accept: ".xls,.xlsx,.ods,.csv" },
  "ppt-to-pdf":   { title: "PPT to PDF",   desc: "Convert presentations (.ppt, .pptx) to PDF.",    icon: Presentation,    multiple: false, cta: "Convert to PDF", toPdf: true, accept: ".ppt,.pptx,.odp" },
  "image-to-pdf": { title: "Image to PDF", desc: "Convert images (JPG, PNG, …) to PDF.",           icon: ImageIcon,       multiple: false, cta: "Convert to PDF", toPdf: true, accept: "image/*" },
  "html-to-pdf":  { title: "HTML to PDF",  desc: "Convert web pages (.html) to PDF.",              icon: FileType2,       multiple: false, cta: "Convert to PDF", toPdf: true, accept: ".html,.htm" },
  protect:  { title: "Protect PDF", desc: "Add a password and encrypt your PDF file.",            icon: Lock,     multiple: false, cta: "Protect PDF", kind: "protect", needsPassword: true },
  unlock:   { title: "Unlock PDF",  desc: "Remove password, encryption & permissions from a PDF.", icon: Unlock,   multiple: false, cta: "Unlock PDF",  kind: "unlock",  needsPassword: true },
  scan:     { title: "PDF Scanner", desc: "Combine photos / scans into a single PDF.",             icon: ScanLine, multiple: true,  cta: "Create PDF", kind: "scan", accept: "image/*" },
  translate: { title: "Translate PDF", desc: "Translate documents — English ⇄ Hindi, Telugu, and more.", icon: Languages, multiple: false, cta: "Translate" },
};

interface Picked { file: File; }
interface ResultLink { label: string; url?: string; href?: string; }

export default function ToolPage() {
  const { tool } = useParams<{ tool: string }>();
  const router = useRouter();
  const def = TOOLS[tool as ToolKey];

  const [files, setFiles]   = useState<Picked[]>([]);
  const [format, setFormat] = useState("docx");
  const [quality, setQuality] = useState<"low" | "medium" | "high">("medium");
  const [fromLang, setFromLang] = useState("auto");
  const [toLang, setToLang]     = useState("hi");
  const [translated, setTranslated] = useState("");
  const [ranges, setRanges] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy]     = useState(false);
  const [results, setResults] = useState<ResultLink[]>([]);
  const [done, setDone]     = useState(false);

  const onPick = useCallback((list: FileList | null) => {
    if (!list) return;
    const picked = Array.from(list).map((file) => ({ file }));
    setFiles((prev) => def?.multiple ? [...prev, ...picked] : picked.slice(0, 1));
    setResults([]); setDone(false);
  }, [def]);

  if (!def) {
    return <div className="p-10 text-center text-slate-500">Unknown tool. <Link href="/tools" className="text-brand-600">Back to tools</Link></div>;
  }

  const uploadAll = async () => {
    const out: { id: string; s3_key: string; name: string }[] = [];
    for (const { file } of files) {
      const { data } = await documentsApi.upload(file);
      out.push({ id: data.id, s3_key: data.s3_key, name: data.original_name });
    }
    return out;
  };

  const run = async () => {
    if (files.length === 0) { toast.error("Add a file first"); return; }
    if (tool === "merge" && files.length < 2) { toast.error("Add at least 2 PDFs to merge"); return; }
    if (def.needsPassword && tool === "protect" && !password.trim()) { toast.error("Enter a password"); return; }
    setBusy(true); setResults([]); setDone(false);
    try {
      // File-upload tools (no document store): protect / unlock / scan / office→pdf.
      if (def.kind === "protect") {
        const { data } = await conversionApi.protect(files[0].file, password);
        setResults([{ label: "protected.pdf", url: data.download_url }]); setDone(true); toast.success("Protected!"); return;
      }
      if (def.kind === "unlock") {
        const { data } = await conversionApi.unlock(files[0].file, password);
        setResults([{ label: "unlocked.pdf", url: data.download_url }]); setDone(true); toast.success("Unlocked!"); return;
      }
      if (def.kind === "scan") {
        const { data } = await conversionApi.scan(files.map((f) => f.file));
        setResults([{ label: "scanned.pdf", url: data.download_url }]); setDone(true); toast.success("PDF created!"); return;
      }
      if (def.toPdf) {
        const { data } = await conversionApi.convertFile(files[0].file, "pdf");
        setResults([{ label: `${files[0].file.name.replace(/\.[^.]+$/, "")}.pdf`, url: data.download_url }]);
        setDone(true); toast.success("Done!");
        return;
      }
      if (tool === "translate") {
        if (fromLang !== "auto" && fromLang === toLang) { toast.error("Pick two different languages"); return; }
        const { data } = await conversionApi.translateFile(files[0].file, toLang, fromLang);
        setTranslated(data.translated_text ?? "");
        setResults([
          { label: `Translated (${data.target_language}).pdf`, url: data.download_url },
          { label: `Translated (${data.target_language}).txt`, url: data.txt_url },
        ]);
        setDone(true);
        toast.success(data.truncated ? "Translated (long document — first part only)" : "Translated!");
        return;
      }

      const uploaded = await uploadAll();
      const first = uploaded[0];

      if (tool === "edit" || tool === "sign") {
        router.push(`/editor/${first.id}`);
        return;
      }
      if (tool === "merge") {
        const { data } = await documentsApi.merge(uploaded.map((u) => u.id));
        const dl = await documentsApi.download(data.id);
        setResults([{ label: "Merged.pdf", url: dl.data.url }]);
      } else if (tool === "split") {
        const parsed = ranges.trim()
          ? ranges.split(",").map((r) => r.split("-").map((n) => parseInt(n.trim(), 10)))
          : undefined;
        const { data } = await documentsApi.split(first.id, parsed as number[][] | undefined);
        const parts = Array.isArray(data) ? data : [data];
        const links: ResultLink[] = [];
        for (let i = 0; i < parts.length; i++) {
          const dl = await documentsApi.download(parts[i].id);
          links.push({ label: `Part ${i + 1}.pdf`, url: dl.data.url });
        }
        setResults(links);
      } else if (tool === "compress") {
        const { data } = await documentsApi.compress(first.id, quality);
        const dl = await documentsApi.download(first.id);
        const saved = data.saved_ratio > 0
          ? ` — saved ${Math.round(data.saved_ratio * 100)}% (${formatBytes(data.original_size)} → ${formatBytes(data.compressed_size)})`
          : " — already optimised";
        setResults([{ label: `Compressed.pdf${saved}`, url: dl.data.url }]);
      } else if (tool === "convert") {
        const { data } = await conversionApi.convert({
          s3_key: first.s3_key, source_format: "pdf", target_format: format, document_id: first.id });
        setResults([{ label: `Converted.${format}`, url: data.download_url }]);
      } else if (tool === "ocr") {
        await ocrApi.process(first.id, first.s3_key);
        setResults([{ label: "Open searchable document in editor", href: `/editor/${first.id}` }]);
      }
      setDone(true);
      toast.success("Done!");
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Operation failed");
    } finally { setBusy(false); }
  };

  const Icon = def.icon;

  return (
    <div className="h-full overflow-y-auto bg-slate-50/50">
      <div className="max-w-2xl mx-auto px-6 py-10">
        <Link href="/tools" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-6">
          <ArrowLeft className="w-4 h-4" /> All tools
        </Link>

        <div className="flex items-center gap-3 mb-1">
          <div className="w-11 h-11 rounded-xl bg-brand-50 flex items-center justify-center">
            <Icon className="w-6 h-6 text-brand-600" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{def.title}</h1>
        </div>
        <p className="text-slate-500 mb-8">{def.desc}</p>

        {/* Dropzone */}
        <label className="block border-2 border-dashed border-slate-200 rounded-2xl bg-white hover:border-brand-300 transition-colors cursor-pointer p-10 text-center">
          <input type="file" accept={def.accept ?? "application/pdf"} multiple={def.multiple} className="hidden"
            onChange={(e) => onPick(e.target.files)} />
          <Upload className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-700 font-medium">{def.toPdf ? "Choose a file" : def.multiple ? "Choose PDFs" : "Choose a PDF"}</p>
          <p className="text-slate-500 text-sm mt-1">or drag & drop here</p>
        </label>

        {/* Selected files */}
        {files.length > 0 && (
          <div className="mt-4 space-y-2">
            {files.map((f, i) => (
              <div key={i} className="flex items-center justify-between bg-white border border-slate-100 rounded-xl px-4 py-2.5">
                <span className="text-sm text-slate-700 truncate">{f.file.name}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-500">{formatBytes(f.file.size)}</span>
                  <button onClick={() => setFiles((p) => p.filter((_, idx) => idx !== i))} className="text-slate-500 hover:text-red-500"><X className="w-4 h-4" /></button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Options */}
        {tool === "convert" && files.length > 0 && (
          <div className="mt-5 flex items-center gap-3">
            <label className="text-sm text-slate-600">Convert to</label>
            <select value={format} onChange={(e) => setFormat(e.target.value)}
              className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white">
              {def.formats!.map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
            </select>
          </div>
        )}
        {tool === "translate" && files.length > 0 && (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <label className="text-sm text-slate-600">From</label>
            <select value={fromLang} onChange={(e) => setFromLang(e.target.value)} aria-label="Source language"
              className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white">
              {Object.entries(LANGS).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
            <label className="text-sm text-slate-600">To</label>
            <select value={toLang} onChange={(e) => setToLang(e.target.value)} aria-label="Target language"
              className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white">
              {Object.entries(LANGS).filter(([c]) => c !== "auto")
                .map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </div>
        )}
        {tool === "compress" && files.length > 0 && (
          <div className="mt-5 flex items-center gap-3">
            <label className="text-sm text-slate-600">Quality</label>
            <select value={quality} onChange={(e) => setQuality(e.target.value as "low" | "medium" | "high")}
              className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white">
              <option value="low">Smallest file (low quality)</option>
              <option value="medium">Balanced (recommended)</option>
              <option value="high">Best quality (larger file)</option>
            </select>
          </div>
        )}
        {def.needsPassword && files.length > 0 && (
          <div className="mt-5">
            <label className="text-sm text-slate-600">
              {tool === "unlock" ? "Current password" : "Set a password"}
              {tool === "unlock" && <span className="text-slate-500"> (leave blank if the file just has permissions)</span>}
            </label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={tool === "unlock" ? "password to remove" : "choose a password"}
              className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
        )}
        {tool === "split" && files.length > 0 && (
          <div className="mt-5">
            <label className="text-sm text-slate-600">Page ranges <span className="text-slate-500">(optional, e.g. 1-3, 4-6)</span></label>
            <input value={ranges} onChange={(e) => setRanges(e.target.value)} placeholder="leave empty to split every page"
              className="mt-1 w-full border border-slate-200 rounded-lg px-3 py-2 text-sm bg-white" />
          </div>
        )}

        {/* Action */}
        <button onClick={run} disabled={busy || files.length === 0}
          className="btn-primary w-full justify-center py-3 mt-6 text-base disabled:opacity-50">
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : def.cta}
        </button>

        {/* Translated text preview */}
        {done && tool === "translate" && translated && (
          <div className="mt-6 bg-white border border-slate-200 rounded-2xl p-5">
            <p className="text-sm font-medium text-slate-700 mb-2">Preview</p>
            <div className="max-h-64 overflow-y-auto text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
              {translated}
            </div>
          </div>
        )}

        {/* Results */}
        {done && results.length > 0 && (
          <div className="mt-6 bg-white border border-green-100 rounded-2xl p-5">
            <p className="flex items-center gap-2 text-green-700 font-medium mb-3"><CheckCircle2 className="w-5 h-5" /> Ready</p>
            <div className="space-y-2">
              {results.map((r, i) => r.href ? (
                <Link key={i} href={r.href} className="btn-secondary w-full justify-center gap-2">{r.label}</Link>
              ) : (
                <a key={i} href={r.url} target="_blank" rel="noreferrer" className="btn-secondary w-full justify-center gap-2">
                  <Download className="w-4 h-4" /> {r.label}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
