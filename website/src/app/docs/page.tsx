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
            <a href="#gmail">Gmail</a>
            <a href="#backup">Backups</a>
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

            <h2 id="backup">Backups</h2>
            <p>
              Settings → Backup creates a local safety copy. GODFIN keeps the latest
              seven daily and four weekly copies. Store another copy on an external
              drive if losing the records would matter to you.
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
          </article>
        </div>
      </section>
    </>
  );
}
