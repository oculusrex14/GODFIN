"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function CopyLicenseKey({ licenseKey }: { licenseKey: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(licenseKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2500);
  }

  return (
    <div className="account-card account-card-spaced">
      <span className="status-pill">Payment complete</span>
      <h2>Your lifetime license key</h2>
      <p className="lead">
        Paste this into GODFIN → Settings → License. A copy has also been sent
        to your account email.
      </p>
      <div className="license-key license-key-spaced">
        {licenseKey}
      </div>
      <button className="button" onClick={copy} type="button">
        {copied ? <Check size={16} /> : <Copy size={16} />}
        {copied ? "Copied" : "Copy license key"}
      </button>
    </div>
  );
}
