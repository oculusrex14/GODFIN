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
      "What stays on your laptop, what the website can see, and where you stay in control.",
  },
  {
    slug: "clean-statement-imports",
    title: "How to import a bank statement without losing trust",
    summary:
      "Why GODFIN shows you what it found before adding anything to your month.",
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
          <h1>Notes on money that stays on your computer</h1>
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
