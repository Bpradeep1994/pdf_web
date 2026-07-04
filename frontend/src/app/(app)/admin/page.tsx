"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard, Users as UsersIcon, FileText, DollarSign, CreditCard, Receipt,
  LifeBuoy, BarChart3, Settings as SettingsIcon, ScrollText, Loader2, Shield,
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import { adminApi } from "@/lib/api";
import { useAuthStore, isStaff } from "@/lib/auth";
import { formatRelative, formatBytes, cn } from "@/lib/utils";
import toast from "react-hot-toast";

const MODULES = [
  { key: "dashboard",     label: "Dashboard",      icon: LayoutDashboard },
  { key: "users",         label: "Users",          icon: UsersIcon },
  { key: "documents",     label: "Documents",      icon: FileText },
  { key: "revenue",       label: "Revenue",        icon: DollarSign },
  { key: "subscriptions", label: "Subscriptions",  icon: CreditCard },
  { key: "invoices",      label: "Invoices",       icon: Receipt },
  { key: "support",       label: "Support Tickets",icon: LifeBuoy },
  { key: "analytics",     label: "Analytics",      icon: BarChart3 },
  { key: "settings",      label: "Settings",       icon: SettingsIcon },
  { key: "audit",         label: "Audit Logs",     icon: ScrollText },
] as const;
type ModKey = typeof MODULES[number]["key"];

const card = "bg-white border border-slate-100 rounded-2xl";
const th   = "text-left px-4 py-2.5 font-medium text-slate-500 text-xs uppercase tracking-wide";
const td   = "px-4 py-3 text-slate-700";

