import { createHash, randomBytes } from "node:crypto";

import { betaLicenseKeyForTester, normalizeEmail } from "../src/lib/beta";
import { sendBetaInviteEmail, sendBetaLicenseEmail } from "../src/lib/email";
import { serverEnv, siteUrl } from "../src/lib/env";
import { hashLicenseKey } from "../src/lib/license";
import { createAdminClient } from "../src/lib/supabase/admin";

type Options = Record<string, string | boolean>;

const command = process.argv[2] || "help";
const { options: args, positionals } = parseArguments(process.argv.slice(3));
let admin: ReturnType<typeof createAdminClient>;
const actor = (process.env.GODFIN_BETA_OPERATOR || "owner-cli").trim().slice(0, 160);

function parseArguments(values: string[]): { options: Options; positionals: string[] } {
  const result: Options = {};
  const positionals: string[] = [];
  for (let index = 0; index < values.length; index += 1) {
    const item = values[index];
    if (!item.startsWith("--")) {
      positionals.push(item);
      continue;
    }
    const name = item.slice(2);
    const next = values[index + 1];
    if (!next || next.startsWith("--")) result[name] = true;
    else {
      result[name] = next;
      index += 1;
    }
  }
  return { options: result, positionals };
}

function option(name: string, required = false): string | null {
  const value = args[name];
  if (typeof value === "string" && value.trim()) return value.trim();
  if (required) throw new Error(`Missing required --${name}.`);
  return null;
}

function emailOption(): string {
  const email = normalizeEmail(option("email") || positionals[0]);
  if (!email) throw new Error("Provide a valid email as the first value or with --email.");
  return email;
}

function maskedEmail(value: string): string {
  const [local, domain] = value.split("@");
  const visible = local.slice(0, 2);
  return `${visible}${"*".repeat(Math.max(2, Math.min(8, local.length - visible.length)))}@${domain}`;
}

function output(value: Record<string, unknown> | Array<Record<string, unknown>>) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

async function findTester(email: string) {
  const { data, error } = await admin
    .from("beta_testers")
    .select("id,email_normalized,cohort,status,phase,user_id,gmail_test_user_required,gmail_test_user_added_at,checkout_test_eligible,checkout_test_completed_at")
    .eq("email_normalized", email)
    .maybeSingle();
  if (error) throw error;
  if (!data) throw new Error("No beta tester matches that email.");
  return data;
}

async function audit(
  testerId: string | null,
  eventType: string,
  reason: string | null,
  metadata: Record<string, unknown> = {},
) {
  const { error } = await admin.from("beta_events").insert({
    beta_tester_id: testerId,
    event_type: eventType,
    actor,
    reason: reason?.slice(0, 1000) || null,
    metadata,
  });
  if (error) throw error;
}

