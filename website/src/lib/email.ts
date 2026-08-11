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
