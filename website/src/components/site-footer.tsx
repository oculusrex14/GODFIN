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
              A local-first personal finance app for people who want to understand
              their money without trading away their bank history.
            </p>
            <a className="footer-email" href="mailto:hello@godfin.dev">hello@godfin.dev</a>
          </div>
          <div className="footer-col">
            <strong>Explore</strong>
            <Link href="/how-it-works">Features</Link>
            <Link href="/demo">Try the real app</Link>
            <Link href="/pricing">Pricing</Link>
            <Link href="/roadmap">Roadmap</Link>
          </div>
          <div className="footer-col">
            <strong>Story</strong>
            <Link href="/about">About</Link>
            <Link href="/blog">Blog</Link>
            <Link href="/contact">Contact</Link>
            <Link href="/changelog">Changelog</Link>
            <Link href="/#waitlist">Join the early testers</Link>
          </div>
          <div className="footer-col">
            <strong>Help</strong>
            <Link href="/docs">Docs and support</Link>
            <Link href="/download">Private beta builds</Link>
            <Link href="/account">Account</Link>
            <Link href="/beta">Tester portal</Link>
          </div>
          <div className="footer-col">
            <strong>Trust</strong>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
          </div>
        </div>
        <div className="footer-bottom">
          <span>Built independently in India. © {new Date().getFullYear()} GODFIN.</span>
          <span>For information only—not financial, investment, tax, or legal advice.</span>
          <span>PolyForm Noncommercial 1.0.0 · planned lifetime licenses</span>
        </div>
      </div>
    </footer>
  );
}
