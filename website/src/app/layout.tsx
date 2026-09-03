import type { Metadata } from "next";
import { headers } from "next/headers";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { PrivacyAnalytics } from "@/components/privacy-analytics";
import { siteUrl } from "@/lib/env";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  icons: {
    icon: "/godfin-vault-dial.png",
    shortcut: "/godfin-vault-dial.png",
    apple: "/godfin-vault-dial.png",
  },
  title: {
    default: "GODFIN — Better money habits and decisions.",
    template: "%s · GODFIN",
  },
  description:
    "An AI-powered, local-first personal finance app for tracking expenses, understanding money habits, and making clearer decisions.",
  openGraph: {
    title: "GODFIN — Better money habits and decisions.",
    description:
      "Bring in supported Gmail alerts or bank statements, understand the month, and keep ordinary finance records on your own computer.",
    images: [
      {
        url: "/video/godfin-beta-hero.poster.webp",
        width: 1920,
        height: 1080,
        alt: "The real GODFIN desktop app using made-up sample data",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "GODFIN — Better money habits and decisions.",
    description: "AI-powered, local-first personal finance for clearer money habits and decisions.",
    images: ["/video/godfin-beta-hero.poster.webp"],
  },
};

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const nonce = (await headers()).get("x-nonce") || undefined;
  return (
    <html lang="en-IN">
      <body>
        <SiteHeader />
        <main>{children}</main>
        <SiteFooter />
        <PrivacyAnalytics nonce={nonce} />
      </body>
    </html>
  );
}
