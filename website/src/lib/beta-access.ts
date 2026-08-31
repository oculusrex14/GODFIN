import { betaCheckoutEligibility, type BetaPhase, type BetaStatus } from "@/lib/beta";
import { createAdminClient } from "@/lib/supabase/admin";

export type BetaPortalState = {
  id: string;
  cohort: string;
  status: BetaStatus;
  phase: BetaPhase;
  gmailTestRequired: boolean;
  gmailTestAddedAt: string | null;
  checkoutEligible: boolean;
  checkoutCompletedAt: string | null;
  acceptedAt: string | null;
  pausedAt: string | null;
  completedAt: string | null;
  license: {
    id: string;
    tier: "pro" | "max";
    status: string;
    expiresAt: string | null;
    keyLast4: string;
  } | null;
};

export async function betaPortalState(userId: string): Promise<BetaPortalState | null> {
  const admin = createAdminClient();
  const { data: tester, error } = await admin
    .from("beta_testers")
    .select(
      "id,cohort,status,phase,gmail_test_user_required,gmail_test_user_added_at,checkout_test_eligible,checkout_test_completed_at,accepted_at,paused_at,completed_at",
    )
    .eq("user_id", userId)
    .maybeSingle();
  if (error) throw error;
  if (!tester) return null;
  const { data: license, error: licenseError } = await admin
    .from("licenses")
    .select("id,tier,status,expires_at,key_last4")
    .eq("beta_tester_id", tester.id)
    .maybeSingle();
  if (licenseError) throw licenseError;
  return {
    id: tester.id,
    cohort: tester.cohort,
    status: tester.status as BetaStatus,
    phase: tester.phase as BetaPhase,
    gmailTestRequired: tester.gmail_test_user_required,
    gmailTestAddedAt: tester.gmail_test_user_added_at,
    checkoutEligible: betaCheckoutEligibility({
      status: tester.status,
      phase: tester.phase,
      eligible: tester.checkout_test_eligible,
    }),
    checkoutCompletedAt: tester.checkout_test_completed_at,
    acceptedAt: tester.accepted_at,
    pausedAt: tester.paused_at,
    completedAt: tester.completed_at,
    license: license
      ? {
          id: license.id,
          tier: license.tier as "pro" | "max",
          status: license.status,
          expiresAt: license.expires_at,
          keyLast4: license.key_last4,
        }
      : null,
  };
}
