"use client";
import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, ShieldCheck, Bell, Palette, KeyRound, Trash2, MailCheck } from "lucide-react";
import toast from "react-hot-toast";
import api, { keysApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { cn } from "@/lib/utils";

const profileSchema = z.object({
  full_name: z.string().min(1),
  email:     z.string().email(),
});

const passwordSchema = z.object({
  current_password: z.string().min(8),
  new_password:     z.string().min(8),
  confirm:          z.string(),
}).refine((d) => d.new_password === d.confirm, { message: "Passwords don't match", path: ["confirm"] });

type ProfileForm   = z.infer<typeof profileSchema>;
type PasswordForm  = z.infer<typeof passwordSchema>;

export default function SettingsPage() {
  const { user, fetchMe } = useAuthStore();
  const [tab, setTab] = useState<"profile" | "security" | "notifications" | "apikeys">("profile");
  const [mfaSetup, setMfaSetup] = useState<{ secret: string; qr_url: string } | null>(null);
  const [mfaCode,  setMfaCode]  = useState("");
  const [keys, setKeys]         = useState<{ id: string; name: string; prefix?: string; created_at: string }[]>([]);
  const [newKeyName, setNewKeyName] = useState("");

  const loadKeys = async () => { try { setKeys((await keysApi.list()).data); } catch {} };
  useEffect(() => { if (tab === "apikeys") loadKeys(); }, [tab]);

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    try {
      const { data } = await keysApi.create(newKeyName.trim());
      if (data.key) { await navigator.clipboard.writeText(data.key).catch(() => {});
        toast.success("Key created & copied — it won't be shown again"); }
      setNewKeyName(""); loadKeys();
    } catch { toast.error("Failed to create key"); }
  };
  const revokeKey = async (id: string) => {
    try { await keysApi.revoke(id); toast.success("Key revoked"); loadKeys(); }
    catch { toast.error("Failed to revoke"); }
  };

  const resendVerification = async () => {
    try {
      const { data } = await api.post("/auth/resend-verification");
      if (data.token) {
        // dev/self-host without SMTP: the API returns the token directly — verify in-app
        toast("Email isn't configured on this server — verifying directly…", { icon: "ℹ️" });
        window.location.href = `/verify-email?token=${data.token}`;
      } else {
        toast.success("Verification email sent");
      }
    } catch { toast.error("Could not send verification email"); }
  };

  const profileForm = useForm<ProfileForm>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user?.full_name ?? "", email: user?.email ?? "" },
  });

  const passwordForm = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) });

  const saveProfile = async (data: ProfileForm) => {
    try {
      await api.patch("/auth/me", data);
      await fetchMe();
      toast.success("Profile updated");
    } catch { toast.error("Update failed"); }
  };

  const changePassword = async (data: PasswordForm) => {
    try {
      await api.post("/auth/change-password", {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      toast.success("Password changed");
      passwordForm.reset();
    } catch { toast.error("Failed to change password"); }
  };

  const setupMfa = async () => {
    try {
      const { data } = await api.post("/auth/mfa/setup");
      setMfaSetup(data);
    } catch { toast.error("MFA setup failed"); }
  };

  const verifyMfa = async () => {
    try {
      await api.post("/auth/mfa/verify", { code: mfaCode });
      toast.success("MFA enabled");
      setMfaSetup(null);
      fetchMe();
    } catch { toast.error("Invalid code"); }
  };

  const tabs = [
    { key: "profile",       label: "Profile",       icon: Palette },
    { key: "security",      label: "Security",      icon: ShieldCheck },
    { key: "notifications", label: "Notifications", icon: Bell },
    { key: "apikeys",       label: "API Keys",      icon: KeyRound },
  ] as const;

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Settings</h1>

      <div className="flex gap-1 mb-8 bg-slate-100 rounded-lg p-1 w-fit">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
              tab === key ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-700"
            )}>
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>

      {tab === "profile" && !user?.is_verified && (
        <div className="card p-4 mb-4 flex items-center justify-between bg-amber-50 border-amber-200">
          <p className="text-sm text-amber-800">Your email is not verified yet.</p>
          <button onClick={resendVerification} className="btn-secondary text-sm gap-1">
            <MailCheck className="w-4 h-4" /> Resend verification
          </button>
        </div>
      )}

      {tab === "profile" && (
        <div className="card p-6">
          <h2 className="font-semibold text-slate-900 mb-4">Profile information</h2>
          <form onSubmit={profileForm.handleSubmit(saveProfile)} className="space-y-4">
            <div>
              <label className="label">Full name</label>
              <input {...profileForm.register("full_name")} className="input" />
            </div>
            <div>
              <label className="label">Email</label>
              <input {...profileForm.register("email")} type="email" className="input" />
            </div>
            <button type="submit" disabled={profileForm.formState.isSubmitting} className="btn-primary">
              {profileForm.formState.isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Save changes"}
            </button>
          </form>
        </div>
      )}

      {tab === "security" && (
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="font-semibold text-slate-900 mb-4">Change password</h2>
            <form onSubmit={passwordForm.handleSubmit(changePassword)} className="space-y-4">
              <div>
                <label className="label">Current password</label>
                <input {...passwordForm.register("current_password")} type="password" className="input" />
              </div>
              <div>
                <label className="label">New password</label>
                <input {...passwordForm.register("new_password")} type="password" className="input" />
              </div>
              <div>
                <label className="label">Confirm new password</label>
                <input {...passwordForm.register("confirm")} type="password" className="input" />
                {passwordForm.formState.errors.confirm && (
                  <p className="text-red-500 text-xs mt-1">{passwordForm.formState.errors.confirm.message}</p>
                )}
              </div>
              <button type="submit" disabled={passwordForm.formState.isSubmitting} className="btn-primary">
                {passwordForm.formState.isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Update password"}
              </button>
            </form>
          </div>

          <div className="card p-6">
            <h2 className="font-semibold text-slate-900 mb-1">Two-factor authentication</h2>
            <p className="text-sm text-slate-500 mb-4">
              {user?.mfa_enabled ? "MFA is enabled on your account." : "Add an extra layer of security with TOTP."}
            </p>
            {!user?.mfa_enabled && !mfaSetup && (
              <button onClick={setupMfa} className="btn-secondary">Enable MFA</button>
            )}
            {mfaSetup && (
              <div className="space-y-4">
                <p className="text-sm text-slate-600">Scan this QR code with your authenticator app:</p>
                <img src={`https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(mfaSetup.qr_url)}&size=180x180`} alt="QR Code" className="rounded-lg border" />
                <div>
                  <label className="label">Enter 6-digit code</label>
                  <input value={mfaCode} onChange={(e) => setMfaCode(e.target.value)}
                    maxLength={6} placeholder="000000" className="input w-32" />
                </div>
                <button onClick={verifyMfa} className="btn-primary">Verify & Enable</button>
              </div>
            )}
            {user?.mfa_enabled && (
              <span className="badge bg-green-100 text-green-700">MFA Active</span>
            )}
          </div>
        </div>
      )}

      {tab === "notifications" && (
        <div className="card p-6 space-y-4">
          <h2 className="font-semibold text-slate-900 mb-2">Email notifications</h2>
          {["Document shared with you", "AI processing complete", "New comment on document", "Billing & invoices"].map((item) => (
            <div key={item} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
              <span className="text-sm text-slate-700">{item}</span>
              <input type="checkbox" defaultChecked className="rounded accent-brand-600" />
            </div>
          ))}
        </div>
      )}

      {tab === "apikeys" && (
        <div className="card p-6 space-y-4">
          <div>
            <h2 className="font-semibold text-slate-900 mb-1">API keys</h2>
            <p className="text-sm text-slate-500">Use these to access the PDFForge API with the <code>X-API-Key</code> header.</p>
          </div>
          <div className="flex gap-2">
            <input value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)}
              placeholder="Key name (e.g. CI pipeline)" className="input flex-1" />
            <button onClick={createKey} className="btn-primary whitespace-nowrap">Create key</button>
          </div>
          <div className="divide-y divide-slate-100">
            {keys.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500">No API keys yet.</p>
            ) : keys.map((k) => (
              <div key={k.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm font-medium text-slate-800">{k.name}</p>
                  <p className="text-xs text-slate-500 font-mono">{k.prefix ? `${k.prefix}…` : "••••"}</p>
                </div>
                <button onClick={() => revokeKey(k.id)} className="text-red-500 hover:bg-red-50 p-2 rounded-lg" title="Revoke">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
