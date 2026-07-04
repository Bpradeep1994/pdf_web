import Link from "next/link";
import type { Metadata } from "next";
import { FileText, Check } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Pricing — PDF Editor",
  description: "Simple, transparent pricing. Start free; upgrade for more documents, AI, OCR, conversions, and e-signatures.",
  alternates: { canonical: "https://app.example.com/pricing" },
};

const PLANS = [
  { name: "Free", price: "$0", note: "forever",
    features: ["5 PDFs / month", "10 MB max file size", "Basic editing", "5 AI queries / month"] },
  { name: "Pro", price: "$1", note: "/ month", popular: true,
    features: ["100 PDFs / month", "100 MB files", "Advanced editing + OCR", "500 AI queries", "All conversions", "E-signatures"] },
  { name: "Business", price: "$5", note: "/ month",
    features: ["Unlimited PDFs", "500 MB files", "Team collaboration", "Unlimited AI", "API access", "Priority support"] },
  { name: "Enterprise", price: "Custom", note: "contact us",
    features: ["SSO / SAML", "On-premise option", "SLA guarantee", "Custom AI models", "Audit logs", "Dedicated CSM"] },
];

export default function Pricing() {
  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
        <Link href="/" className="flex items-center gap-2">
          <FileText className="w-7 h-7 text-brand-600" />
          <span className="font-bold text-lg">PDF Editor</span>
        </Link>
        <nav className="flex items-center gap-3 text-sm">
          <ThemeToggle />
          <Link href="/login" className="px-3 py-1.5 text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white">Sign in</Link>
          <Link href="/register" className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2 font-medium">Get started</Link>
        </nav>
      </header>

      <section className="max-w-3xl mx-auto text-center px-6 pt-12 pb-10">
        <h1 className="text-4xl font-extrabold tracking-tight">Simple, transparent pricing</h1>
        <p className="mt-3 text-slate-600 dark:text-slate-500">Start free. Scale as you grow. Cancel anytime.</p>
      </section>

      <section className="max-w-6xl mx-auto px-6 pb-24 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {PLANS.map((p) => (
          <div key={p.name}
            className={`rounded-2xl border p-6 flex flex-col ${p.popular
              ? "border-brand-500 ring-2 ring-brand-500/40 shadow-lg"
              : "border-slate-200 dark:border-slate-800"}`}>
            {p.popular && <div className="text-xs font-bold text-brand-600 mb-2">MOST POPULAR</div>}
            <h2 className="font-bold text-lg">{p.name}</h2>
            <div className="mt-2 mb-5">
              <span className="text-3xl font-extrabold">{p.price}</span>
              <span className="text-slate-500 text-sm ml-1">{p.note}</span>
            </div>
            <ul className="space-y-2 flex-1 mb-6">
              {p.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
                  <Check className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />{f}
                </li>
              ))}
            </ul>
            <Link href="/register"
              className={`text-center rounded-lg px-4 py-2 font-medium transition-colors ${p.popular
                ? "bg-brand-600 hover:bg-brand-700 text-white"
                : "border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900"}`}>
              {p.name === "Enterprise" ? "Contact sales" : "Get started"}
            </Link>
          </div>
        ))}
      </section>
    </div>
  );
}
