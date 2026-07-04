"use client";
import { useEffect, useState } from "react";
import { X, Send, Check, Trash2, Loader2, MessageSquare } from "lucide-react";
import { documentsApi } from "@/lib/api";
import { formatRelative } from "@/lib/utils";
import toast from "react-hot-toast";

interface Comment {
  id: string; content: string; page: number | null; resolved: boolean; created_at: string;
}

export default function CommentsPanel({ documentId, currentPage, onClose }: {
  documentId: string; currentPage: number; onClose: () => void;
}) {
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [text, setText] = useState("");
  const [pinPage, setPinPage] = useState(true);
  const [sending, setSending] = useState(false);

  const load = async () => {
    try { setComments((await documentsApi.comments(documentId)).data); } catch { setComments([]); }
  };
  useEffect(() => { load(); }, [documentId]);

  const add = async () => {
    if (!text.trim()) return;
    setSending(true);
    try {
      await documentsApi.addComment(documentId, { content: text.trim(), page: pinPage ? currentPage : null });
      setText(""); load();
    } catch { toast.error("Failed to add comment"); }
    finally { setSending(false); }
  };
  const toggleResolve = async (c: Comment) => {
    try { await documentsApi.updateComment(documentId, c.id, { resolved: !c.resolved });
      setComments((xs) => xs!.map((x) => x.id === c.id ? { ...x, resolved: !x.resolved } : x)); }
    catch { toast.error("Failed"); }
  };
  const remove = async (id: string) => {
    try { await documentsApi.deleteComment(documentId, id);
      setComments((xs) => xs!.filter((x) => x.id !== id)); }
    catch { toast.error("Failed to delete"); }
  };

  return (
    <aside className="w-80 flex-shrink-0 border-l border-slate-200 bg-white flex flex-col h-full">
      <div className="flex items-center justify-between px-4 h-12 border-b border-slate-100">
        <span className="font-semibold text-sm flex items-center gap-2"><MessageSquare className="w-4 h-4" /> Comments</span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-600"><X className="w-4 h-4" /></button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {comments === null ? (
          <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-brand-500" /></div>
        ) : comments.length === 0 ? (
          <p className="text-center text-sm text-slate-500 py-8">No comments yet.</p>
        ) : comments.map((c) => (
          <div key={c.id} className={`rounded-lg border p-3 text-sm ${c.resolved ? "bg-slate-50 border-slate-100 opacity-70" : "border-slate-200"}`}>
            <p className={c.resolved ? "line-through text-slate-500" : "text-slate-800"}>{c.content}</p>
            <div className="flex items-center justify-between mt-2 text-[11px] text-slate-500">
              <span>{c.page ? `p.${c.page} · ` : ""}{formatRelative(c.created_at)}</span>
              <span className="flex items-center gap-1">
                <button onClick={() => toggleResolve(c)} title={c.resolved ? "Reopen" : "Resolve"}
                  className={`p-1 rounded hover:bg-slate-100 ${c.resolved ? "text-green-600" : "text-slate-500"}`}><Check className="w-3.5 h-3.5" /></button>
                <button onClick={() => remove(c.id)} title="Delete" className="p-1 rounded hover:bg-red-50 text-slate-500 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-100 p-3 space-y-2">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
          placeholder="Add a comment…" className="input text-sm resize-none"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) add(); }} />
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            <input type="checkbox" checked={pinPage} onChange={(e) => setPinPage(e.target.checked)} className="rounded accent-brand-600" />
            Pin to page {currentPage}
          </label>
          <button onClick={add} disabled={sending || !text.trim()} className="btn-primary text-sm gap-1 disabled:opacity-50">
            {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />} Send
          </button>
        </div>
      </div>
    </aside>
  );
}
