import type { Metadata } from "next";

import { DownloadChooser } from "@/components/download-chooser";

export const metadata: Metadata = {
  title: "Download",
  description: "Download the local GODFIN desktop app for macOS, Windows, or Linux.",
};

export default function DownloadPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
            Local desktop app
          </div>
          <h1>Download GODFIN</h1>
          <p>
            Install it, set a local PIN, and start with Core—no website account
            or payment details required.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell">
          <DownloadChooser />
          <div className="callout">
            Verify release signatures before opening a downloaded build. GODFIN
            never asks you to upload a statement to this website.
          </div>
        </div>
      </section>
    </>
  );
}
