import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documentation",
  description: "Install, secure, and use GODFIN with supported Indian banks.",
};

export default function DocsPage() {
  return (
    <>
      <section className="page-hero">
        <div className="shell">
          <div className="eyebrow" style={{ color: "var(--teal-dark)" }}>
            Documentation
          </div>
          <h1>From first launch to a clean month</h1>
          <p>
            GODFIN is designed to stay understandable: local database, explicit
            connections, and reversible edits until you finalize a month.
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
              Signed public installers are not published during the private
              preview. When a release is available, use only the platform link
              shown on the download page and verify its published signature and
              checksum. The app starts a local interface and local API bound to
              <code>127.0.0.1</code>.
            </p>
            <div className="callout">
              Leave “Allow network access” off unless you deliberately want to
              use GODFIN from another device on your LAN.
            </div>

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
            <h3>SBI, ICICI, Axis, and Kotak</h3>
            <p>
              These are on the parser roadmap and are not supported by the
              launch build. GODFIN will ship each bank-specific parser only
              after its formats are validated; the app does not silently guess
              at an incompatible statement.
            </p>

            <h2 id="gmail">Gmail</h2>
            <p>
              Gmail is optional and separate from website sign-in. The desktop
              app requests the exact OAuth scope
              <code>https://www.googleapis.com/auth/gmail.readonly</code>, which
              permits message and mailbox-settings viewing. GODFIN uses it to
              search matching bank-alert messages; it does not request Gmail
              send, edit, or delete access. OAuth credentials and tokens are
              encrypted locally, and the website account is not involved.
            </p>

            <h2 id="backup">Backups</h2>
            <p>
              Settings → Backup creates a local SQLite snapshot. Automatic
              retention keeps the latest seven daily and four weekly backups.
              Store a copy on an external drive if the data matters.
            </p>

            <h2 id="licenses">Activate Pro or Max</h2>
            <ol>
              <li>Purchase a lifetime license on the pricing page.</li>
              <li>Copy the key from the delivery email.</li>
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
              No. The desktop app and its SQLite database run locally. The
              website handles accounts, downloads, purchases, and licenses.
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
