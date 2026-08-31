import type { CashfreeOrder, CashfreePayment } from "@/lib/cashfree";

export const BETA_CHECKOUT_AMOUNT_MINOR = 100;
export const BETA_CHECKOUT_CURRENCY = "inr";
export const BETA_CHECKOUT_PRODUCT_CODE = "godfin_beta_checkout_test";
export const BETA_CHECKOUT_FLOW = "beta_checkout_validation";

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function text(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

export function isBetaCheckoutOrderId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^godfin_beta_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value,
    )
  );
}

export function betaOrderIdFromWebhook(event: unknown): string | null {
  const root = record(event);
  const data = record(root.data);
  const type = text(root.type) || "";
  let candidate: string | null = null;
  if (type.startsWith("PAYMENT_")) {
    candidate = text(record(data.order).order_id);
  } else if (type === "REFUND_STATUS_WEBHOOK") {
    candidate = text(record(data.refund).order_id);
  } else if (type === "AUTO_REFUND_STATUS_WEBHOOK") {
    candidate = text(record(data.auto_refund).order_id);
  } else if (type.startsWith("DISPUTE_")) {
    candidate = text(record(data.order_details).order_id);
  }
  return isBetaCheckoutOrderId(candidate) ? candidate : null;
}

export function betaPaymentIdFromWebhook(event: unknown): string | null {
  const root = record(event);
  const data = record(root.data);
  const payment = record(data.payment);
  return text(payment.cf_payment_id);
}

export function betaStatusFromWebhook(event: unknown):
  | "failed"
  | "abandoned"
  | "refund_pending"
  | "refunded"
  | "disputed"
  | "dispute_lost"
  | null {
  const root = record(event);
  const data = record(root.data);
  const type = text(root.type) || "";
  if (type === "PAYMENT_FAILED_WEBHOOK") return "failed";
  if (type === "PAYMENT_USER_DROPPED_WEBHOOK") return "abandoned";
  if (type === "REFUND_STATUS_WEBHOOK" || type === "AUTO_REFUND_STATUS_WEBHOOK") {
    const refund = record(
      type === "AUTO_REFUND_STATUS_WEBHOOK" ? data.auto_refund : data.refund,
    );
    return (text(refund.refund_status) || "").toUpperCase() === "SUCCESS"
      ? "refunded"
      : "refund_pending";
  }
  if (type === "DISPUTE_CLOSED") {
    const status = (text(record(data.dispute).dispute_status) || "").toUpperCase();
    return status.includes("LOST") ? "dispute_lost" : "disputed";
  }
  if (type === "DISPUTE_CREATED" || type === "DISPUTE_UPDATED") {
    return "disputed";
  }
  return null;
}

export function reviewBetaCheckout({
  order,
  payment,
  orderId,
  testerId,
  userId,
  accountEmail,
}: {
  order: CashfreeOrder;
  payment: CashfreePayment;
  orderId: string;
  testerId: string;
  userId: string;
  accountEmail: string;
}): { verified: boolean; reason: string | null } {
  const failures: string[] = [];
  if (order.order_id !== orderId) failures.push("order_id_mismatch");
  if (order.order_status.toUpperCase() !== "PAID") failures.push("order_not_paid");
  if (payment.payment_status.toUpperCase() !== "SUCCESS") {
    failures.push("payment_not_successful");
  }
  if (Math.round(order.order_amount * 100) !== BETA_CHECKOUT_AMOUNT_MINOR) {
    failures.push("order_amount_mismatch");
  }
  if (Math.round(payment.payment_amount * 100) !== BETA_CHECKOUT_AMOUNT_MINOR) {
    failures.push("payment_amount_mismatch");
  }
  if (order.order_currency.toLowerCase() !== BETA_CHECKOUT_CURRENCY) {
    failures.push("order_currency_mismatch");
  }
  if (payment.payment_currency.toLowerCase() !== BETA_CHECKOUT_CURRENCY) {
    failures.push("payment_currency_mismatch");
  }
  if (order.order_tags?.product_code !== BETA_CHECKOUT_PRODUCT_CODE) {
    failures.push("product_code_mismatch");
  }
  if (order.order_tags?.flow !== BETA_CHECKOUT_FLOW) failures.push("flow_mismatch");
  if (order.order_tags?.beta_tester_id !== testerId) {
    failures.push("tester_mismatch");
  }
  if (order.order_tags?.user_id !== userId) failures.push("user_mismatch");
  if (
    order.customer_details?.customer_email?.trim().toLowerCase() !==
    accountEmail.trim().toLowerCase()
  ) {
    failures.push("account_email_mismatch");
  }
  return {
    verified: failures.length === 0,
    reason: failures.length ? failures.join(",") : null,
  };
}