export default function AdminPage() {
  const { user } = useAuthStore();
  const router = useRouter();
  const [mod, setMod] = useState<ModKey>("dashboard");
  const [data, setData] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user && !isStaff(user)) router.replace("/dashboard");
  }, [user, router]);

  const load = useCallback(async (m: ModKey) => {
    setLoading(true);
    try {
      const fetcher: Record<string, () => Promise<any>> = {
        dashboard:     () => adminApi.kpis(),
        users:         () => adminApi.users(1, 50),
        documents:     () => adminApi.documents(1),
        revenue:       () => adminApi.revenue(),
        subscriptions: () => adminApi.subscriptions(1),
        invoices:      () => adminApi.invoices(1),
        support:       () => adminApi.tickets(),
        analytics:     () => adminApi.analytics(),
        settings:      () => adminApi.settings(),
        audit:         () => adminApi.auditLogs(1, 100),
      };
      const res = await fetcher[m]();
      setData((d) => ({ ...d, [m]: res.data }));
    } catch { toast.error("Failed to load"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (isStaff(user)) load(mod); }, [mod, user, load]);

  const d = data[mod];

  const updateUser = async (id: string, body: any, msg: string) => {
    try { await adminApi.updateUser(id, body); toast.success(msg); load("users"); }
    catch (e: any) { toast.error(e?.response?.data?.detail ?? "Failed"); }
  };
  const resetPw = async (id: string, email: string) => {
    try { await adminApi.resetUserPassword(id); toast.success(`Reset link sent to ${email}`); }
    catch { toast.error("Failed"); }
  };
  const deleteUser = async (id: string, email: string) => {
    if (!confirm(`Delete ${email}? This removes their account and data.`)) return;
    try { await adminApi.deleteUser(id); toast.success("User deleted"); load("users"); }
    catch (e: any) { toast.error(e?.response?.data?.detail ?? "Failed"); }
  };
  const setTicket = async (id: string, body: { status?: string; response?: string }) => {
    try { await adminApi.updateTicket(id, body); toast.success("Ticket updated"); load("support"); }
    catch { toast.error("Failed"); }
  };
  const saveSetting = async (key: string, value: object) => {
    try { await adminApi.putSetting(key, value); toast.success("Saved"); load("settings"); }
    catch { toast.error("Failed"); }
  };

  return (
    <div className="flex h-full bg-slate-50/50">
      {/* Sub-nav */}
      <aside className="w-60 flex-shrink-0 bg-white border-r border-slate-100 p-3 overflow-y-auto">
        <div className="flex items-center gap-2 px-2 py-3 mb-2">
          <Shield className="w-5 h-5 text-brand-600" />
          <span className="font-semibold text-slate-900">Super Admin</span>
        </div>
        {MODULES.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setMod(key)}
            className={cn("flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm mb-0.5 transition-colors",
              mod === key ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </aside>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 mb-6">
          {MODULES.find((m) => m.key === mod)?.label}
        </h1>

        {loading || !d ? (
          <div className="flex justify-center items-center h-64"><Loader2 className="w-7 h-7 animate-spin text-brand-400" /></div>
        ) : (
          <>
            {/* ── Dashboard (KPIs) ── */}
            {mod === "dashboard" && (
              <div className="space-y-6">
                {/* Users */}
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  <Stat label="Total users" value={d.users?.total?.toLocaleString()} sub={`+${d.users?.new_30d ?? 0} this month`} />
                  <Stat label="Active users" value={d.users?.active?.toLocaleString()} sub={`${d.users?.active_30d ?? 0} active 30d`} />
                  <Stat label="New users (7d)" value={d.users?.new_7d?.toLocaleString()} />
                </div>
                {/* Revenue */}
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  <Stat label="Total revenue" value={`$${(d.revenue?.total ?? 0).toLocaleString()}`} />
                  <Stat label="Monthly revenue" value={`$${(d.revenue?.monthly ?? 0).toLocaleString()}`} />
                  <Stat label="Annual revenue" value={`$${(d.revenue?.annual ?? 0).toLocaleString()}`} />
                </div>
                {/* Docs + storage + subs */}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <Stat label="PDF uploads" value={d.documents?.uploads?.toLocaleString()} />
                  <Stat label="PDF downloads" value={d.documents?.downloads?.toLocaleString()} />
                  <Stat label="Storage used" value={formatBytes(d.storage_bytes ?? 0)} />
                  <Stat label="Active subscriptions" value={d.active_subscriptions?.toLocaleString()} />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className={`${card} p-5`}>
                    <h3 className="font-medium text-slate-700 mb-4">Subscription growth (12 mo)</h3>
                    {(d.subscription_growth ?? []).length === 0 ? <Empty text="No data yet" /> : (
                      <ResponsiveContainer width="100%" height={200}>
                        <BarChart data={d.subscription_growth}>
                          <XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                          <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                  <div className={`${card} p-5`}>
                    <h3 className="font-medium text-slate-700 mb-4">Revenue (12 mo)</h3>
                    {(d.revenue_chart ?? []).length === 0 ? <Empty text="No revenue yet" /> : (
                      <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={d.revenue_chart}>
                          <XAxis dataKey="label" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                          <Line type="monotone" dataKey="value" stroke="#16a34a" strokeWidth={2} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <div className={`${card} p-5`}>
                    <h3 className="font-medium text-slate-700 mb-3">Top countries</h3>
                    {(d.top_countries ?? []).length === 0 ? <Empty text="No traffic data yet" /> :
                      d.top_countries.map((c: any) => (
                        <div key={c.label} className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
                          <span className="text-sm text-slate-700">{c.label}</span>
                          <span className="text-sm font-medium text-slate-500">{c.value}</span>
                        </div>
                      ))}
                  </div>
                  <div className={`${card} p-5`}>
                    <h3 className="font-medium text-slate-700 mb-3">Traffic sources</h3>
                    {(d.traffic_sources ?? []).length === 0 ? <Empty text="No traffic data yet" /> :
                      d.traffic_sources.map((s: any) => (
                        <div key={s.label} className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
                          <span className="text-sm text-slate-700">{s.label}</span>
                          <span className="text-sm font-medium text-slate-500">{s.value}</span>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── Users ── */}
            {mod === "users" && (
              <Table head={["Email", "Plan", "Access role", "Status", "Joined", "Actions"]}>
                {(d.items ?? []).map((u: any) => (
                  <tr key={u.id} className="border-t border-slate-50 hover:bg-slate-50/50">
                    <td className={td}>
                      <div className="text-slate-800">{u.full_name ?? "—"}</div>
                      <div className="text-xs text-slate-500">{u.email}</div>
                    </td>
                    <td className={td}>
                      <select value={u.role} onChange={(e) => updateUser(u.id, { role: e.target.value }, "Plan updated")}
                        className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white">
                        {["free", "pro", "business", "enterprise"].map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className={td}>
                      <select value={u.admin_level ?? "user"} onChange={(e) => updateUser(u.id, { admin_level: e.target.value }, "Role assigned")}
                        className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white">
                        {["user", "moderator", "admin", "superadmin"].map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    </td>
                    <td className={td}>
                      <select value={u.status ?? "active"} onChange={(e) => updateUser(u.id, { status: e.target.value }, "Status updated")}
                        className={cn("text-xs border rounded-lg px-2 py-1",
                          u.status === "banned" ? "border-red-200 text-red-700 bg-red-50"
                          : u.status === "suspended" ? "border-amber-200 text-amber-700 bg-amber-50"
                          : "border-slate-200 bg-white text-slate-700")}>
                        {["active", "suspended", "banned"].map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </td>
                    <td className={td}>{formatRelative(u.created_at)}</td>
                    <td className={td}>
                      <div className="flex items-center gap-3">
                        <button onClick={() => resetPw(u.id, u.email)} className="text-xs text-brand-600 hover:underline">Reset pw</button>
                        <button onClick={() => deleteUser(u.id, u.email)} className="text-xs text-red-600 hover:underline">Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </Table>
            )}

            {/* ── Documents ── */}
            {mod === "documents" && (
              <Table head={["Name", "Owner", "Pages", "Size", "Status", "Created"]}>
                {(d.items ?? []).map((x: any) => (
                  <tr key={x.id} className="border-t border-slate-50 hover:bg-slate-50/50">
                    <td className={td}>{x.original_name}</td>
                    <td className={td}>{x.owner_email ?? "—"}</td>
                    <td className={td}>{x.page_count ?? "—"}</td>
                    <td className={td}>{formatBytes(x.file_size ?? 0)}</td>
                    <td className={td}><Badge text={x.status} /></td>
                    <td className={td}>{formatRelative(x.created_at)}</td>
                  </tr>
                ))}
              </Table>
            )}

            {/* ── Revenue ── */}
            {mod === "revenue" && (
              <div className="space-y-6">
                <div className="grid grid-cols-3 gap-4">
                  <Stat label="Total revenue" value={`$${d.total_revenue?.toLocaleString()}`} />
                  <Stat label="Paid invoices" value={d.paid_invoices} />
                  <Stat label="Active subscriptions" value={d.active_subscriptions} />
                </div>
                <div className={`${card} p-5`}>
                  <h3 className="font-medium text-slate-700 mb-4">Revenue by month</h3>
                  {(d.revenue_chart ?? []).length === 0 ? <Empty text="No paid invoices yet" /> : (
                    <ResponsiveContainer width="100%" height={220}>
                      <LineChart data={d.revenue_chart}>
                        <XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                        <Line type="monotone" dataKey="revenue" stroke="#16a34a" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>
            )}

            {/* ── Subscriptions ── */}
            {mod === "subscriptions" && (
              <Table head={["User", "Plan", "Status", "Renews", "Since"]}>
                {(d.items ?? []).length === 0 ? <EmptyRow cols={5} text="No subscriptions" /> :
                  d.items.map((s: any) => (
                    <tr key={s.id} className="border-t border-slate-50 hover:bg-slate-50/50">
                      <td className={td}>{s.email ?? "—"}</td>
                      <td className={td}><Badge text={s.plan} /></td>
                      <td className={td}><Badge text={s.status} /></td>
                      <td className={td}>{s.current_period_end ? formatRelative(s.current_period_end) : "—"}</td>
                      <td className={td}>{formatRelative(s.created_at)}</td>
                    </tr>
                  ))}
              </Table>
            )}

            {/* ── Invoices ── */}
            {mod === "invoices" && (
              <Table head={["Invoice", "User", "Amount", "Status", "Date", ""]}>
                {(d.items ?? []).length === 0 ? <EmptyRow cols={6} text="No invoices" /> :
                  d.items.map((i: any) => (
                    <tr key={i.stripe_invoice_id} className="border-t border-slate-50 hover:bg-slate-50/50">
                      <td className={`${td} font-mono text-xs`}>{i.stripe_invoice_id?.slice(0, 18) ?? "—"}</td>
                      <td className={td}>{i.email ?? "—"}</td>
                      <td className={td}>{i.currency?.toUpperCase()} {i.amount}</td>
                      <td className={td}><Badge text={i.status} /></td>
                      <td className={td}>{formatRelative(i.created_at)}</td>
                      <td className={td}>{i.invoice_url && <a href={i.invoice_url} target="_blank" rel="noreferrer" className="text-xs text-brand-600 hover:underline">View</a>}</td>
                    </tr>
                  ))}
              </Table>
            )}

            {/* ── Support tickets ── */}
            {mod === "support" && (
              <div className="space-y-3">
                {(d.items ?? []).length === 0 ? <div className={`${card} p-10`}><Empty text="No support tickets" /></div> :
                  d.items.map((t: any) => (
                    <div key={t.id} className={`${card} p-4`}>
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-slate-800">{t.subject}</span>
                            <Badge text={t.priority} /><Badge text={t.status} />
                          </div>
                          <p className="text-sm text-slate-500 mt-1">{t.message}</p>
                          <p className="text-xs text-slate-500 mt-1">{t.user_email} · {formatRelative(t.created_at)}</p>
                          {t.response && <p className="text-sm text-slate-700 mt-2 bg-slate-50 rounded-lg p-2">↳ {t.response}</p>}
                        </div>
                        <div className="flex flex-col gap-1.5 flex-shrink-0">
                          <select value={t.status} onChange={(e) => setTicket(t.id, { status: e.target.value })}
                            className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white">
                            {["open", "pending", "closed"].map((s) => <option key={s} value={s}>{s}</option>)}
                          </select>
                          <button onClick={() => { const r = window.prompt("Response to user", t.response ?? ""); if (r !== null) setTicket(t.id, { response: r }); }}
                            className="text-xs text-brand-600 hover:underline">Respond</button>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {/* ── Analytics ── */}
            {mod === "analytics" && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <Stat label="Users" value={d.totals?.users} />
                  <Stat label="Documents" value={d.totals?.documents} />
                  <Stat label="Active subs" value={d.totals?.active_subs} />
                  <Stat label="Open tickets" value={d.totals?.open_tickets} />
                </div>
                {[["Signups (30d)", d.signups], ["Documents (30d)", d.documents]].map(([title, series]: any) => (
                  <div key={title} className={`${card} p-5`}>
                    <h3 className="font-medium text-slate-700 mb-4">{title}</h3>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={series ?? []}>
                        <XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                        <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ))}
              </div>
            )}

            {/* ── Settings ── */}
            {mod === "settings" && (
              <div className={`${card} p-6 max-w-xl space-y-4`}>
                <p className="text-sm text-slate-500">Platform-wide toggles. Changes apply immediately.</p>
                {[
                  { key: "signups_enabled", label: "Allow new sign-ups" },
                  { key: "maintenance_mode", label: "Maintenance mode" },
                  { key: "uploads_enabled", label: "Allow document uploads" },
                ].map(({ key, label }) => {
                  const on = (d.settings?.[key]?.enabled) ?? (key === "maintenance_mode" ? false : true);
                  return (
                    <div key={key} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                      <span className="text-sm text-slate-700">{label}</span>
                      <button onClick={() => saveSetting(key, { enabled: !on })}
                        className={cn("w-11 h-6 rounded-full transition-colors relative", on ? "bg-brand-600" : "bg-slate-300")}>
                        <span className={cn("absolute top-0.5 w-5 h-5 bg-white rounded-full transition-all", on ? "left-5" : "left-0.5")} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── Audit logs ── */}
            {mod === "audit" && (
              <Table head={["Time", "Action", "Resource", "User", "IP"]}>
                {(d.items ?? []).length === 0 ? <EmptyRow cols={5} text="No audit entries" /> :
                  d.items.map((a: any) => (
                    <tr key={a.id} className="border-t border-slate-50 hover:bg-slate-50/50">
                      <td className={`${td} whitespace-nowrap`}>{formatRelative(a.created_at)}</td>
                      <td className={td}><span className="text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full">{a.action}</span></td>
                      <td className={td}>{a.resource ?? "—"}</td>
                      <td className={`${td} font-mono text-xs`}>{a.user_id ? a.user_id.slice(0, 8) : "—"}</td>
                      <td className={td}>{a.ip_address ?? "—"}</td>
                    </tr>
                  ))}
              </Table>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: any; sub?: string }) {
  return (
    <div className={`${card} p-5`}>
      <p className="text-sm text-slate-500">{label}</p>
      <p className="text-2xl font-semibold text-slate-900 mt-1">{value ?? "—"}</p>
      {sub && <p className="text-xs text-green-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className={`${card} overflow-hidden`}>
      <table className="w-full text-sm">
        <thead className="bg-slate-50/70"><tr>{head.map((h, i) => <th key={i} className={th}>{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Badge({ text }: { text: string }) {
  const c: Record<string, string> = {
    admin: "bg-red-100 text-red-700", active: "bg-green-100 text-green-700", paid: "bg-green-100 text-green-700",
    open: "bg-amber-100 text-amber-700", high: "bg-red-100 text-red-700", closed: "bg-slate-100 text-slate-600",
    ready: "bg-green-100 text-green-700",
  };
  return <span className={cn("text-xs px-2 py-0.5 rounded-full capitalize", c[text] ?? "bg-slate-100 text-slate-600")}>{text ?? "—"}</span>;
}

function Empty({ text }: { text: string }) {
  return <p className="text-center text-sm text-slate-500 py-6">{text}</p>;
}
function EmptyRow({ cols, text }: { cols: number; text: string }) {
  return <tr><td colSpan={cols} className="px-4 py-8 text-center text-slate-500 text-sm">{text}</td></tr>;
}
