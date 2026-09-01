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
          <h1>Notes from GODFIN</h1>
          <p>
            Practical writing about understanding your money, keeping the record
            local, and working with Indian bank statements. No fluff, affiliate
            links, or product-pushing dressed up as advice.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell feature-grid blog-grid">
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
        <div className="shell blog-next-note">
          <div className="eyebrow eyebrow-accent">Coming next</div>
          <p>How category memory works, a five-minute weekly money check-in, and what a finance app should explain before it asks for trust.</p>
        </div>
      </section>
    </>
  );
}
