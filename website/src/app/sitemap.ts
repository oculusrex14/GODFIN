import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    "",
    "/how-it-works",
    "/pricing",
    "/roadmap",
    "/about",
    "/docs",
    "/blog",
    "/contact",
    "/changelog",
    "/privacy",
    "/terms",
  ].map((path) => ({
    url: `${siteUrl()}${path}`,
    lastModified: new Date(),
  }));
}
