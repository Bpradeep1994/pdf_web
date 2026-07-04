import type { MetadataRoute } from "next";

const BASE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://app.example.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: "*", allow: "/", disallow: ["/dashboard", "/editor", "/settings", "/billing", "/admin", "/ai"] },
    ],
    sitemap: `${BASE}/sitemap.xml`,
  };
}
