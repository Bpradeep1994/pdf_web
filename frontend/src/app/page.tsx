import Link from "next/link";
import type { Metadata } from "next";
import {
  FileText, Sparkles, PenTool, Shuffle, Scissors, Minimize2, ScanLine, ShieldCheck,
  FileType2, FileSpreadsheet, Presentation, Image as ImageIcon, Lock, Unlock, Languages,
} from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "PDF Editor — Edit, Sign & Convert PDFs Online",
  description: "Edit, merge, split, compress, OCR, convert, and e-sign your PDFs. A fast, secure, all-in-one document workspace.",
  keywords: ["pdf editor", "esign", "pdf converter", "ocr", "merge pdf", "split pdf", "compress pdf"],
  openGraph: {
    title: "PDF Editor — All-in-One Document Platform",
    description: "Edit, sign, convert, and manage your PDFs online.",
    type: "website",
    url: "https://app.example.com",
  },
  alternates: { canonical: "https://app.example.com" },
};

const FEATURES = [
  { icon: PenTool,         title: "Edit & Annotate", body: "Add text, highlight, redact, draw, and images.", tool: "edit" },
  { icon: Shuffle,         title: "Merge PDF",       body: "Combine multiple PDFs into one document.", tool: "merge" },
  { icon: Scissors,        title: "Split PDF",       body: "Break a PDF into pages or custom ranges.", tool: "split" },
  { icon: Minimize2,       title: "Compress PDF",    body: "Shrink file size while keeping quality.", tool: "compress" },
  { icon: ScanLine,        title: "OCR",             body: "Make scanned documents searchable.", tool: "ocr" },
  { icon: FileType2,       title: "Convert PDF",     body: "PDF → Word, Excel, PowerPoint, images.", tool: "convert" },
  { icon: Languages,       title: "Translate PDF",   body: "English ⇄ Hindi, Telugu, Tamil & more.", tool: "translate" },
  { icon: FileText,        title: "Word to PDF",     body: "Convert DOC / DOCX files to PDF.", tool: "word-to-pdf" },
  { icon: FileSpreadsheet, title: "Excel to PDF",    body: "Convert XLS / XLSX files to PDF.", tool: "excel-to-pdf" },
  { icon: Presentation,    title: "PPT to PDF",      body: "Convert PPT / PPTX files to PDF.", tool: "ppt-to-pdf" },
  { icon: ImageIcon,       title: "Image to PDF",    body: "Convert JPG / PNG images to PDF.", tool: "image-to-pdf" },
  { icon: Lock,            title: "Protect PDF",     body: "Add a password and encrypt your PDF.", tool: "protect" },
  { icon: Unlock,          title: "Unlock PDF",      body: "Remove password, encryption & permissions.", tool: "unlock" },
  { icon: ScanLine,        title: "PDF Scanner",     body: "Combine photos / scans into a PDF.", tool: "scan" },
  { icon: ShieldCheck,     title: "E-Signatures",    body: "Sign documents and request signatures.", tool: "sign" },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {/* Nav */}
      <header className="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <FileText className="w-7 h-7 text-brand-600" />
          <span className="font-bold text-lg">PDF Editor</span>
        </div>
        <nav className="flex items-center gap-2 sm:gap-4 text-sm">
          <Link href="/pricing" className="hidden sm:inline text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white">Pricing</Link>
          <ThemeToggle />
          <Link href="/login" className="text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white px-3 py-1.5">Sign in</Link>
          <Link href="/register" className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2 font-medium transition-colors">Get started</Link>
        </nav>
      </header>

      {/* Hero */}
      <section className="max-w-4xl mx-auto text-center px-6 pt-16 pb-20">
        <div className="inline-flex items-center gap-2 text-xs font-medium text-brand-700 bg-brand-50 dark:bg-brand-900/30 dark:text-brand-300 rounded-full px-3 py-1 mb-6">
          <Sparkles className="w-3.5 h-3.5" /> All-in-one document workspace
        </div>
        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight">
          Every PDF tool you need, <span className="text-brand-600">in one place.</span>
        </h1>
        <p className="mt-6 text-lg text-slate-600 dark:text-slate-500 max-w-2xl mx-auto">
          Edit, merge, split, compress, OCR, convert, and e-sign your PDFs —
          fast, secure, and built for teams.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/register" className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-6 py-3 font-semibold transition-colors">Start free</Link>
          <Link href="/pricing" className="border border-slate-300 dark:border-slate-700 rounded-lg px-6 py-3 font-semibold hover:bg-slate-50 dark:hover:bg-slate-900 transition-colors">View pricing</Link>
        </div>
        <p className="mt-4 text-xs text-slate-500">No credit card required · Encrypted in transit &amp; at rest · Delete your data anytime</p>
      </section>

      {/* Tools launcher */}
      <section className="max-w-6xl mx-auto px-6 pb-24">
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold">Pick a tool to get started</h2>
          <p className="text-slate-500 dark:text-slate-500 mt-1">Choose a tool, drop your file, get your result.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {FEATURES.map(({ icon: Icon, title, body, tool }) => (
            <Link key={title} href={`/tools/${tool}`}
              className="group rounded-2xl border-2 border-slate-200 dark:border-slate-700 p-5 hover:shadow-md hover:-translate-y-0.5 hover:border-brand-400 transition-all">
              <div className="w-10 h-10 rounded-xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center mb-3 group-hover:bg-brand-100 transition-colors">
                <Icon className="w-5 h-5 text-brand-600 dark:text-brand-400" />
              </div>
              <h3 className="font-semibold group-hover:text-brand-700">{title}</h3>
              <p className="text-sm text-slate-500 dark:text-slate-500 mt-1">{body}</p>
            </Link>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="bg-brand-600">
        <div className="max-w-4xl mx-auto text-center px-6 py-16 text-white">
          <h2 className="text-3xl font-bold">Ready to work smarter with your PDFs?</h2>
          <p className="mt-3 text-blue-50">Join free and edit your first document in under a minute.</p>
          <Link href="/register" className="inline-block mt-6 bg-white text-brand-700 rounded-lg px-6 py-3 font-semibold hover:bg-brand-50 transition-colors">Create your free account</Link>
        </div>
      </section>

      <footer className="max-w-7xl mx-auto px-6 py-8 text-sm text-slate-500 flex flex-col sm:flex-row justify-between gap-2">
        <span>© {new Date().getFullYear()} PDF Editor. All rights reserved.</span>
        <div className="flex gap-4">
          <Link href="/pricing" className="hover:text-slate-600 dark:hover:text-slate-200">Pricing</Link>
          <Link href="/login" className="hover:text-slate-600 dark:hover:text-slate-200">Sign in</Link>
        </div>
      </footer>
    </div>
  );
}
