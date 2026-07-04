"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Cookies from "js-cookie";
import { Loader2 } from "lucide-react";

export default function OAuthCallback() {
  const router = useRouter();

  useEffect(() => {
    // Tokens arrive in the URL fragment (#access_token=...&refresh_token=...).
    const hash = typeof window !== "undefined" ? window.location.hash.slice(1) : "";
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");
    if (access && refresh) {
      Cookies.set("access_token", access, { expires: 1 / 48, secure: true, sameSite: "lax" });
      Cookies.set("refresh_token", refresh, { expires: 7, secure: true, sameSite: "lax" });
      router.replace("/dashboard");
    } else {
      router.replace("/login?error=oauth");
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
    </div>
  );
}