async function list() {
  const status = option("status");
  if (status === "confirmed") {
    const { data: candidates, error: candidateError } = await admin
      .from("waitlist_entries")
      .select("id,email_normalized,os,intended_use,country,confirmed_at")
      .not("confirmed_at", "is", null)
      .order("confirmed_at", { ascending: false })
      .limit(500);
    if (candidateError) throw candidateError;
    const ids = (candidates || []).map((row) => row.id);
    const { data: profiles, error: profileError } = ids.length
      ? await admin
          .from("beta_candidate_profiles")
          .select("waitlist_entry_id,banks,primary_use,gmail_test_interest,feedback_commitment,platform_detail")
          .in("waitlist_entry_id", ids)
      : { data: [], error: null };
    if (profileError) throw profileError;
    const byEntry = new Map((profiles || []).map((row) => [row.waitlist_entry_id, row]));
    const os = option("os")?.toLowerCase();
    const bank = option("bank")?.toLowerCase();
    const use = option("use")?.toLowerCase();
    output((candidates || [])
      .filter((row) => !os || row.os === os)
      .filter((row) => {
        const profile = byEntry.get(row.id);
        return !bank || (profile?.banks || []).some((value: string) => value.toLowerCase().includes(bank));
      })
      .filter((row) => {
        const profile = byEntry.get(row.id);
        const haystack = `${row.intended_use} ${(profile?.primary_use || []).join(" ")}`.toLowerCase();
        return !use || haystack.includes(use);
      })
      .map((row) => {
        const profile = byEntry.get(row.id);
        return {
          email: maskedEmail(row.email_normalized),
          status: "confirmed",
          os: row.os,
          country: row.country || "unknown",
          banks: profile?.banks || [],
          uses: profile?.primary_use || [],
          gmail_interest: profile?.gmail_test_interest || false,
          feedback_commitment: profile?.feedback_commitment || false,
          platform_detail: profile?.platform_detail || null,
          confirmed_at: row.confirmed_at,
        };
      }));
    return;
  }
  let query = admin
    .from("beta_testers")
    .select("email_normalized,cohort,status,phase,gmail_test_user_required,gmail_test_user_added_at,checkout_test_eligible,checkout_test_completed_at,created_at")
    .order("created_at", { ascending: false })
    .limit(200);
  if (status) query = query.eq("status", status);
  const { data, error } = await query;
  if (error) throw error;
  output((data || []).map((row) => ({
    email: maskedEmail(row.email_normalized),
    cohort: row.cohort,
    status: row.status,
    phase: row.phase,
    gmail: row.gmail_test_user_required
      ? row.gmail_test_user_added_at ? "ready" : "owner_action"
      : "not_requested",
    checkout: row.checkout_test_completed_at
      ? "complete"
      : row.checkout_test_eligible ? "allowlisted" : "off",
    created_at: row.created_at,
  })));
}

async function shortlist() {
  const email = emailOption();
  const cohort = (option("cohort") || positionals[1] || "").toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{1,39}$/.test(cohort)) {
    throw new Error("--cohort must be 2-40 lowercase letters, numbers, underscores, or hyphens.");
  }
  const { data: waitlist, error: waitlistError } = await admin
    .from("waitlist_entries")
    .select("id,confirmed_at")
    .eq("email_normalized", email)
    .maybeSingle();
  if (waitlistError) throw waitlistError;
  if (!waitlist?.confirmed_at) throw new Error("Only a confirmed waitlist entry can be shortlisted.");
  const { data: existing, error: existingError } = await admin
    .from("beta_testers")
    .select("id,status,phase")
    .eq("email_normalized", email)
    .maybeSingle();
  if (existingError) throw existingError;
  if (existing) {
    output({ email: maskedEmail(email), status: existing.status, phase: existing.phase, changed: false });
    return;
  }
  const { data: tester, error } = await admin
    .from("beta_testers")
    .insert({
      waitlist_entry_id: waitlist.id,
      email_normalized: email,
      cohort,
      gmail_test_user_required: args.gmail === true,
    })
    .select("id,status,phase")
    .single();
  if (error) throw error;
  await audit(tester.id, "tester:shortlisted", option("reason"), { cohort });
  output({ email: maskedEmail(email), status: tester.status, phase: tester.phase, changed: true });
}

async function invite() {
  const email = emailOption();
  const tester = await findTester(email);
  if (!["shortlisted", "invited"].includes(tester.status)) {
    throw new Error("Only a shortlisted or previously invited tester can receive an invitation.");
  }
  const now = new Date().toISOString();
  const { error: revokeError } = await admin
    .from("beta_invites")
    .update({ revoked_at: now })
    .eq("beta_tester_id", tester.id)
    .is("used_at", null)
    .is("revoked_at", null);
  if (revokeError) throw revokeError;
  const token = randomBytes(32).toString("base64url");
  const tokenHash = createHash("sha256").update(token).digest("hex");
  const expiresAt = new Date(Date.now() + 48 * 60 * 60 * 1000).toISOString();
  const { data: inviteRow, error: inviteError } = await admin
    .from("beta_invites")
    .insert({ beta_tester_id: tester.id, token_hash: tokenHash, expires_at: expiresAt })
    .select("id")
    .single();
  if (inviteError) throw inviteError;
  const inviteUrl = `${siteUrl()}/beta/accept#token=${encodeURIComponent(token)}`;
  try {
    await sendBetaInviteEmail({
      to: email,
      inviteUrl,
      cohort: tester.cohort,
      idempotencyKey: `beta-invite:${inviteRow.id}`,
    });
  } catch (error) {
    await admin.from("beta_invites").update({ revoked_at: new Date().toISOString() }).eq("id", inviteRow.id);
    throw error;
  }
  await Promise.all([
    admin.from("beta_invites").update({ sent_at: now }).eq("id", inviteRow.id),
    admin.from("beta_testers").update({ status: "invited", invited_at: now, updated_at: now }).eq("id", tester.id),
  ]).then((results) => {
    for (const result of results) if (result.error) throw result.error;
  });
  await audit(tester.id, "invite:sent", option("reason"), { expires_at: expiresAt });
  output({ email: maskedEmail(email), status: "invited", expires_at: expiresAt, delivered: true });
}

