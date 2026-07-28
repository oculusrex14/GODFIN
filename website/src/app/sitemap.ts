import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    "",
    "/download",
    "/pricing",
    "/docs",
    "/blog",
    "/changelog",
    "/privacy",
    "/terms",
    "/account",
  ].map((path) => ({
    url: `${siteUrl()}${path}`,
    lastModified: new Date(),
  }));
}
