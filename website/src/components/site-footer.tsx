import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell">
        <div className="footer-grid">
          <div>
            <Link className="brand" href="/">
              <span className="brand-mark">GF</span>
              GODFIN
            </Link>
            <p className="footer-copy">
              A local-first personal finance app for people who refuse to trade
              their bank history for convenience.
            </p>
          </div>
          <div className="footer-col">
            <strong>Product</strong>
            <Link href="/download">Download</Link>
            <Link href="/pricing">Pricing</Link>
            <Link href="/changelog">Changelog</Link>
          </div>
          <div className="footer-col">
            <strong>Learn</strong>
            <Link href="/docs">Documentation</Link>
            <Link href="/blog">Blog</Link>
            <Link href="/docs#faq">FAQ</Link>
          </div>
          <div className="footer-col">
            <strong>Legal</strong>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
            <Link href="/account">Account</Link>
          </div>
        </div>
        <div className="footer-bottom">
          © {new Date().getFullYear()} GODFIN · PolyForm Noncommercial 1.0.0 ·
          Lifetime licenses only
        </div>
      </div>
    </footer>
  );
}