async function revokeInvite() {
  const email = emailOption();
  const tester = await findTester(email);
  const now = new Date().toISOString();
  const { error } = await admin
    .from("beta_invites")
    .update({ revoked_at: now })
    .eq("beta_tester_id", tester.id)
    .is("used_at", null)
    .is("revoked_at", null);
  if (error) throw error;
  await audit(tester.id, "invite:revoked", option("reason"));
  output({ email: maskedEmail(email), status: tester.status, invite: "revoked" });
}

async function setAccess(overrides: { phase?: string; status?: string } = {}) {
  const email = emailOption();
  const tester = await findTester(email);
  const currentPhase = tester.phase === "checkout_test" ? "max" : tester.phase;
  const phase = overrides.phase || option("phase") || currentPhase;
  const status = overrides.status || option("status");
  if (!phase || !["core", "pro", "max"].includes(phase)) throw new Error("--phase must be core, pro, or max.");
  if (!status || !["active", "paused", "completed", "revoked"].includes(status)) {
    throw new Error("--status must be active, paused, completed, or revoked.");
  }
  const days = Number(option("days") || "30");
  if (!Number.isInteger(days) || days < 1 || days > 180) throw new Error("--days must be an integer from 1 to 180.");
  const expiresAt = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();
  const licenseKey = phase === "core"
    ? null
    : betaLicenseKeyForTester(tester.id, serverEnv.licenseSigningSecret());
  const { data, error } = await admin.rpc("set_beta_tester_access", {
    p_tester_id: tester.id,
    p_phase: phase,
    p_status: status,
    p_license_hash: licenseKey ? hashLicenseKey(licenseKey) : null,
    p_license_last4: licenseKey?.slice(-4) || null,
    p_expires_at: licenseKey ? expiresAt : null,
    p_actor: actor,
    p_reason: option("reason"),
  });
  if (error) throw error;
  if (licenseKey && status === "active") {
    await sendBetaLicenseEmail({
      to: email,
      licenseKey,
      tier: phase as "pro" | "max",
      expiresAt,
      idempotencyKey: `beta-license:${tester.id}:${phase}:${expiresAt.slice(0, 10)}`,
    });
  }
  output({
    email: maskedEmail(email),
    phase,
    status,
    expires_at: licenseKey ? expiresAt : null,
    license_emailed: Boolean(licenseKey && status === "active"),
    changed: Boolean(data),
  });
}

async function gmailList() {
  const { data, error } = await admin
    .from("beta_testers")
    .select("email_normalized,status,gmail_test_user_added_at")
    .eq("gmail_test_user_required", true)
    .order("created_at", { ascending: true });
  if (error) throw error;
  output((data || []).map((row) => ({
    email: args["reveal-email"] === true
      ? row.email_normalized
      : maskedEmail(row.email_normalized),
    status: row.status,
    gmail: row.gmail_test_user_added_at ? "ready" : "owner_action",
  })));
}

async function gmailMarkAdded() {
  const email = emailOption();
  const tester = await findTester(email);
  if (!tester.gmail_test_user_required) throw new Error("This tester was not selected for Gmail testing.");
  const now = new Date().toISOString();
  const { error } = await admin
    .from("beta_testers")
    .update({ gmail_test_user_added_at: now, updated_at: now })
    .eq("id", tester.id);
  if (error) throw error;
  await audit(tester.id, "gmail:test_user_added", option("reason"));
  output({ email: maskedEmail(email), gmail: "ready" });
}

