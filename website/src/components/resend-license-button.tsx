"use client";

import { Mail } from "lucide-react";
import { useState } from "react";

export function ResendLicenseButton({ licenseId }: { licenseId: string }) {
  const [state, setState] = useState<"idle" | "pending" | "sent" | "error">(
    "idle",
  );

  async function resend() {
    setState("pending");
    const response = await fetch("/api/license/resend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ license_id: licenseId }),
    });
    setState(response.ok ? "sent" : "error");
  }

  return (
    <button className="button-secondary" disabled={state === "pending"} onClick={resend}>
      <Mail size={15} />
      {state === "pending"
        ? "Sending…"
        : state === "sent"
          ? "Email sent"
          : state === "error"
            ? "Try again"
            : "Email key again"}
    </button>
  );
}
