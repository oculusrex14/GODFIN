import Link from "next/link";

import { GodfinLogo } from "./godfin-logo";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell">
        <div className="footer-grid">
          <div>
            <Link className="brand" href="/"><GodfinLogo tagline /></Link>
            <p className="footer-copy">
              A desktop-first way to understand everyday money while keeping ordinary
              finance records on your own computer.
            </p>
            <a className="footer-email" href="mailto:hello@godfin.dev">hello@godfin.dev</a>
          </div>
          <div className="footer-col">
            <strong>Explore</strong>
            <Link href="/demo">Public demo</Link>
            <Link href="/how-it-works">How it works</Link>
            <Link href="/pricing">Planned pricing</Link>
            <Link href="/#waitlist">Join beta</Link>
          </div>
          <div className="footer-col">
            <strong>Help</strong>
            <Link href="/docs">Setup and support</Link>
            <Link href="/account">Account</Link>
            <Link href="/beta">Selected testers</Link>
            <Link href="/changelog">Changelog</Link>
          </div>
          <div className="footer-col">
            <strong>Trust</strong>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
          </div>
        </div>
        <div className="footer-bottom">
          © {new Date().getFullYear()} GODFIN · PolyForm Noncommercial 1.0.0 ·
          planned lifetime licenses, no software subscription
        </div>
      </div>
    </footer>
  );
}
