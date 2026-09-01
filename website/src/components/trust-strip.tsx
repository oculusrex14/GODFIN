import { Bot, Laptop, ShieldCheck, WalletCards } from "lucide-react";

const trustItems = [
  {
    icon: Laptop,
    title: "Money records stay local",
    body: "Statements and everyday finance records stay in the desktop app on your computer.",
  },
  {
    icon: ShieldCheck,
    title: "Try the demo without an account",
    body: "The public demo uses made-up data and never connects to a bank or payment service.",
  },
  {
    icon: WalletCards,
    title: "No software subscription",
    body: "Core is free. Pro and Max are planned as one-time lifetime licenses.",
  },
  {
    icon: Bot,
    title: "AI and Gmail are optional",
    body: "Core calculations and sorting work without either connection.",
  },
];

export function TrustStrip({ compact = false }: { compact?: boolean }) {
  return (
    <aside
      aria-label="What GODFIN promises"
      className={`trust-strip${compact ? " trust-strip-compact" : ""}`}
    >
      <div className="shell trust-strip-grid">
        {trustItems.map(({ body, icon: Icon, title }) => (
          <div className="trust-strip-item" key={title}>
            <Icon aria-hidden="true" size={18} />
            <div>
              <strong>{title}</strong>
              {!compact ? <span>{body}</span> : null}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
