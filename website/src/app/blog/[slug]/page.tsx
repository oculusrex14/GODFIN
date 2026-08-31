import type { Metadata } from "next";
import { notFound } from "next/navigation";

const articles = {
  "local-first-finance": {
    title: "What local-first actually means for a finance app",
    description:
      "What stays on your laptop, what the website can see, and why the two are kept apart.",
    sections: [
      [
        "Start with the data boundary",
        "A privacy promise should be easy to check. In GODFIN, statements, transactions, balances, category memory, budgets, and reports belong to the desktop app and the money-record file on your computer.",
      ],
      [
        "Keep commerce separate",
        "The website may need an email address, tester access, a purchase record after checkout opens, a license state, and device activation records. It does not need a copy of your transactions. Keeping these systems apart limits what any website problem could expose.",
      ],
      [
        "Make network features optional",
        "Gmail, optional AI connections, license checks, and updates can help without becoming requirements for everyday use. When the internet disappears, your local rules and records should still work.",
      ],
    ],
  },
  "clean-statement-imports": {
    title: "How to import a bank statement without losing trust",
    description:
      "How GODFIN checks a statement and shows what it found before adding anything.",
    sections: [
      [
        "Preview before mutation",
        "Before adding anything, GODFIN should show the account, date range, number of rows, and statement format it found. You get a chance to stop if any of that looks wrong.",
      ],
      [
        "Reconcile deterministically",
        "Dates, amounts, account details, and file fingerprints are safer than trusting a filename. Existing transactions should be matched or skipped clearly, not added twice and cleaned up later.",
      ],
      [
        "Return a report, not a mystery",
        "A finished import should say what was added, what was already there, what GODFIN understood, what needs your review, and what it could not read. You should never be left guessing what the spinner did.",
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
