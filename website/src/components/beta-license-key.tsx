"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export function BetaLicenseKey({
  licenseKey,
  expiresAt,
}: {
  licenseKey: string;
  expiresAt: string | null;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(licenseKey);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2500);
  }

  return (
    <div className="beta-license-key">
      <p className="account-caption">
        Revocable beta key{expiresAt ? ` · expires ${new Date(expiresAt).toLocaleDateString("en-IN")}` : ""}
      </p>
      <div className="license-key license-key-spaced">{licenseKey}</div>
      <button className="button-secondary" onClick={copy} type="button">
        {copied ? <Check size={16} /> : <Copy size={16} />}
        {copied ? "Copied" : "Copy beta key"}
      </button>
    </div>
  );
}
