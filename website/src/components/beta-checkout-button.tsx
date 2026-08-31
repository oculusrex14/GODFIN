"use client";

import { useRef, useState } from "react";

import { waitForCashfree } from "@/components/purchase-button";

export function BetaCheckoutButton({ enabled }: { enabled: boolean }) {
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const attemptId = useRef<string | null>(null);

  async function openCheckout() {
    setPending(true);
    setError("");
    try {
      attemptId.current ||= crypto.randomUUID();
      const response = await fetch("/api/beta/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checkoutAttemptId: attemptId.current }),
      });
      const body = await response.json();
      if (!response.ok || !body.paymentSessionId || !["sandbox", "production"].includes(body.mode)) {
        throw new Error(body.message || "The private checkout test is unavailable.");
      }
      if (body.amountMinor !== 100 || body.currency !== "inr" || body.createsPurchase !== false) {
        throw new Error("The private checkout contract did not match the expected INR 1 test.");
      }
      const Cashfree = await waitForCashfree();
      await Cashfree({ mode: body.mode }).checkout({
        paymentSessionId: body.paymentSessionId,
        redirectTarget: "_self",
      });
    } catch (checkoutError) {
      setError(
        checkoutError instanceof Error
          ? checkoutError.message
          : "The private checkout test could not be opened.",
      );
      setPending(false);
    }
  }

  return (
    <div className="beta-checkout-action">
      <label className="beta-checkout-confirmation">
        <input
          checked={confirmed}
          disabled={!enabled || pending}
          onChange={(event) => setConfirmed(event.target.checked)}
          type="checkbox"
        />
        <span>
          I understand this is a one-time INR 1 checkout-flow test. It does not
          buy GODFIN, change my beta plan, or create a permanent license.
        </span>
      </label>
      <button
        className="button"
        disabled={!enabled || !confirmed || pending}
        onClick={openCheckout}
        type="button"
      >
        {pending ? "Opening Cashfree…" : enabled ? "Run private INR 1 test" : "Owner gate is off"}
      </button>
      {error ? <p className="form-error-small" role="alert">{error}</p> : null}
    </div>
  );
}
