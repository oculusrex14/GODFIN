import { Resend } from "resend";

import { serverEnv, siteUrl } from "@/lib/env";
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
  const { error } = await resend.emails.send(
    {
      from: serverEnv.resendFromEmail(),
      to,
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
