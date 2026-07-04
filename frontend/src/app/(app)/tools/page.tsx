"use client";
import Link from "next/link";
import {
  PenLine, Combine, Scissors, Minimize2, ScanText, FileType2, PenTool,
  FileText, FileSpreadsheet, Presentation, Image as ImageIcon,
  Lock, Unlock, ScanLine, Languages,
} from "lucide-react";

const TOOLS = [
  { key: "edit",         title: "Edit & Annotate", desc: "Add text, highlight, redact, draw, images.", icon: PenLine },
  { key: "merge",        title: "Merge PDF",       desc: "Combine multiple PDFs into one.",            icon: Combine },
  { key: "split",        title: "Split PDF",       desc: "Break a PDF into pages or ranges.",          icon: Scissors },
  { key: "compress",     title: "Compress PDF",    desc: "Shrink file size, keep quality.",            icon: Minimize2 },
  { key: "ocr",          title: "OCR",             desc: "Make scans searchable & selectable.",        icon: ScanText },
  { key: "convert",      title: "Convert PDF",     desc: "PDF â†’ Word, Excel, PPT, images.",            icon: FileType2 },
  { key: "translate",    title: "Translate PDF",   desc: "English â‡„ Hindi, Telugu & more.",            icon: Languages },
  { key: "word-to-pdf",  title: "Word to PDF",     desc: "DOC/DOCX â†’ PDF.",                            icon: FileText },
  { key: "excel-to-pdf", title: "Excel to PDF",    desc: "XLS/XLSX â†’ PDF.",                            icon: FileSpreadsheet },
  { key: "ppt-to-pdf",   title: "PPT to PDF",      desc: "PPT/PPTX â†’ PDF.",                            icon: Presentation },
  { key: "image-to-pdf", title: "Image to PDF",    desc: "JPG/PNG â†’ PDF.",                             icon: ImageIcon },
  { key: "html-to-pdf",  title: "HTML to PDF",     desc: "HTML pages â†’ PDF.",                          icon: FileType2 },
  { key: "protect",      title: "Protect PDF",     desc: "Add a password and encrypt your PDF.",       icon: Lock },
  { key: "unlock",       title: "Unlock PDF",      desc: "Remove password & encryption.",              icon: Unlock },
  { key: "scan",         title: "PDF Scanner",     desc: "Combine photos / scans into a PDF.",         icon: ScanLine },
  { key: "sign",         title: "E-Signature",     desc: "Sign or request signatures.",                icon: PenTool },
];

export default function ToolsHub() {
  return (
    <div className="h-full overflow-y-auto bg-slate-50/50">
      <div className="max-w-5xl mx-auto px-6 sm:px-10 py-10">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Tools</h1>
        <p className="text-slate-500 text-sm mt-1.5 mb-8">Pick a tool, drop your file, get your result.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {TOOLS.map(({ key, title, desc, icon: Icon }) => (
            <Link key={key} href={`/tools/${key}`}
              className="group bg-white border-2 border-slate-200 rounded-2xl p-5 hover:shadow-lg hover:shadow-slate-200/60 hover:-translate-y-0.5 hover:border-brand-400 transition-all">
              <div className="w-11 h-11 rounded-xl bg-brand-50 flex items-center justify-center mb-3 group-hover:bg-brand-100 transition-colors">
                <Icon className="w-6 h-6 text-brand-600" />
              </div>
              <h3 className="font-semibold text-slate-900">{title}</h3>
              <p className="text-sm text-slate-500 mt-1">{desc}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