async function checkoutGate(allowed: boolean) {
  const email = emailOption();
  const tester = await findTester(email);
  if (allowed && (tester.status !== "active" || tester.phase !== "max")) {
    throw new Error("Only an active Max beta tester can enter the checkout-test phase.");
  }
  const now = new Date().toISOString();
  const phase = allowed ? "checkout_test" : tester.phase === "checkout_test" ? "max" : tester.phase;
  const { error } = await admin
    .from("beta_testers")
    .update({ checkout_test_eligible: allowed, phase, updated_at: now })
    .eq("id", tester.id);
  if (error) throw error;
  await audit(tester.id, allowed ? "checkout:allowlisted" : "checkout:disabled", option("reason"));
  output({ email: maskedEmail(email), status: tester.status, phase, checkout: allowed ? "allowlisted" : "off" });
}

async function feedback() {
  const limit = Math.min(100, Math.max(1, Number(option("limit") || "25") || 25));
  const requestedEmail = option("email") || positionals[0];
  const requestedTester = requestedEmail
    ? await findTester(normalizeEmail(requestedEmail) || "invalid")
    : null;
  let query = admin
    .from("beta_feedback")
    .select("id,beta_tester_id,category,feature_screen,severity,status,feedback_quality,created_at")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (requestedTester) query = query.eq("beta_tester_id", requestedTester.id);
  const { data, error } = await query;
  if (error) throw error;
  output((data || []).map((row) => ({
    id: String(row.id).slice(0, 8),
    tester: String(row.beta_tester_id).slice(0, 8),
    category: row.category,
    feature: row.feature_screen,
    severity: row.severity,
    status: row.status,
    quality: row.feedback_quality,
    created_at: row.created_at,
  })));
}

function help() {
  output({
    usage: "npm run beta:ops -- <command> [options]",
    commands: [
      "list --status confirmed [--os macos] [--bank hdfc] [--use budgeting]",
      "list [--status active]",
      "shortlist EMAIL --cohort COHORT [--gmail] [--reason TEXT]",
      "invite EMAIL [--reason TEXT]",
      "revoke-invite EMAIL [--reason TEXT]",
      "activate EMAIL [--days 30] [--reason TEXT]",
      "phase EMAIL core|pro|max [--days 30] [--reason TEXT]",
      "pause EMAIL [--reason TEXT]",
      "revoke EMAIL [--reason TEXT]",
      "complete EMAIL [--reason TEXT]",
      "access --email EMAIL --phase core|pro|max --status active|paused|completed|revoked [--days 30] [--reason TEXT]",
      "gmail-list [--reveal-email]",
      "gmail-mark-added EMAIL [--reason TEXT]",
      "checkout-allow EMAIL [--reason TEXT]",
      "checkout-deny EMAIL [--reason TEXT]",
      "feedback [EMAIL] [--limit 25]",
    ],
    note: "Raw invitation tokens, license keys, and service credentials are never printed.",
  });
}

async function main() {
  if (command === "help") {
    help();
    return;
  }
  admin = createAdminClient();
  if (command === "list") await list();
  else if (command === "shortlist") await shortlist();
  else if (command === "invite") await invite();
  else if (command === "revoke-invite") await revokeInvite();
  else if (command === "access") await setAccess();
  else if (command === "activate") await setAccess({ status: "active" });
  else if (command === "phase") await setAccess({ phase: positionals[1], status: "active" });
  else if (command === "pause") await setAccess({ status: "paused" });
  else if (command === "revoke") await setAccess({ status: "revoked" });
  else if (command === "complete") await setAccess({ status: "completed" });
  else if (command === "gmail-list") await gmailList();
  else if (command === "gmail-mark-added") await gmailMarkAdded();
  else if (command === "checkout-allow") await checkoutGate(true);
  else if (command === "checkout-deny") await checkoutGate(false);
  else if (command === "feedback") await feedback();
  else help();
}

main().catch((error) => {
  process.stderr.write(`Beta operation failed: ${error instanceof Error ? error.message : "Unknown error"}\n`);
  process.exitCode = 1;
});
