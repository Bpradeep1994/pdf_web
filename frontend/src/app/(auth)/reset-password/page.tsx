"use client";
import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, KeyRound, CheckCircle2, FileText } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "@/lib/api";

function ResetPasswordInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [pw, setPw]           = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy]       = useState(false);
  const [done, setDone]       = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pw.length < 8) { toast.error("Password must be at least 8 characters"); return; }
    if (pw !== confirm) { toast.error("Passwords don't match"); return; }
    setBusy(true);
    try {
      await authApi.resetPasswordConfirm(token, pw);
      setDone(true);
      setTimeout(() => router.push("/login"), 2500);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Reset failed — the link may have expired");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-8 shadow-sm animate-fade-in">
        <div className="flex items-center gap-2 mb-6">
          <FileText className="w-6 h-6 text-brand-600" />
          <span className="text-xl font-bold">PDF Editor</span>
        </div>

        {done ? (
          <div className="text-center py-2">
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
              <CheckCircle2 className="w-7 h-7 text-green-600" />
            </div>
            <h1 className="text-xl font-semibold text-slate-900">Password updated</h1>
            <p className="text-slate-500 mt-1">Sign in with your new password.</p>
            <p className="text-xs text-slate-500 mt-3">Redirecting to sign in…</p>
          </div>
        ) : !token ? (
          <div className="text-center py-2">
            <h1 className="text-xl font-semibold text-slate-900">Invalid link</h1>
            <p className="text-slate-500 mt-1 mb-6">This reset link is missing its token.</p>
            <Link href="/forgot-password" className="btn-primary justify-center w-full py-2.5">Request a new link</Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-slate-900 mb-1">Set a new password</h1>
            <p className="text-slate-500 mb-6">Choose a strong password for your account.</p>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="label">New password</label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input value={pw} onChange={(e) => setPw(e.target.value)} type="password"
                    placeholder="••••••••" className="input pl-9" autoFocus />
                </div>
              </div>
              <div>
                <label className="label">Confirm password</label>
                <input value={confirm} onChange={(e) => setConfirm(e.target.value)} type="password"
                  placeholder="••••••••" className="input" />
              </div>
              <button type="submit" disabled={busy} className="btn-primary w-full justify-center py-2.5 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Update password"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-brand-400" /></div>}>
      <ResetPasswordInner />
    </Suspense>
  );
}
