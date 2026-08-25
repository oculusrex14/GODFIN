import Image from "next/image";

export function GodfinLogo({ tagline = false }: { tagline?: boolean }) {
  return (
    <span className="godfin-logo">
      <Image src="/godfin-vault-dial.png" alt="" aria-hidden="true" width={44} height={44} />
      <span>
        <span className="godfin-wordmark" aria-label="GODFIN">
          <span>GOD</span><span>FIN</span>
        </span>
        {tagline ? <small>Local-first. Private. In control.</small> : null}
      </span>
    </span>
  );
}
