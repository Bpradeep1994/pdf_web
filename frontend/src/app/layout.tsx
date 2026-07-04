import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import { Toaster } from "react-hot-toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "PDF Editor — AI-Powered Document Platform",
  description: "Edit, sign, convert, and chat with your PDFs using AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
          <Toaster
            position="top-right"
            toastOptions={{
              style: { borderRadius: "10px", fontSize: "14px" },
              success: { iconTheme: { primary: "#22c55e", secondary: "#fff" } },
              error:   { iconTheme: { primary: "#ef4444", secondary: "#fff" } },
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
