import Link from "next/link";
import { GodfinLogo } from "./godfin-logo";

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="shell nav-row">
        <Link className="brand" href="/">
          <GodfinLogo />
        </Link>
        <nav className="nav-links" aria-label="Primary navigation">
          <Link href="/#features">Features</Link>
          <Link href="/pricing">Pricing</Link>
          <Link href="/docs">Docs</Link>
          <Link href="/download">Download</Link>
        </nav>
        <Link className="button-ghost" href="/account">
          Account
        </Link>
      </div>
    </header>
  );
}
