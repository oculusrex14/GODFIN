import type { Metadata } from "next";
import { notFound } from "next/navigation";

const articles = {
  "local-first-finance": {
    title: "What local-first actually means for a finance app",
    description:
      "The architecture behind keeping a finance ledger local while still supporting purchases and licenses.",
    sections: [
      [
        "Start with the data boundary",
        "A privacy promise is useful only when it maps to architecture. In GODFIN, statements, transactions, balances, merchant memory, budgets, and reports belong to the desktop application and its local SQLite database.",
      ],
      [
        "Keep commerce separate",
        "The website needs an email address, a purchase record, a license state, and device activation records. It does not need a copy of the user’s ledger. Separating these systems narrows both the security surface and the meaning of consent.",
      ],
      [
        "Make network features optional",
        "Gmail ingestion, optional AI provider connections, license checks, and updates can improve the product without becoming prerequisites for local bookkeeping. When the network disappears, the local rules and records should remain useful.",
      ],
    ],
  },
  "clean-statement-imports": {
    title: "How to import a bank statement without losing trust",
    description:
      "A safer workflow for statement parsing, reconciliation, and duplicate handling.",
    sections: [
      [
        "Preview before mutation",
        "A statement importer should identify the account, date range, row count, and likely format before changing the ledger. That gives the user a chance to stop a bad parse early.",
      ],
      [
        "Reconcile deterministically",
        "Checksums, dates, amounts, and account context are more reliable than filenames. Existing transactions should be matched or skipped explicitly, not inserted and cleaned up later.",
      ],
      [
        "Return a report, not a mystery",
        "A successful import should say what was imported, skipped as duplicate, classified automatically, sent to review, or rejected. Auxiliary merchant-memory updates should never erase the main result.",
      ],
    ],
  },
} as const;

type ArticleSlug = keyof typeof articles;

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const article = articles[slug as ArticleSlug];
  return article
    ? { title: article.title, description: article.description }
    : {};
}

export default async function ArticlePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const article = articles[slug as ArticleSlug];
  if (!article) notFound();

  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            GODFIN guide
          </div>
          <h1>{article.title}</h1>
          <p>{article.description}</p>
        </div>
      </section>
      <section className="page-content">
        <article className="shell narrow prose">
          {article.sections.map(([heading, body]) => (
            <section key={heading}>
              <h2>{heading}</h2>
              <p>{body}</p>
            </section>
          ))}
        </article>
      </section>
    </>
  );
}
