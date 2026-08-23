import type { ProductCode } from "@/lib/products";

export type RequestedLicenseProduct = "pro" | "max";

export type ExistingPurchaseLicense = {
  id: string;
  tier: string;
  status: string;
};

export type CheckoutResolution =
  | {
      ok: true;
      productCode: ProductCode;
      purchaseKind: "base" | "upgrade";
      upgradeLicenseId: string | null;
    }
  | {
      ok: false;
      status: 409;
      message: string;
    };

export function resolveLicenseCheckout(
  requested: RequestedLicenseProduct,
  purchaseLicenses: ExistingPurchaseLicense[],
): CheckoutResolution {
  if (purchaseLicenses.length > 1) {
    return {
      ok: false,
      status: 409,
      message:
        "This account has more than one purchase license. Contact hello@godfin.dev before starting another checkout.",
    };
  }

  const current = purchaseLicenses[0] || null;
  if (!current) {
    return {
      ok: true,
      productCode: requested,
      purchaseKind: "base",
      upgradeLicenseId: null,
    };
  }
  if (current.status !== "active") {
    return {
      ok: false,
      status: 409,
      message:
        "Your existing purchase license needs review. Contact hello@godfin.dev before starting another checkout.",
    };
  }
  if (current.tier === "max") {
    return {
      ok: false,
      status: 409,
      message: "This account already owns GODFIN Max.",
    };
  }
  if (current.tier !== "pro") {
    return {
      ok: false,
      status: 409,
      message:
        "Your existing purchase license has an unknown plan. Contact hello@godfin.dev before checkout.",
    };
  }
  if (requested === "pro") {
    return {
      ok: false,
      status: 409,
      message: "This account already owns GODFIN Pro. Choose Max to upgrade.",
    };
  }
  return {
    ok: true,
    productCode: "pro_to_max",
    purchaseKind: "upgrade",
    upgradeLicenseId: current.id,
  };
}
