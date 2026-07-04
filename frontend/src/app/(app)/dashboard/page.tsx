"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  FileText, MoreVertical, Trash2, Download, Share2, Loader2, Search,
  FolderPlus, Pencil, FolderInput,
} from "lucide-react";
import { documentsApi, foldersApi } from "@/lib/api";
import { formatRelative, formatBytes, cn } from "@/lib/utils";
import UploadButton from "@/components/dashboard/UploadButton";
import toast from "react-hot-toast";

interface Doc {
  id:            string;
  original_name: string;
  file_size:     number;
  page_count:    number | null;
  status:        string;
  folder_id:     string | null;
  created_at:    string;
}
interface FolderT { id: string; name: string; }
interface Usage { documents: number; used_bytes: number; limit_bytes: number | null; plan: string; }

export default function DashboardPage() {
  const [docs, setDocs]         = useState<Doc[]>([]);
  const [folders, setFolders]   = useState<FolderT[]>([]);
  const [activeFolder, setActiveFolder] = useState<string | null>(null); // null = all
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [moveOpen, setMoveOpen] = useState<string | null>(null);
  const [usage, setUsage]       = useState<Usage | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, f, u] = await Promise.all([
        documentsApi.list(),
        foldersApi.list().catch(() => ({ data: [] })),
        documentsApi.usage().catch(() => ({ data: null })),
      ]);
      setDocs(d.data); setFolders(f.data); setUsage(u.data);
    } catch { toast.error("Failed to load documents"); }
    finally  { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const createFolder = async () => {
    const name = window.prompt("Folder name");
    if (!name?.trim()) return;
    try { await foldersApi.create(name.trim()); toast.success("Folder created"); load(); }
    catch { toast.error("Failed to create folder"); }
  };

  const deleteDoc = async (id: string) => {
    if (!confirm("Delete this document?")) return;
    try { await documentsApi.delete(id); setDocs((d) => d.filter((doc) => doc.id !== id)); toast.success("Deleted"); }
    catch { toast.error("Delete failed"); }
  };
  const downloadDoc = async (id: string) => {
    try { const { data } = await documentsApi.download(id); window.open(data.url, "_blank"); }
    catch { toast.error("Download failed"); }
  };
  const shareDoc = async (id: string) => {
    try {
      const { data } = await documentsApi.share(id, { permission: "view" });
      await navigator.clipboard.writeText(data.share_url).catch(() => {});
      toast.success("Share link copied");
    } catch { toast.error("Failed to create share link"); }
    finally { setMenuOpen(null); }
  };
  const renameDoc = async (id: string, current: string) => {
    const name = window.prompt("Rename document", current);
    if (!name?.trim() || name === current) return;
    try { await documentsApi.update(id, { original_name: name.trim() });
      setDocs((d) => d.map((x) => x.id === id ? { ...x, original_name: name.trim() } : x));
      toast.success("Renamed"); }
    catch { toast.error("Rename failed"); }
    finally { setMenuOpen(null); }
  };
  const moveDoc = async (id: string, folderId: string | null) => {
    try { await documentsApi.update(id, { folder_id: folderId });
      setDocs((d) => d.map((x) => x.id === id ? { ...x, folder_id: folderId } : x));
      toast.success("Moved"); }
    catch { toast.error("Move failed"); }
    finally { setMoveOpen(null); setMenuOpen(null); }
  };

  const filtered = docs
    .filter((d) => activeFolder === null || d.folder_id === activeFolder)
    .filter((d) => d.original_name.toLowerCase().includes(search.toLowerCase()));

  const chip = (active: boolean) => cn(
    "px-3.5 py-1.5 rounded-full text-sm whitespace-nowrap transition-colors",
    active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200",
  );

  return (
    <div className="h-full overflow-y-auto bg-slate-50/50">
      <div className="max-w-6xl mx-auto px-6 sm:px-10 py-10">
        {/* Header */}
        <div className="flex items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">My documents</h1>
            <p className="text-slate-500 text-sm mt-1.5">
              {filtered.length} file{filtered.length !== 1 ? "s" : ""}
              {usage && (
                <span data-testid="storage-usage">
                  {" · "}{formatBytes(usage.used_bytes)}
                  {usage.limit_bytes ? ` of ${formatBytes(usage.limit_bytes, 0)} used` : " used"}
                </span>
              )}
            </p>
            {usage?.limit_bytes ? (
              <div className="w-56 h-1.5 bg-slate-100 rounded-full mt-2 overflow-hidden">
                <div
                  className={cn("h-full rounded-full transition-all",
                    usage.used_bytes / usage.limit_bytes > 0.9 ? "bg-red-400" : "bg-brand-500")}
                  style={{ width: `${Math.min(100, (usage.used_bytes / usage.limit_bytes) * 100)}%` }}
                />
              </div>
            ) : null}
          </div>
          <UploadButton onUploaded={load} />
        </div>

        {/* Search */}
        <div className="relative mb-6 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input type="text" placeholder="Search documents…" value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white border border-slate-200 text-sm
                       placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-300" />
        </div>

        {/* Folder chips */}
        <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-1">
          <button onClick={() => setActiveFolder(null)} className={chip(activeFolder === null)}>All documents</button>
          {folders.map((f) => (
            <button key={f.id} onClick={() => setActiveFolder(f.id)} className={chip(activeFolder === f.id)}>{f.name}</button>
          ))}
          <button onClick={createFolder}
            className="px-3.5 py-1.5 rounded-full text-sm whitespace-nowrap border border-dashed border-slate-300
                       text-slate-500 hover:border-brand-300 hover:text-brand-600 flex items-center gap-1.5">
            <FolderPlus className="w-3.5 h-3.5" /> New folder
          </button>
        </div>

        {/* Grid */}
        {loading ? (
          <div className="flex justify-center items-center h-72"><Loader2 className="w-7 h-7 animate-spin text-brand-400" /></div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-72 text-center">
            <div className="w-16 h-16 rounded-2xl bg-white border border-slate-100 flex items-center justify-center mb-4">
              <FileText className="w-7 h-7 text-slate-300" />
            </div>
            <p className="text-slate-600 font-medium">No documents here yet</p>
            <p className="text-slate-500 text-sm mt-1">Upload a PDF to get started</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
            {filtered.map((doc) => (
              <div key={doc.id}
                className="relative group rounded-2xl bg-white border border-slate-100 p-3
                           hover:shadow-lg hover:shadow-slate-200/60 hover:-translate-y-0.5 transition-all duration-150">
                <Link href={`/editor/${doc.id}`} className="block">
                  <div className="aspect-[3/4] rounded-xl bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center mb-3">
                    <FileText className="w-10 h-10 text-slate-300 group-hover:text-brand-300 transition-colors" />
                  </div>
                  <p className="text-sm font-medium text-slate-800 truncate" title={doc.original_name}>{doc.original_name}</p>
                  <p className="text-xs text-slate-500 mt-1">
                    {doc.page_count ? `${doc.page_count} page${doc.page_count !== 1 ? "s" : ""} · ` : ""}{formatRelative(doc.created_at)}
                  </p>
                  {doc.status !== "ready" && (
                    <span className="inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-600 capitalize">{doc.status}</span>
                  )}
                </Link>

                {/* Hover menu in the corner */}
                <div className="absolute top-2.5 right-2.5">
                  <button onClick={() => { setMenuOpen(menuOpen === doc.id ? null : doc.id); setMoveOpen(null); }}
                    className="w-7 h-7 rounded-lg bg-white/90 border border-slate-100 shadow-sm flex items-center justify-center
                               text-slate-500 hover:text-slate-800 opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity">
                    <MoreVertical className="w-4 h-4" />
                  </button>
                  {menuOpen === doc.id && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => { setMenuOpen(null); setMoveOpen(null); }} />
                      <div className="absolute right-0 mt-1 w-44 bg-white rounded-xl shadow-xl border border-slate-100 z-20 py-1 animate-fade-in">
                        <button onClick={() => renameDoc(doc.id, doc.original_name)} className="flex items-center gap-2 w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                          <Pencil className="w-4 h-4" /> Rename
                        </button>
                        <button onClick={() => setMoveOpen(moveOpen === doc.id ? null : doc.id)} className="flex items-center gap-2 w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                          <FolderInput className="w-4 h-4" /> Move to…
                        </button>
                        {moveOpen === doc.id && (
                          <div className="max-h-40 overflow-auto border-y border-slate-100 my-1 bg-slate-50/50">
                            <button onClick={() => moveDoc(doc.id, null)} className="block w-full text-left px-6 py-1.5 text-xs text-slate-600 hover:bg-slate-100">No folder</button>
                            {folders.map((f) => (
                              <button key={f.id} onClick={() => moveDoc(doc.id, f.id)} className="block w-full text-left px-6 py-1.5 text-xs text-slate-600 hover:bg-slate-100 truncate">{f.name}</button>
                            ))}
                          </div>
                        )}
                        <button onClick={() => downloadDoc(doc.id)} className="flex items-center gap-2 w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                          <Download className="w-4 h-4" /> Download
                        </button>
                        <button onClick={() => shareDoc(doc.id)} className="flex items-center gap-2 w-full px-4 py-2 text-sm text-slate-700 hover:bg-slate-50">
                          <Share2 className="w-4 h-4" /> Share
                        </button>
                        <button onClick={() => { deleteDoc(doc.id); setMenuOpen(null); }} className="flex items-center gap-2 w-full px-4 py-2 text-sm text-red-500 hover:bg-red-50">
                          <Trash2 className="w-4 h-4" /> Delete
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
