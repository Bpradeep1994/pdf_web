"use client";
import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Lock, Loader2, ArrowLeft, CreditCard, Smartphone, Building2, Wallet, CheckCircle2, ShieldCheck } from "lucide-react";
import { billingApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import toast from "react-hot-toast";

const BASE: Record<string, number> = { pro: 1, business: 5 };
const amountFor = (plan: string, interval: string) => {
  const b = BASE[plan] ?? 1;
  return interval === "yearly" ? b * 10 : interval === "lifetime" ? b * 30 : b;
};

const PROVIDERS = [
  { id: "stripe", label: "Card (Stripe)" }, { id: "paypal", label: "PayPal" },
  { id: "razorpay", label: "Razorpay" }, { id: "applepay", label: "Apple Pay" }, { id: "upi", label: "UPI" },
];
const METHODS: Record<string, { id: string; label: string; icon: any }[]> = {
  stripe:    [{ id: "card", label: "Card", icon: CreditCard }],
  razorpay:  [{ id: "card", label: "Card", icon: CreditCard }, { id: "upi", label: "UPI", icon: Smartphone }, { id: "netbanking", label: "Net Banking", icon: Building2 }, { id: "wallet", label: "Wallet", icon: Wallet }],
  paypal:    [{ id: "paypal", label: "PayPal", icon: Wallet }],
  applepay:  [{ id: "wallet", label: "Apple Pay", icon: Wallet }],
  upi:       [{ id: "upi", label: "UPI", icon: Smartphone }],
};
const CARDS = ["Visa", "Mastercard", "Amex", "Discover", "JCB", "Diners"];
const BANKS = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank", "Kotak Mahindra", "Punjab National Bank"];

// Detect card brand from the typed number (IIN/BIN ranges).
function detectBrand(num: string): string | null {
  const n = num.replace(/\D/g, "");
  if (!n) return null;
  if (/^4/.test(n)) return "Visa";
  if (/^(5[1-5]|2(2[2-9]|[3-6][0-9]|7[01]|720))/.test(n)) return "Mastercard";
  if (/^3[47]/.test(n)) return "Amex";
  if (/^(6011|65|64[4-9]|622)/.test(n)) return "Discover";
  if (/^35(2[89]|[3-8][0-9])/.test(n)) return "JCB";
  if (/^3(0[0-5]|[689])/.test(n)) return "Diners";
  return null;
}
const groups = (n: string) => n.replace(/\D/g, "").slice(0, 19).replace(/(.{4})/g, "$1 ").trim();

function CheckoutInner() {
  const params = useSearchParams();
  const router = useRouter();
  const plan = (params.get("plan") || "pro").toLowerCase();
  const interval = (params.get("interval") || "monthly").toLowerCase();
  const amount = amountFor(plan, interval);
  const suffix = interval === "lifetime" ? "" : interval === "yearly" ? " / year" : " / month";

  const [provider, setProvider] = useState("stripe");
  const [method, setMethod]     = useState("card");
  const [brand, setBrand]       = useState("Visa");
  const [card, setCard] = useState(""); const [exp, setExp] = useState(""); const [cvc, setCvc] = useState("");
  const [upiId, setUpiId] = useState("");
  const [bank, setBank]   = useState(BANKS[0]);
  const [phone, setPhone] = useState("");
  const [step, setStep]   = useState<"form" | "otp" | "done">("form");
  const [otp, setOtp]     = useState("");
  const [sentTo, setSentTo] = useState("");
  const [busy, setBusy]   = useState(false);

  const methods = METHODS[provider] ?? METHODS.stripe;
  const isCard = method === "card";
  const detected = isCard ? detectBrand(card) : null;
  const providerLabel = PROVIDERS.find((p) => p.id === provider)?.label ?? provider;
  const isWallet = method === "wallet" && provider === "applepay";
  const upiNote = "A collect request will be sent to this UPI ID — approve it in any UPI app (Google Pay, PhonePe, Paytm, BHIM…).";

  const pickProvider = (p: string) => { setProvider(p); setMethod((METHODS[p] ?? METHODS.stripe)[0].id); };
  const onCard = (v: string) => { setCard(groups(v)); const d = detectBrand(v); if (d) setBrand(d); };

  // Step 1 → server generates + sends the OTP (email + optional SMS)
  const startPayment = async () => {
    if (isCard) {
      if (card.replace(/\D/g, "").length < 12) { toast.error("Enter a valid card number"); return; }
      const m = /^(\d{2})\s*\/?\s*(\d{2})$/.exec(exp.trim());
      if (!m) { toast.error("Enter the expiry as MM/YY"); return; }
      const mm = +m[1], yy = 2000 + +m[2];
      if (mm < 1 || mm > 12) { toast.error("Invalid expiry month"); return; }
      if (new Date(yy, mm, 0, 23, 59, 59) < new Date()) { toast.error("Card expired — check the expiry date"); return; }
      if (cvc.replace(/\D/g, "").length < 3) { toast.error("Enter the CVC"); return; }
    }
    if (method === "upi" && !/^[\w.\-]{2,}@[a-zA-Z]{2,}$/.test(upiId.trim())) { toast.error("Enter a valid UPI ID (e.g. name@upi)"); return; }
    setBusy(true);
    try {
      const { data } = await billingApi.sendOtp(phone || undefined);
      setOtp(""); setStep("otp");
      const where = [data.email, data.phone].filter(Boolean).join(" & ");
      setSentTo(where);
      if (data.dev_otp) toast(`Demo code (no email/SMS configured): ${data.dev_otp}`, { duration: 9000, icon: "🔐" });
      else toast.success(`Code sent to ${where}`);
    } catch { toast.error("Could not send code"); }
    finally { setBusy(false); }
  };

  // Step 2 → server verifies OTP + activates
  const verify = async () => {
    setBusy(true);
    try {
      await billingApi.verifyOtp({ otp, plan, interval, provider, method, card_brand: isCard ? brand.toLowerCase() : undefined });
      setStep("done");
      setTimeout(() => router.push("/billing?status=success"), 2200);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Verification failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-full bg-slate-50/50 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Link href="/billing" className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 mb-5">
          <ArrowLeft className="w-4 h-4" /> Back to plans
        </Link>

        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <h1 className="text-xl font-semibold text-slate-900">Checkout</h1>
            <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded-full">Demo mode</span>
          </div>
          <p className="text-slate-500 text-sm mb-5">
            <span className="capitalize font-medium text-slate-700">{plan}</span> · <span className="capitalize">{interval}</span> · <span className="font-semibold">${amount}</span>{suffix}
          </p>

          {/* ── Step: payment form ── */}
          {step === "form" && (
            <>
              <label className="label">Payment provider</label>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {PROVIDERS.map((p) => (
                  <button key={p.id} onClick={() => pickProvider(p.id)}
                    className={cn("px-2.5 py-1.5 rounded-lg text-xs border transition-colors",
                      provider === p.id ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50")}>
                    {p.label}
                  </button>
                ))}
              </div>

              {methods.length > 1 && (
                <>
                  <label className="label">Method</label>
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {methods.map((m) => (
                      <button key={m.id} onClick={() => setMethod(m.id)}
                        className={cn("flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs border transition-colors",
                          method === m.id ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-200 text-slate-600 hover:bg-slate-50")}>
                        <m.icon className="w-3.5 h-3.5" /> {m.label}
                      </button>
                    ))}
                  </div>
                </>
              )}

              {isCard ? (
                <div className="space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    {CARDS.map((c) => (
                      <button key={c} onClick={() => setBrand(c)}
                        className={cn("px-2 py-1 rounded text-[11px] border font-medium transition-colors",
                          brand === c ? "border-slate-800 text-slate-800" : "border-slate-200 text-slate-500 hover:text-slate-600",
                          detected === c && "ring-2 ring-brand-300")}>
                        {c}
                      </button>
                    ))}
                  </div>
                  <div className="relative">
                    <CreditCard className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input value={card} onChange={(e) => onCard(e.target.value)} placeholder="4242 4242 4242 4242"
                      className="input pl-9 pr-20" inputMode="numeric" />
                    {detected && (
                      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-brand-600">{detected}</span>
                    )}
                  </div>
                  <div className="flex gap-3">
                    <input value={exp} onChange={(e) => setExp(e.target.value)} placeholder="MM / YY" className="input flex-1" />
                    <input value={cvc} onChange={(e) => setCvc(e.target.value)} placeholder="CVC" className="input flex-1" inputMode="numeric" />
                  </div>
                </div>
              ) : method === "upi" ? (
                <div className="space-y-1.5">
                  <label className="label">UPI ID</label>
                  <div className="relative">
                    <Smartphone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input value={upiId} onChange={(e) => setUpiId(e.target.value)} placeholder="yourname@upi"
                      className="input pl-9" autoComplete="off" />
                  </div>
                  <p className="text-xs text-slate-500">{upiNote}</p>
                </div>
              ) : method === "netbanking" ? (
                <div className="space-y-1.5">
                  <label className="label">Select your bank</label>
                  <div className="relative">
                    <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 pointer-events-none" />
                    <select value={bank} onChange={(e) => setBank(e.target.value)} className="input pl-9 appearance-none">
                      {BANKS.map((b) => <option key={b}>{b}</option>)}
                    </select>
                  </div>
                  <p className="text-xs text-slate-500">You will be redirected to {bank} to authorize the payment.</p>
                </div>
              ) : isWallet ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center shrink-0">
                    <Wallet className="w-5 h-5 text-slate-700" />
                  </div>
                  <div className="text-sm text-slate-600">
                    <p className="font-medium text-slate-800">{providerLabel}</p>
                    <p className="text-xs mt-0.5">No card details needed — your saved {providerLabel} payment method will be used after OTP verification.</p>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-white border border-slate-200 flex items-center justify-center shrink-0">
                    <Wallet className="w-5 h-5 text-slate-700" />
                  </div>
                  <div className="text-sm text-slate-600">
                    <p className="font-medium text-slate-800">{method === "paypal" ? "PayPal" : providerLabel}</p>
                    <p className="text-xs mt-0.5">You will complete payment via <span className="capitalize">{method === "paypal" ? "PayPal" : method}</span> after OTP verification.</p>
                  </div>
                </div>
              )}

              <div className="mt-4">
                <label className="label">Mobile number <span className="text-slate-500">(for OTP — optional)</span></label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210"
                  className="input" inputMode="tel" />
              </div>

              <button onClick={startPayment} disabled={busy} className="btn-primary w-full justify-center py-2.5 mt-6 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : isWallet ? `Pay $${amount}${suffix} with ${providerLabel}` : `Pay $${amount}${suffix}`}
              </button>
            </>
          )}

          {/* ── Step: OTP ── */}
          {step === "otp" && (
            <div className="text-center py-2">
              <div className="w-12 h-12 rounded-full bg-brand-50 flex items-center justify-center mx-auto mb-3">
                <ShieldCheck className="w-6 h-6 text-brand-600" />
              </div>
              <h2 className="font-semibold text-slate-900">Verify your payment</h2>
              <p className="text-sm text-slate-500 mt-1 mb-4">Enter the 6-digit code sent to {sentTo || "your email / mobile"}.</p>
              <input value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="••••••" inputMode="numeric" autoFocus
                className="w-44 mx-auto text-center text-2xl tracking-[0.5em] font-semibold border border-slate-300 rounded-xl py-2.5 outline-none focus:border-brand-500" />
              <button onClick={verify} disabled={busy || otp.length !== 6} className="btn-primary w-full justify-center py-2.5 mt-5 disabled:opacity-50">
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : `Verify & Pay $${amount}`}
              </button>
              <button onClick={() => setStep("form")} className="text-xs text-slate-500 hover:text-slate-700 mt-3">Back</button>
            </div>
          )}

          {/* ── Step: success ── */}
          {step === "done" && (
            <div className="text-center py-6">
              <div className="w-16 h-16 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="w-9 h-9 text-green-600" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900">Payment successful</h2>
              <p className="text-slate-500 mt-1">You are now on the <span className="capitalize font-medium text-slate-700">{plan}</span> plan.</p>
              <p className="text-xs text-slate-500 mt-3">Redirecting to billing…</p>
            </div>
          )}

          {step !== "done" && (
            <p className="flex items-center justify-center gap-1.5 text-xs text-slate-500 mt-4">
              <Lock className="w-3.5 h-3.5" /> Demo checkout — no real charge.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={<div className="flex h-full items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-brand-400" /></div>}>
      <CheckoutInner />
    </Suspense>
  );
}
