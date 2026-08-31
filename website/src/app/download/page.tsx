import type { Metadata } from "next";
import Link from "next/link";

import { SignInButton } from "@/components/auth-controls";
import { betaPortalState } from "@/lib/beta-access";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: "Private beta downloads",
  description: "Selected GODFIN beta build availability.",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

export default async function DownloadPage() {
  const supabase = await createSupabaseServerClient();
  const { data: { user } } = (await supabase?.auth.getUser()) || { data: { user: null } };
  const tester = user ? await betaPortalState(user.id) : null;
  const active = tester?.status === "active";
  const macUrl = active ? process.env.BETA_MAC_APPLE_SILICON_DOWNLOAD_URL?.trim() : null;
  const windowsUrl = active ? process.env.BETA_WINDOWS_X64_DOWNLOAD_URL?.trim() : null;

  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">Selected desktop beta</div>
          <h1>Private beta builds</h1>
          <p>
            The first group currently tests Macs with Apple chips and Windows PCs. Build
            access does not sync or upload your desktop financial records.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell narrow-shell">
          {!user ? (
            <div className="account-card">
              <h2>Sign in with your invited email</h2>
              <p>Only accepted testers can see private build links. Not invited yet?</p>
              <SignInButton next="/download" />
              <Link className="text-link" href="/#waitlist">Join the early testers →</Link>
            </div>
          ) : !active ? (
            <div className="account-card">
              <h2>No active build access</h2>
              <p>This account does not have an active beta invite yet.</p>
              <Link className="button-secondary" href="/beta">Return to beta portal</Link>
              <Link className="text-link" href="/#waitlist">Join the early testers →</Link>
            </div>
          ) : (
            <>
              <div className="download-grid">
                <section className="account-card">
                  <div className="eyebrow">Mac with Apple chip</div>
                  <h2>macOS beta</h2>
                  <p>For M-series Macs only. Intel Mac testing comes later.</p>
                  {macUrl ? (
                    <a className="button" href={macUrl} rel="noreferrer">Download selected Mac build</a>
                  ) : (
                    <p className="notice">The owner has not attached a Mac build to this cohort yet.</p>
                  )}
                </section>
                <section className="account-card">
                  <div className="eyebrow">Windows PC</div>
                  <h2>Windows beta</h2>
                  <p>For Windows 10 22H2 or Windows 11 on x64 computers.</p>
                  {windowsUrl ? (
                    <a className="button" href={windowsUrl} rel="noreferrer">Download selected Windows build</a>
                  ) : (
                    <p className="notice">The owner has not attached a Windows build to this cohort yet.</p>
                  )}
                </section>
              </div>
              <div className="callout">
                These are private test builds, not public signed downloads. Keep the
                link private and use the checksum supplied with the build.
              </div>
            </>
          )}
        </div>
      </section>
    </>
  );
}
