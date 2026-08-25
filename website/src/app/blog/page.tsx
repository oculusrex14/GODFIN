import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Blog",
  description: "Local-first finance, Indian statement workflows, and practical privacy.",
};

const articles = [
  {
    slug: "local-first-finance",
    title: "What local-first actually means for a finance app",
    summary:
      "A concrete boundary between the database on your laptop and the services needed to sell and support the app.",
  },
  {
    slug: "clean-statement-imports",
    title: "How to import a bank statement without losing trust",
    summary:
      "Preview, reconciliation, duplicate detection, and why an import report matters more than a spinner.",
  },
];

export default function BlogPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            Notes from GODFIN
          </div>
          <h1>Privacy with implementation details</h1>
          <p>
            Practical writing about personal finance software, local data, and
            workflows for Indian bank statements.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell feature-grid">
          {articles.map((article) => (
            <article className="content-card" key={article.slug}>
              <div className="eyebrow eyebrow-accent">
                Guide
              </div>
              <h2>{article.title}</h2>
              <p>{article.summary}</p>
              <Link href={`/blog/${article.slug}`}>Read article →</Link>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
