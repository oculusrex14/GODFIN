import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Documentation",
  description: "Install, secure, and use GODFIN with supported Indian banks.",
};

export default function DocsPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow eyebrow-accent">
            Documentation
          </div>
          <h1>How to set up GODFIN on your computer</h1>
          <p>
            Start here when you receive a beta invite. These steps explain the app
            without assuming you know finance or software terms.
          </p>
        </div>
      </section>
      <section className="page-content">
        <div className="shell docs-grid">
          <nav className="docs-nav" aria-label="Documentation sections">
            <a href="#install">Install</a>
            <a href="#first-run">First run</a>
            <a href="#statements">Statements</a>
            <a href="#review">Review and memory</a>
            <a href="#planning">Budgets and goals</a>
            <a href="#reports">Reports</a>
            <a href="#gmail">Gmail</a>
            <a href="#ai">Optional AI</a>
            <a href="#backup">Backups</a>
            <a href="#your-data">Your data</a>
            <a href="#technical">Technically curious</a>
            <a href="#licenses">Licenses</a>
            <a href="#faq">FAQ</a>
          </nav>
          <article className="content-card prose">
            <h2 id="install">Install</h2>
            <p>
              During the beta, only invited testers receive a download link. If you
              already have an invite, open the download page and choose Mac or
              Windows. If you do not have one yet, join the early testers first.
            </p>
            <div className="inline-actions">
              <Link className="button-secondary" href="/download">Open downloads</Link>
              <Link className="button-ghost" href="/#waitlist">Join the early testers</Link>
            </div>
            <details>
              <summary>If you are curious how it runs</summary>
              <p>GODFIN starts the screen you use and a private helper service on the same computer. It listens only on <code>127.0.0.1</code> by default. Leave “Allow network access” off unless you deliberately want another device on your home network to reach it.</p>
            </details>

            <h2 id="first-run">First run</h2>
            <ol>
              <li>Choose a local PIN. It is not sent to the website.</li>
              <li>Skip or connect Gmail for supported transaction alerts.</li>
              <li>Upload a statement or add a transaction manually.</li>
              <li>Review unfamiliar merchants and confirm their categories.</li>
              <li>Create a backup before making larger changes.</li>
            </ol>
            <p>
              <strong>Learn GODFIN</strong> is a readable guide you can open at any
              time. The separate in-app tutorial moves through real screens, can be
              skipped or paused, and can be restarted later from Settings.
            </p>

            <h2 id="statements">Bank statements</h2>
            <h3>HDFC</h3>
            <p>
              Core supports manual HDFC statement import. Select the matching
              account, preview reconciliation, then import. Password-protected
              statement passwords are used locally for that operation.
            </p>
            <h3>SBI and Kotak</h3>
            <p>
              Current tested formats also include selected SBI savings relationship
              statements and Kotak savings statements. Bank files change over time,
              so GODFIN stops and explains the problem when it does not recognize a
              format instead of inventing transactions.
            </p>

            <h2 id="review">Review and category memory</h2>
            <p>
              The Review queue is for transactions that need a human choice. Correct
              a category only when you recognize the payment. GODFIN can remember a
              confirmed merchant for later matches and shows the reason it used.
            </p>
            <p>
              Finalised months do not change silently. You can inspect, undo, export,
              or reset learned category memory from the app. Automatic sorting is a
              helper, not a substitute for checking important records.
            </p>

            <h2 id="planning">Budgets, goals, and regular payments</h2>
            <p>
              Budgets compare planned limits with classified spending. Goals start
              with an optional amount already saved, then keep a dated history of
              deposits and withdrawals. A projection is only an estimate and shows
              its assumptions and available data.
            </p>
            <p>
              Regular-payment detection looks for repeated merchant, amount, and
              timing evidence. Review every suggestion. GODFIN does not cancel a
              subscription or move money into an FD, RD, or goal for you.
            </p>

            <h2 id="reports">Reports and explanations</h2>
            <p>
              Standard reports use verified local calculations for money in,
              spending, savings, budgets, goals, and regular payments. Information
              bubbles explain unfamiliar ratios in plain language and show the
              period and inputs behind them.
            </p>
            <p>
              Optional AI can help describe those verified figures. It does not
              produce the authoritative totals. The CA tax pack is a review aid, not
              a completed income-tax return and not a replacement for AIS, TIS,
              Form 26AS, Form 16, official records, or professional advice.
            </p>

            <h2 id="gmail">Gmail</h2>
            <p>
              Gmail is optional and separate from signing in on this website. If you
              connect it, the desktop app asks for read-only access so it can look for
              supported bank alerts. It cannot send, edit, or delete email. The exact
              Google permission is
              <code>https://www.googleapis.com/auth/gmail.readonly</code>, which
              permits message and mailbox-settings viewing. The connection details
              are protected on your computer, and the website account is not involved.
            </p>

            <h2 id="ai">Optional AI</h2>
            <p>
              You can continue without AI, use a supported local model through
              Ollama, or connect a supported provider with your own key. GODFIN shows
              the model size and expected computer requirements before a local model
              download; it should never begin a model download merely because a
              setting was switched on.
            </p>
            <p>
              Cloud AI requires separate consent. GODFIN removes exact amounts,
              dates, payment addresses, phone numbers, account fragments, references,
              and long number sequences before sending the remaining prompt. This
              reduces exposure but does not make the prompt anonymous.
            </p>

            <h2 id="backup">Backups</h2>
            <p>
              Settings → Backup creates a local safety copy. GODFIN keeps the latest
              seven daily and four weekly copies. Store another copy on an external
              drive if losing the records would matter to you.
            </p>

            <h2 id="your-data">Exporting or removing your data</h2>
            <p>
              The desktop app keeps ordinary statements, transactions, categories,
              budgets, goals, reports, settings, and backups on your computer. Use
              the app&apos;s export tools before resetting data. A reset cannot remove
              an original statement stored elsewhere on your computer, and deleting
              a website account does not delete the local app record.
            </p>

            <h2 id="licenses">Activate Pro or Max</h2>
            <p>Public checkout is closed during the beta. Selected testers receive temporary test access; nobody should pay for a permanent license yet.</p>
            <ol>
              <li>Open the beta email sent to your invited address.</li>
              <li>Copy the temporary test key.</li>
              <li>Open Settings → License in the desktop app.</li>
              <li>Paste the key and activate this device.</li>
            </ol>
            <p>
              License verification sends the key and a random installation ID,
              plus a generic operating-system/architecture label and app
              version. The server hashes the installation ID before storage.
              It does not send transactions, statement files, balances, or
              merchant history.
            </p>

            <h2 id="technical">For the technically curious</h2>
            <p>
              GODFIN&apos;s ordinary finance record is stored in a local SQLite database,
              with schema changes applied through additive, restart-safe migrations.
              Before a migration, the app creates a local safety backup. The desktop
              helper listens on <code>127.0.0.1</code> by default.
            </p>
            <p>
              The classification engine starts with deterministic rules and confirmed
              merchant memory. Embeddings and AI are optional helpers, never the source
              of authoritative totals. The desktop app does not send product analytics.
            </p>
            <p>
              OpenDataLoader remains a benchmark-only PDF adapter. It is not bundled
              into live statement uploads unless a lawful redacted test set proves that
              the accuracy gain justifies adding its Java runtime.
            </p>
            <p>
              The source is governed by PolyForm Noncommercial 1.0.0. The repository
              remains private during the beta; commercial use and commercial forks
              require written approval.
            </p>

            <h2 id="faq">FAQ</h2>
            <h3>Is GODFIN cloud software?</h3>
            <p>
              No. The desktop app and its money-record file run on your computer.
              The website handles tester access and, later, purchases and licenses.
            </p>
            <h3>Is there a subscription?</h3>
            <p>
              No software subscription. Pro and Max are lifetime licenses.
              GODFIN does not currently sell hosted AI credit packs.
            </p>
            <h3>Can I use my own AI key?</h3>
            <p>
              Yes. A supported provider key is encrypted on your device. You
              can also use a supported local model or continue without AI.
            </p>
            <h3>Does GODFIN connect directly to my bank?</h3>
            <p>No. The current workflow uses statement files you choose and optional supported bank-alert email. It does not ask for internet-banking credentials.</p>
            <h3>Can a report tell me which tax return to file?</h3>
            <p>No. Transaction data alone is incomplete. Use official tax records and, where needed, a qualified CA or tax professional.</p>
          </article>
        </div>
      </section>
    </>
  );
}
