import type { Metadata } from "next";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { PrivacyAnalytics } from "@/components/privacy-analytics";
import { siteUrl } from "@/lib/env";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  icons: {
    icon: "/godfin-mark.svg",
    shortcut: "/godfin-mark.svg",
    apple: "/godfin-mark.svg",
  },
  title: {
    default: "GODFIN — The Finance App That Respects Your Privacy",
    template: "%s · GODFIN",
  },
  description:
    "Local-first personal finance for Indian banks. Your statements and financial data stay on your laptop.",
  openGraph: {
    title: "GODFIN — The Finance App That Respects Your Privacy",
    description:
      "Parse Indian bank statements, classify spending, and build reports without uploading your bank history.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "GODFIN — Local-first personal finance",
    description: "Your bank data stays on your laptop.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-IN">
      <body>
        <SiteHeader />
        <main>{children}</main>
        <SiteFooter />
        <PrivacyAnalytics />
      </body>
    </html>
  );
}
