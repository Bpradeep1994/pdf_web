"use client";
import { useEffect, useState } from "react";
import { Bell, CheckCheck } from "lucide-react";
import { notificationsApi } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

interface Notif { id: string; kind: string; title: string; body?: string; link?: string; read: boolean; created_at: string; }

export default function NotificationBell() {
  const [open, setOpen]     = useState(false);
  const [items, setItems]   = useState<Notif[]>([]);
  const [unread, setUnread] = useState(0);

  const loadCount = async () => {
    try { setUnread((await notificationsApi.unreadCount()).data.unread); } catch {}
  };
  useEffect(() => { loadCount(); const t = setInterval(loadCount, 30000); return () => clearInterval(t); }, []);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) { try { setItems((await notificationsApi.list()).data); } catch {} }
  };
  const markAll = async () => {
    try { await notificationsApi.markAllRead(); } catch {}
    setItems((xs) => xs.map((x) => ({ ...x, read: true }))); setUnread(0);
  };

  return (
    <div className="relative">
      <button onClick={toggle} className="relative p-2 rounded-lg text-slate-500 hover:bg-slate-100" aria-label="Notifications">
        <Bell className="w-5 h-5" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-slate-100 z-40 max-h-96 overflow-auto">
            <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
              <span className="font-semibold text-sm">Notifications</span>
              <button onClick={markAll} className="text-xs text-brand-600 hover:underline flex items-center gap-1">
                <CheckCheck className="w-3.5 h-3.5" /> Mark all read
              </button>
            </div>
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-slate-500">No notifications</div>
            ) : items.map((n) => (
              <a key={n.id} href={n.link || "#"}
                 className={`block px-4 py-3 border-b border-slate-50 hover:bg-slate-50 ${n.read ? "" : "bg-brand-50/40"}`}>
                <p className="text-sm font-medium text-slate-800">{n.title}</p>
                {n.body && <p className="text-xs text-slate-500 mt-0.5">{n.body}</p>}
                <p className="text-[10px] text-slate-500 mt-1">{formatRelative(n.created_at)}</p>
              </a>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
