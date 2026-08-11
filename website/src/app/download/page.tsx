import type { Metadata } from "next";

import { DownloadChooser } from "@/components/download-chooser";

export const metadata: Metadata = {
  title: "Download",
  description: "Check GODFIN desktop release availability for macOS, Windows, or Linux.",
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
            Signed installers are not publicly available during the private
            preview. Platform buttons activate only when a verified release is
            configured.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell">
          <DownloadChooser />
          <div className="callout">
            When a release link is enabled, verify its published signature and
            checksum before opening it. GODFIN never asks you to upload a
            statement to this website.
          </div>
        </div>
      </section>
    </>
  );
}
