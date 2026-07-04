"use client";
import { useState } from "react";
import Link from "next/link";
import { Loader2, MailCheck, FileText, ArrowLeft } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy]   = useState(false);
  const [sent, setSent]   = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email)) { toast.error("Enter a valid email"); return; }
    setBusy(true);
    try {
      await authApi.resetPasswordRequest(email.trim());
      setSent(true);
    } catch {
      toast.error("Could not send reset link — try again");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-8 shadow-sm animate-fade-in">
        <div className="flex items-center gap-2 mb-6">
          <FileText className="w-6 h-6 text-brand-600" />
          <span className="text-xl font-bold">PDF Editor</span>
        </div>

        {sent ? (
          <div className="text-center py-2">
            <div className="w-14 h-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
              <MailCheck className="w-7 h-7 text-green-600" />
            </div>
            <h1 className="text-xl font-semibold text-slate-900">Check your inbox</h1>
            <p className="text-slate-500 mt-1">
              If an account exists for <span className="font-medium text-slate-700">{email}</span>, a reset link is on its way.
            </p>
            <Link href="/login" className="btn-secondary justify-center w-full py-2.5 mt-6">Back to sign in</Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-slate-900 mb-1">Forgot your password?</h1>
            <p className="text-slate-500 mb-6">Enter your email and we&apos;ll send you a reset link.</p>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="label">Email</label>
                <input value={email} onChange={(e) => setEmail(e.target.value)} type="email"
                  placeholder="you@example.com" className="input" autoFocus />
              </div>
              <button type="submit" disabled={busy} className="btn-primary w-full justify-center py-2.5 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send reset link"}
              </button>
            </form>
            <Link href="/login" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mt-6">
              <ArrowLeft className="w-4 h-4" /> Back to sign in
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
