"use client";

import { useRef, useState } from "react";

import { trackAnalytics } from "@/components/privacy-analytics";
import type { ProductCode } from "@/lib/products";

declare global {
  interface Window {
    Cashfree?: (options: { mode: "sandbox" | "production" }) => {
      checkout: (options: {
        paymentSessionId: string;
        redirectTarget: "_self";
      }) => Promise<unknown>;
    };
  }
}

async function waitForCashfree(): Promise<NonNullable<Window["Cashfree"]>> {
  if (window.Cashfree) return window.Cashfree;
  await new Promise<void>((resolve, reject) => {
    const existing = document.getElementById("cashfree-checkout-sdk") as
      | HTMLScriptElement
      | null;
    const script = existing || document.createElement("script");
    const cleanup = () => {
      window.clearTimeout(timeout);
      script.removeEventListener("load", loaded);
      script.removeEventListener("error", failed);
    };
    const loaded = () => {
      cleanup();
      resolve();
    };
    const failed = () => {
      cleanup();
      script.remove();
      reject(new Error("Secure checkout could not load."));
    };
    const timeout = window.setTimeout(failed, 10_000);
    script.addEventListener("load", loaded, { once: true });
    script.addEventListener("error", failed, { once: true });
    if (!existing) {
      script.id = "cashfree-checkout-sdk";
      script.src = "https://sdk.cashfree.com/js/v3/cashfree.js";
      script.async = true;
      const nonceScript = document.querySelector<HTMLScriptElement>(
        "script[nonce]",
      );
      if (nonceScript?.nonce) script.nonce = nonceScript.nonce;
      document.head.appendChild(script);
    }
  });
  if (window.Cashfree) return window.Cashfree;
  throw new Error("Secure checkout could not load. Check your connection and try again.");
}

export function PurchaseButton({
  product,
  children,
  secondary = false,
  enabled = true,
}: {
  product: ProductCode;
  children: React.ReactNode;
  secondary?: boolean;
  enabled?: boolean;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const checkoutAttemptId = useRef<string | null>(null);

  async function checkout() {
    setPending(true);
    setError("");
    try {
      checkoutAttemptId.current ||= crypto.randomUUID();
      const response = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product,
          checkoutAttemptId: checkoutAttemptId.current,
        }),
      });
      const body = await response.json();
      if (response.status === 401) {
        window.location.assign("/account?next=/pricing");
        return;
      }
      if (
        !response.ok ||
        !body.paymentSessionId ||
        !["sandbox", "production"].includes(body.mode)
      ) {
        throw new Error(body.message || "Checkout is not available yet.");
      }
      trackAnalytics("begin_checkout", { product_code: product });
      const Cashfree = await waitForCashfree();
      const cashfree = Cashfree({ mode: body.mode });
      await cashfree.checkout({
        paymentSessionId: body.paymentSessionId,
        redirectTarget: "_self",
      });
    } catch (checkoutError) {
      setError(
        checkoutError instanceof Error
          ? checkoutError.message
          : "Checkout could not be started.",
      );
      setPending(false);
    }
  }

  return (
    <>
      <button
        className={secondary ? "button-secondary" : "button"}
        disabled={pending || !enabled}
        onClick={checkout}
        type="button"
      >
        {pending
          ? "Opening secure checkout…"
          : enabled
            ? children
            : "Checkout opens after payment verification"}
      </button>
      {error ? (
        <p className="form-error-small">{error}</p>
      ) : null}
    </>
  );
}
