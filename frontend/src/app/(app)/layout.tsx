"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import NotificationBell from "@/components/NotificationBell";
import { useAuthStore, isAuthenticated } from "@/lib/auth";
import { analyticsApi } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router  = useRouter();
  const fetchMe = useAuthStore((s) => s.fetchMe);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    fetchMe();
    // one pageview per session → powers admin Top Countries / Traffic Sources
    try {
      if (!sessionStorage.getItem("tracked")) {
        sessionStorage.setItem("tracked", "1");
        let source = "Direct";
        const ref = document.referrer;
        if (ref) {
          try {
            const host = new URL(ref).hostname.replace(/^www\./, "");
            if (host.includes("google")) source = "Google";
            else if (/facebook|twitter|t\.co|linkedin|instagram|reddit/.test(host)) source = "Social";
            else if (host !== location.hostname) source = host;
          } catch {}
        }
        const country = (navigator.language.split("-")[1] || "").toUpperCase() || "Unknown";
        analyticsApi.track({ source, country, path: location.pathname }).catch(() => {});
      }
    } catch {}
  }, [fetchMe, router]);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="flex items-center justify-end gap-2 px-4 h-12 border-b border-slate-200 bg-white flex-shrink-0">
          <NotificationBell />
        </header>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
