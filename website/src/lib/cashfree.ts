import {
  createHmac,
  timingSafeEqual,
} from "node:crypto";

import { serverEnv, siteUrl } from "@/lib/env";

export const CASHFREE_API_VERSION = "2026-01-01";
const CASHFREE_WEBHOOK_VERSIONS = new Set([
  CASHFREE_API_VERSION,
  "2025-01-01",
  "2023-08-01",
]);
const WEBHOOK_CLOCK_SKEW_MS = 5 * 60 * 1000;

export type CashfreeMode = "sandbox" | "production";

export type CashfreeOrder = {
  cf_order_id: string;
  order_id: string;
  order_amount: number;
  order_currency: string;
  order_status: string;
  payment_session_id?: string;
  customer_details?: {
    customer_id?: string | null;
    customer_email?: string | null;
    customer_phone?: string | null;
  } | null;
  order_tags?: Record<string, string> | null;
};

export type CashfreePayment = {
  cf_payment_id: string | number;
  payment_status: string;
  payment_amount: number;
  payment_currency: string;
  payment_time?: string | null;
};

type CashfreeErrorPayload = {
  message?: string;
  code?: string;
  type?: string;
};

export class CashfreeApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, payload: CashfreeErrorPayload) {
    super(payload.message || "Cashfree rejected the request.");
    this.name = "CashfreeApiError";
    this.status = status;
    this.code = payload.code || null;
  }
}

export function cashfreeMode(): CashfreeMode {
  return process.env.CASHFREE_ENVIRONMENT?.trim().toLowerCase() === "production"
    ? "production"
    : "sandbox";
}

function cashfreeBaseUrl(): string {
  return cashfreeMode() === "production"
    ? "https://api.cashfree.com/pg"
    : "https://sandbox.cashfree.com/pg";
}

function minorToMajor(amountMinor: number): number {
  if (!Number.isSafeInteger(amountMinor) || amountMinor < 100) {
    throw new Error("Cashfree order amount is invalid.");
  }
  return Number((amountMinor / 100).toFixed(2));
}

export function cashfreeAmountToMinor(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  const minor = Math.round(value * 100);
  return Number.isSafeInteger(minor) ? minor : null;
}

async function cashfreeRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${cashfreeBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "x-api-version": CASHFREE_API_VERSION,
      "x-client-id": serverEnv.cashfreeClientId(),
      "x-client-secret": serverEnv.cashfreeClientSecret(),
      ...(init.headers || {}),
    },
    signal: AbortSignal.timeout(10_000),
  });
  const payload = (await response.json().catch(() => ({}))) as
    | T
    | CashfreeErrorPayload;
  if (!response.ok) {
    throw new CashfreeApiError(response.status, payload as CashfreeErrorPayload);
  }
  return payload as T;
}

export async function createCashfreeOrder({
  orderId,
  amountMinor,
  currency,
  customerId,
  customerEmail,
  productName,
  tags,
}: {
  orderId: string;
  amountMinor: number;
  currency: string;
  customerId: string;
  customerEmail: string;
  productName: string;
  tags: Record<string, string>;
}): Promise<CashfreeOrder> {
  return cashfreeRequest<CashfreeOrder>("/orders", {
    method: "POST",
    headers: {
      "x-idempotency-key": orderId.slice("godfin_".length),
      "x-request-id": orderId,
    },
    body: JSON.stringify({
      order_id: orderId,
      order_amount: minorToMajor(amountMinor),
      order_currency: currency.toUpperCase(),
      customer_details: {
        customer_id: customerId,
        customer_email: customerEmail,
        // Cashfree requires this field even when a merchant does not collect a
        // phone number. Their API explicitly permits dummy customer details.
        customer_phone: "9999999999",
      },
      order_meta: {
        return_url: `${siteUrl()}/account?checkout=return&order_id=${encodeURIComponent(orderId)}`,
        notify_url: `${siteUrl()}/api/webhook`,
      },
      order_note: productName,
      order_tags: tags,
    }),
  });
}

export async function getCashfreeOrder(orderId: string): Promise<CashfreeOrder> {
  return cashfreeRequest<CashfreeOrder>(
    `/orders/${encodeURIComponent(orderId)}`,
  );
}

export async function getCashfreePayments(
  orderId: string,
): Promise<CashfreePayment[]> {
  return cashfreeRequest<CashfreePayment[]>(
    `/orders/${encodeURIComponent(orderId)}/payments`,
  );
}

export function verifyCashfreeWebhook({
  rawBody,
  signature,
  timestamp,
  version,
  now = Date.now(),
}: {
  rawBody: string;
  signature: string | null;
  timestamp: string | null;
  version: string | null;
  now?: number;
}): boolean {
  if (
    !signature ||
    !timestamp ||
    !/^\d{13}$/.test(timestamp) ||
    !version ||
    !CASHFREE_WEBHOOK_VERSIONS.has(version)
  ) {
    return false;
  }
  const sentAt = Number(timestamp);
  if (!Number.isSafeInteger(sentAt) || Math.abs(now - sentAt) > WEBHOOK_CLOCK_SKEW_MS) {
    return false;
  }
  const expected = createHmac("sha256", serverEnv.cashfreeClientSecret())
    .update(timestamp + rawBody, "utf8")
    .digest();
  let supplied: Buffer;
  try {
    supplied = Buffer.from(signature, "base64");
  } catch {
    return false;
  }
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}
