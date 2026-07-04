"use client";
import { useState, useEffect, useCallback } from "react";
import { Check, Loader2, Zap, Building2, Globe, RotateCcw } from "lucide-react";
import toast from "react-hot-toast";
import { billingApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { cn, formatRelative } from "@/lib/utils";

const PLANS = [
  {
    name: "Free",
    price: 0,
    interval: null,
    icon: null,
    color: "slate",
    features: [
      "5 PDFs / month",
      "10 MB max file size",
      "Basic editing",
      "5 AI queries / month",
      "Email support",
    ],
    priceId: null,
  },
  {
    name: "Pro",
    price: 1,
    interval: "month",
    icon: Zap,
    color: "brand",
    popular: true,
    features: [
      "100 PDFs / month",
      "100 MB max file size",
      "Advanced editing + OCR",
      "500 AI queries / month",
      "All conversions",
      "Priority support",
    ],
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRO_PRICE_ID ?? "",
  },
  {
    name: "Business",
    price: 5,
    interval: "month",
    icon: Building2,
    color: "violet",
    features: [
      "Unlimited PDFs",
      "500 MB max file size",
      "Team collaboration",
      "Unlimited AI queries",
      "E-signatures",
      "API access",
      "Dedicated support",
    ],
    priceId: process.env.NEXT_PUBLIC_STRIPE_BUSINESS_PRICE_ID ?? "",
  },
  {
    name: "Enterprise",
    price: null,
    interval: null,
    icon: Globe,
    color: "slate",
    features: [
      "Custom limits",
      "SSO / SAML",
      "On-premise option",
      "SLA guarantee",
      "Custom AI models",
      "Audit logs",
      "Dedicated CSM",
    ],
    priceId: null,
  },
];

interface Sub { plan: string; status: string; interval: string | null; cancel_at_period_end?: boolean; current_period_end?: string | null; }
interface Payment { id: string; amount: number; currency: string; status: string; provider?: string; method?: string; card_brand?: string; description?: string; created_at: string; }

export default function BillingPage() {
  const { user, fetchMe } = useAuthStore();
  const [annual, setAnnual]     = useState(false);
  const [loading, setLoading]   = useState<string | null>(null);
  const [sub, setSub]           = useState<Sub | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);

  const reload = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([billingApi.subscription(), billingApi.payments().catch(() => ({ data: [] }))]);
      setSub(s.data); setPayments(p.data);
    } catch {}
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const manage = async (fn: () => Promise<unknown>, msg: string) => {
    try { await fn(); toast.success(msg); await fetchMe(); reload(); }
    catch { toast.error("Action failed"); }
  };
  const doCancel = () => manage(() => billingApi.cancel(), "Subscription will cancel at period end");
  const doResume = () => manage(() => billingApi.resume(), "Subscription resumed");
  const doChange = (plan: string) => manage(() => billingApi.changePlan(plan), `Switched to ${plan}`);
  const doRefund = (id: string) => manage(() => billingApi.refund(id), "Refund processed");

  const checkout = async (planName: string, interval = "monthly") => {
    const plan = planName.toLowerCase();
    if (plan === "free")       { toast("You're on the Free plan."); return; }
    if (plan === "enterprise") { toast("Contact sales for Enterprise pricing."); return; }
    setLoading(planName);
    try {
      const { data } = await billingApi.checkout(plan, interval);
      window.location.href = data.checkout_url;
    } catch (e: any) {
      if (e?.response?.status === 503) toast("Billing isn't configured yet — add Stripe keys to enable it.");
      else toast.error("Failed to start checkout");
    } finally {
      setLoading(null);
    }
  };

  const colorMap: Record<string, string> = {
    brand:  "border-brand-500 ring-brand-500",
    violet: "border-violet-500 ring-violet-500",
    slate:  "border-slate-200",
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="text-center mb-10">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Simple, transparent pricing</h1>
        <p className="text-slate-500">Scale as you grow. Cancel anytime.</p>

        <div className="flex items-center justify-center gap-3 mt-6">
          <span className={cn("text-sm", !annual && "font-semibold text-slate-900")}>Monthly</span>
          <button
            onClick={() => setAnnual(!annual)}
            className={cn(
              "relative w-12 h-6 rounded-full transition-colors",
              annual ? "bg-brand-600" : "bg-slate-300"
            )}
          >
            <span className={cn(
              "absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform",
              annual ? "left-7" : "left-1"
            )} />
          </button>
          <span className={cn("text-sm", annual && "font-semibold text-slate-900")}>
            Annual <span className="text-green-600 font-medium">–20%</span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {PLANS.map((plan) => {
          const isCurrent = user?.role === plan.name.toLowerCase();
          const Icon = plan.icon;
          const discountedPrice = plan.price && annual ? Math.round(plan.price * 0.8) : plan.price;

          return (
            <div key={plan.name}
              className={cn(
                "card p-6 flex flex-col relative",
                plan.popular && "ring-2 ring-brand-500 shadow-lg shadow-brand-100",
                colorMap[plan.color]
              )}>
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                  Most popular
                </div>
              )}

              <div className="flex items-center gap-2 mb-4">
                {Icon && <Icon className="w-5 h-5 text-brand-600" />}
                <h2 className="font-bold text-slate-900 text-lg">{plan.name}</h2>
              </div>

              <div className="mb-6">
                {plan.price === null ? (
                  <p className="text-3xl font-bold text-slate-900">Custom</p>
                ) : plan.price === 0 ? (
                  <p className="text-3xl font-bold text-slate-900">Free</p>
                ) : (
                  <div className="flex items-end gap-1">
                    <p className="text-3xl font-bold text-slate-900">${discountedPrice}</p>
                    <p className="text-slate-500 text-sm mb-1">/ month</p>
                  </div>
                )}
                {annual && plan.price && plan.price > 0 && (
                  <p className="text-xs text-green-600 mt-1">Billed ${discountedPrice! * 12}/year</p>
                )}
              </div>

              <ul className="space-y-2 flex-1 mb-6">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
                    <Check className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => checkout(plan.name, annual ? "yearly" : "monthly")}
                disabled={isCurrent || loading === plan.name}
                className={cn(
                  "w-full py-2 rounded-lg text-sm font-medium transition-colors",
                  isCurrent
                    ? "bg-slate-100 text-slate-500 cursor-default"
                    : plan.popular
                    ? "btn-primary justify-center"
                    : "btn-secondary justify-center"
                )}
              >
                {loading === plan.name ? (
                  <Loader2 className="w-4 h-4 animate-spin mx-auto" />
                ) : isCurrent ? (
                  "Current plan"
                ) : plan.price === null ? (
                  "Contact sales"
                ) : (
                  "Get started"
                )}
              </button>

              {plan.price && plan.price > 0 && !isCurrent && (
                <button onClick={() => checkout(plan.name, "lifetime")}
                  className="mt-2 w-full text-xs text-slate-500 hover:text-brand-600">
                  or pay once — Lifetime ${plan.price * 30}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-center text-sm text-slate-500 mt-8">
        All plans include a 14-day free trial. No credit card required for Free plan.
      </p>

      {/* Manage subscription */}
      {sub && sub.plan !== "free" && (
        <div className="card p-6 mt-10">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-900">Your subscription</h3>
              <p className="text-sm text-slate-500 mt-0.5 capitalize">
                {sub.plan} · {sub.interval ?? "lifetime"} · {sub.status}
                {sub.cancel_at_period_end && <span className="text-amber-600"> · cancels at period end</span>}
                {sub.current_period_end && <span className="text-slate-500"> · renews {formatRelative(sub.current_period_end)}</span>}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {sub.plan !== "business" && <button onClick={() => doChange("business")} className="btn-secondary text-sm">Upgrade to Business</button>}
              {sub.plan !== "pro" && <button onClick={() => doChange("pro")} className="btn-secondary text-sm">Switch to Pro</button>}
              {sub.cancel_at_period_end
                ? <button onClick={doResume} className="btn-secondary text-sm gap-1"><RotateCcw className="w-3.5 h-3.5" /> Resume</button>
                : <button onClick={doCancel} className="text-sm px-3 py-1.5 rounded-lg text-red-600 hover:bg-red-50">Cancel</button>}
            </div>
          </div>
        </div>
      )}

      {/* Payment history */}
      {payments.length > 0 && (
        <div className="card mt-6 overflow-hidden">
          <h3 className="font-semibold text-slate-900 px-5 py-3 border-b border-slate-100">Payment history</h3>
          <table className="w-full text-sm">
            <thead className="bg-slate-50/70">
              <tr>{["Date", "Description", "Method", "Amount", "Status", ""].map((h) => (
                <th key={h} className="text-left px-5 py-2.5 font-medium text-slate-500 text-xs uppercase tracking-wide">{h}</th>))}</tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} className="border-t border-slate-50">
                  <td className="px-5 py-3 text-slate-500">{formatRelative(p.created_at)}</td>
                  <td className="px-5 py-3 text-slate-700">{p.description ?? "—"}</td>
                  <td className="px-5 py-3 text-slate-500 capitalize">{[p.provider, p.card_brand ?? p.method].filter(Boolean).join(" · ")}</td>
                  <td className="px-5 py-3 text-slate-700">{p.currency?.toUpperCase()} {p.amount}</td>
                  <td className="px-5 py-3">
                    <span className={cn("text-xs px-2 py-0.5 rounded-full capitalize",
                      p.status === "refunded" ? "bg-slate-100 text-slate-600" : "bg-green-100 text-green-700")}>{p.status}</span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {p.status === "succeeded" && (
                      <button onClick={() => doRefund(p.id)} className="text-xs text-red-600 hover:underline">Refund</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
