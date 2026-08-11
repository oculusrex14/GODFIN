"use client";

import { useState } from "react";

import { trackAnalytics } from "@/components/privacy-analytics";
import type { ProductCode } from "@/lib/products";

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

  async function checkout() {
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product }),
      });
      const body = await response.json();
      if (response.status === 401) {
        window.location.assign("/account?next=/pricing");
        return;
      }
      if (!response.ok || !body.url) {
        throw new Error(body.message || "Checkout is not available yet.");
      }
      trackAnalytics("begin_checkout", { product_code: product });
      window.location.assign(body.url);
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
