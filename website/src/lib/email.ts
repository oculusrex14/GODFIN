import { Resend } from "resend";

import { publicContactConfig, serverEnv, siteUrl } from "@/lib/env";
import type { LicenseTier } from "@/lib/license";

export async function sendLicenseEmail({
  to,
  licenseKey,
  tier,
  idempotencyKey,
}: {
  to: string;
  licenseKey: string;
  tier: LicenseTier;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { supportEmail } = publicContactConfig();
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(supportEmail ? { replyTo: supportEmail } : {}),
      subject: `Your GODFIN ${tier === "max" ? "Max" : "Pro"} lifetime license`,
      text: [
        `Your GODFIN ${tier.toUpperCase()} lifetime license is ready.`,
        "",
        licenseKey,
        "",
        "Open GODFIN → Settings → License, paste this key, and activate.",
        `Manage your account: ${siteUrl()}/account`,
        "",
        "Keep this key private. Your desktop financial database remains local.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#07131f">
          <p style="color:#087b6d;font-weight:700">GODFIN ${tier.toUpperCase()}</p>
          <h1>Your lifetime license is ready</h1>
          <p>Open GODFIN → Settings → License, paste the key below, and activate.</p>
          <div style="padding:18px;border-radius:12px;background:#eef3ee;font:700 18px monospace;word-break:break-all">${licenseKey}</div>
          <p style="margin-top:24px"><a href="${siteUrl()}/account">Manage your GODFIN account</a></p>
          <p style="color:#667987;font-size:13px">Keep this key private. Your desktop financial database remains local.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}

export async function sendPlanUpgradeEmail({
  to,
  idempotencyKey,
}: {
  to: string;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { supportEmail } = publicContactConfig();
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(supportEmail ? { replyTo: supportEmail } : {}),
      subject: "Your GODFIN lifetime license is now Max",
      text: [
        "Your existing GODFIN Pro lifetime license has been upgraded to Max.",
        "",
        "Keep using the same license key. In the desktop app, open Settings → License and choose Refresh license if Max does not appear automatically.",
        `Manage your account: ${siteUrl()}/account`,
        "",
        "No subscription or recurring AI credits were added.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#07131f">
          <p style="color:#087b6d;font-weight:700">GODFIN MAX</p>
          <h1>Your lifetime license has been upgraded</h1>
          <p>Keep using the same license key. In GODFIN, open Settings → License and choose <strong>Refresh license</strong> if Max does not appear automatically.</p>
          <p style="margin-top:24px"><a href="${siteUrl()}/account">Manage your GODFIN account</a></p>
          <p style="color:#667987;font-size:13px">No subscription or recurring AI credits were added.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}

export async function sendWaitlistConfirmationEmail({
  to,
  confirmationUrl,
  idempotencyKey,
}: {
  to: string;
  confirmationUrl: string;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { privacyEmail } = publicContactConfig();
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(privacyEmail ? { replyTo: privacyEmail } : {}),
      subject: "Confirm your GODFIN waitlist place",
      text: [
        "Confirm that you want product and launch updates from GODFIN:",
        "",
        confirmationUrl,
        "",
        "If you did not request this, ignore the email. Joining the waitlist does not create a desktop-data account.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#07131f">
          <p style="color:#087b6d;font-weight:700">GODFIN WAITLIST</p>
          <h1>Confirm your place</h1>
          <p>One click confirms that you want product and launch updates from GODFIN.</p>
          <p style="margin:28px 0"><a href="${confirmationUrl}" style="display:inline-block;padding:13px 20px;border-radius:10px;background:#087b6d;color:white;text-decoration:none;font-weight:700">Confirm waitlist</a></p>
          <p style="color:#667987;font-size:13px">If you did not request this, ignore the email. Joining the waitlist does not create a desktop-data account.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}

export async function sendWaitlistConfirmedEmail({
  to,
  idempotencyKey,
}: {
  to: string;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { privacyEmail } = publicContactConfig();
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(privacyEmail ? { replyTo: privacyEmail } : {}),
      subject: "You’re on the GODFIN early-tester list",
      text: [
        "Your GODFIN waitlist email is confirmed.",
        "",
        "You can optionally tell us which supported computer and statement formats you can help test. Never send a bank statement, account number, PIN, license key, or Gmail content.",
        `See the public demo: ${siteUrl()}/demo`,
        "",
        "We will contact a small number of people for the first Apple Silicon Mac and Windows x64 beta.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#17201c">
          <p style="color:#2f6b52;font-weight:700">GODFIN EARLY TESTERS</p>
          <h1>Your email is confirmed</h1>
          <p>You can optionally tell us which supported computer and statement formats you can help test.</p>
          <p><strong>Never send a bank statement, account number, PIN, license key, or Gmail content.</strong></p>
          <p style="margin:28px 0"><a href="${siteUrl()}/demo" style="display:inline-block;padding:13px 20px;border-radius:10px;background:#2f6b52;color:white;text-decoration:none;font-weight:700">Try the made-up household demo</a></p>
          <p style="color:#626b65;font-size:13px">We will contact a small number of people for the first Apple Silicon Mac and Windows x64 beta.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}

export async function sendBetaInviteEmail({
  to,
  inviteUrl,
  cohort,
  idempotencyKey,
}: {
  to: string;
  inviteUrl: string;
  cohort: string;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { supportEmail } = publicContactConfig();
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(supportEmail ? { replyTo: supportEmail } : {}),
      subject: "Your private GODFIN beta invitation",
      text: [
        "You have been selected for the GODFIN desktop beta.",
        `Cohort: ${cohort}`,
        "",
        inviteUrl,
        "",
        "Open the link, then continue with the same Google email address that received this message. The one-time link expires in 48 hours.",
        "Never reply with a statement, account number, PIN, license key, or Gmail content.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#17201c">
          <p style="color:#2f6b52;font-weight:700">GODFIN PRIVATE BETA</p>
          <h1>You’re invited</h1>
          <p>You have been selected for cohort <strong>${cohort}</strong>.</p>
          <p style="margin:28px 0"><a href="${inviteUrl}" style="display:inline-block;padding:13px 20px;border-radius:10px;background:#2f6b52;color:white;text-decoration:none;font-weight:700">Accept private invitation</a></p>
          <p>Continue with the same Google email address that received this message. The one-time link expires in 48 hours.</p>
          <p style="color:#626b65;font-size:13px">Never send GODFIN a statement, account number, PIN, license key, or Gmail content.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}

export async function sendBetaLicenseEmail({
  to,
  licenseKey,
  tier,
  expiresAt,
  idempotencyKey,
}: {
  to: string;
  licenseKey: string;
  tier: "pro" | "max";
  expiresAt: string;
  idempotencyKey: string;
}) {
  const resend = new Resend(serverEnv.resendApiKey());
  const { supportEmail } = publicContactConfig();
  const expiryLabel = new Intl.DateTimeFormat("en-IN", {
    dateStyle: "long",
    timeZone: "Asia/Kolkata",
  }).format(new Date(expiresAt));
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
      ...(supportEmail ? { replyTo: supportEmail } : {}),
      subject: `Your revocable GODFIN ${tier === "max" ? "Max" : "Pro"} beta key`,
      text: [
        `Your selected GODFIN ${tier.toUpperCase()} beta phase is ready.`,
        "",
        licenseKey,
        "",
        "Open GODFIN → Settings → License, paste this key, and activate.",
        `This beta key expires on ${expiryLabel}, can be paused or revoked, and uses the normal three-device limit. It is not a purchase or lifetime license.`,
        `Manage your beta access: ${siteUrl()}/beta`,
        "",
        "Keep this key private. Your desktop financial database remains local.",
      ].join("\n"),
      html: `
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#17201c">
          <p style="color:#2f6b52;font-weight:700">GODFIN PRIVATE BETA</p>
          <h1>Your ${tier === "max" ? "Max" : "Pro"} beta phase is ready</h1>
          <p>Open GODFIN → Settings → License, paste the key below, and activate.</p>
          <div style="padding:18px;border-radius:12px;background:#eef3ee;font:700 18px monospace;word-break:break-all">${licenseKey}</div>
          <p>This revocable beta key expires on <strong>${expiryLabel}</strong> and uses the normal three-device limit. It is not a purchase or lifetime license.</p>
          <p style="margin-top:24px"><a href="${siteUrl()}/beta">Manage your beta access</a></p>
          <p style="color:#626b65;font-size:13px">Keep this key private. Your desktop financial database remains local.</p>
        </div>
      `,
    },
    { idempotencyKey },
  );
  if (error) throw new Error(error.message);
}
