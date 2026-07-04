"use client";
import { useEffect, useState } from "react";
import { X, Loader2, RotateCcw } from "lucide-react";
import { documentsApi } from "@/lib/api";
import { formatRelative, formatBytes } from "@/lib/utils";
import toast from "react-hot-toast";

interface Version { version: number; file_size: number; comment?: string; created_at: string; }

export default function VersionHistory({ documentId, onClose, onRestored }: {
  documentId: string; onClose: () => void; onRestored: () => void;
}) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    documentsApi.versions(documentId).then(({ data }) => setVersions(data)).catch(() => setVersions([]));
  }, [documentId]);

  const restore = async (v: number) => {
    setBusy(v);
    try { await documentsApi.restoreVersion(documentId, v); toast.success(`Restored version ${v}`); onRestored(); onClose(); }
    catch { toast.error("Restore failed"); }
    finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-slate-900">Version history</h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-600"><X className="w-5 h-5" /></button>
        </div>
        {versions === null ? (
          <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-brand-500" /></div>
        ) : versions.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">No previous versions yet. Edits create versions you can restore.</p>
        ) : (
          <ul className="space-y-2 max-h-80 overflow-auto">
            {versions.map((v) => (
              <li key={v.version} className="flex items-center justify-between border border-slate-100 rounded-lg px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-slate-800">Version {v.version}</p>
                  <p className="text-xs text-slate-500">{formatBytes(v.file_size)} · {formatRelative(v.created_at)}</p>
                </div>
                <button onClick={() => restore(v.version)} disabled={busy === v.version}
                  className="btn-secondary text-xs gap-1 disabled:opacity-50">
                  {busy === v.version ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                  Restore
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
