"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { GodfinLogo } from "./godfin-logo";

const links = [
  { href: "/demo", label: "Demo" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/pricing", label: "Pricing" },
  { href: "/#waitlist", label: "Join beta" },
];

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <div className="shell nav-row">
        <Link aria-label="GODFIN home" className="brand" href="/" onClick={() => setOpen(false)}>
          <GodfinLogo />
        </Link>
        <button
          aria-controls="primary-navigation"
          aria-expanded={open}
          aria-label={open ? "Close navigation" : "Open navigation"}
          className="mobile-menu-button"
          onClick={() => setOpen((value) => !value)}
          type="button"
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
        <nav
          className={`nav-links${open ? " nav-links-open" : ""}`}
          id="primary-navigation"
          aria-label="Primary navigation"
        >
          {links.map((link) => (
            <Link href={link.href} key={link.href} onClick={() => setOpen(false)}>
              {link.label}
            </Link>
          ))}
        </nav>
        <Link className="account-link" href="/account">Sign in</Link>
      </div>
    </header>
  );
}
