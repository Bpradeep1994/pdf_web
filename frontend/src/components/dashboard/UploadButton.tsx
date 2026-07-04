"use client";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileText, Loader2 } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";
import { documentsApi } from "@/lib/api";
import toast from "react-hot-toast";

interface Props {
  onUploaded: () => void;
}

export default function UploadButton({ onUploaded }: Props) {
  const [open, setOpen]         = useState(false);
  const [files, setFiles]       = useState<File[]>([]);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [uploading, setUploading] = useState(false);

  const MAX_MB = 100;

  const onDrop = useCallback((accepted: File[], rejected: { file: File }[]) => {
    // Tell the user WHY a file was dropped instead of silently discarding it.
    const rejectedNames = (rejected ?? []).map((r) => r.file.name);
    const pdfs: File[] = [];
    const tooBig: string[] = [];
    for (const f of accepted) {
      if (f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
        rejectedNames.push(f.name);
      } else if (f.size > MAX_MB * 1024 * 1024) {
        tooBig.push(f.name);
      } else {
        pdfs.push(f);
      }
    }
    if (rejectedNames.length) toast.error(`Only PDF files are allowed — skipped ${rejectedNames.join(", ")}`);
    if (tooBig.length) toast.error(`Over ${MAX_MB} MB — skipped ${tooBig.join(", ")}`);
    // de-dupe by name+size so the same file isn't queued twice
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...pdfs.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxSize: MAX_MB * 1024 * 1024,
    multiple: true,
  });

  const remove = (name: string) => setFiles((prev) => prev.filter((f) => f.name !== name));

  const upload = async () => {
    if (!files.length) return;
    setUploading(true);
    const failed: File[] = [];
    let ok = 0;
    for (const file of files) {
      try {
        await documentsApi.upload(file, (pct) =>
          setProgress((p) => ({ ...p, [file.name]: pct }))
        );
        ok++;
      } catch (e: any) {
        const detail = e?.response?.data?.detail ?? "upload failed";
        toast.error(`${file.name}: ${detail}`);
        failed.push(file);
      }
    }
    setUploading(false);
    if (ok > 0) {
      toast.success(`${ok} file(s) uploaded`);
      onUploaded();                    // always refresh what DID succeed
    }
    if (failed.length === 0) {
      setFiles([]); setProgress({}); setOpen(false);
    } else {
      // keep only the files that failed so the user can retry just those
      setFiles(failed);
      setProgress({});
    }
  };

  return (
    <>
      <button onClick={() => setOpen(true)} className="btn-primary">
        <Upload className="w-4 h-4" /> Upload PDF
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 animate-fade-in">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold">Upload PDF files</h2>
              <button onClick={() => setOpen(false)} className="text-slate-500 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div
              {...getRootProps()}
              className={cn(
                "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
                isDragActive ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-brand-300"
              )}
            >
              <input {...getInputProps()} />
              <Upload className="w-10 h-10 text-slate-300 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-700">Drop PDFs here or click to browse</p>
              <p className="text-xs text-slate-500 mt-1">Only PDF files accepted</p>
            </div>

            {files.length > 0 && (
              <ul className="mt-4 space-y-2 max-h-48 overflow-y-auto">
                {files.map((f) => (
                  <li key={f.name} className="flex items-center gap-3 text-sm">
                    <FileText className="w-4 h-4 text-brand-500 flex-shrink-0" />
                    <span className="flex-1 truncate text-slate-700">{f.name}</span>
                    <span className="text-slate-500 flex-shrink-0">{formatBytes(f.size)}</span>
                    {progress[f.name] !== undefined && (
                      <span className="text-brand-600 flex-shrink-0">{progress[f.name]}%</span>
                    )}
                    {!uploading && (
                      <button onClick={() => remove(f.name)} className="text-slate-300 hover:text-red-400">
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="flex justify-end gap-2 mt-6">
              <button onClick={() => setOpen(false)} className="btn-secondary">Cancel</button>
              <button onClick={upload} disabled={!files.length || uploading} className="btn-primary">
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {uploading ? "Uploading…" : `Upload ${files.length || ""} file(s)`}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
