"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, MailCheck, XCircle, FileText } from "lucide-react";
import { authApi } from "@/lib/api";

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [state, setState] = useState<"working" | "ok" | "error">(token ? "working" : "error");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    if (!token) { setDetail("No verification token in the link."); return; }
    authApi.verifyEmail(token)
      .then(() => setState("ok"))
      .catch((e) => {
        setState("error");
        setDetail(e?.response?.data?.detail ?? "Verification failed — the link may have expired.");
      });
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-8 shadow-sm text-center animate-fade-in">
        <div className="flex items-center justify-center gap-2 mb-6">
          <FileText className="w-6 h-6 text-brand-600" />
          <span className="text-xl font-bold">PDF Editor</span>
        </div>

        {state === "working" && (
          <>
            <Loader2 className="w-10 h-10 animate-spin text-brand-500 mx-auto mb-4" />
            <h1 className="text-xl font-semibold text-slate-900">Verifying your email…</h1>
          </>
        )}

        {state === "ok" && (
          <>
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
              <MailCheck className="w-7 h-7 text-green-600" />
            </div>
            <h1 className="text-xl font-semibold text-slate-900">Email verified</h1>
            <p className="text-slate-500 mt-1 mb-6">Your email address is confirmed. You&apos;re all set.</p>
            <Link href="/dashboard" className="btn-primary justify-center w-full py-2.5">Go to dashboard</Link>
          </>
        )}

        {state === "error" && (
          <>
            <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
              <XCircle className="w-7 h-7 text-red-500" />
            </div>
            <h1 className="text-xl font-semibold text-slate-900">Verification failed</h1>
            <p className="text-slate-500 mt-1 mb-6">{detail}</p>
            <Link href="/settings" className="btn-secondary justify-center w-full py-2.5">Request a new link in Settings</Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-brand-400" /></div>}>
      <VerifyEmailInner />
    </Suspense>
  );
}
