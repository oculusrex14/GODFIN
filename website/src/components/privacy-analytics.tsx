"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

const CONSENT_KEY = "godfin_analytics_consent";
const CONSENT_EVENT = "godfin-analytics-consent";

type Consent = "granted" | "denied" | null;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

function readConsent(): Consent {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(CONSENT_KEY);
  return value === "granted" || value === "denied" ? value : null;
}

function useAnalyticsConsent() {
  const [consent, setConsent] = useState<Consent>(null);

  useEffect(() => {
    const sync = () => setConsent(readConsent());
    sync();
    window.addEventListener(CONSENT_EVENT, sync);
    return () => window.removeEventListener(CONSENT_EVENT, sync);
  }, []);

  const choose = (value: Exclude<Consent, null>) => {
    window.localStorage.setItem(CONSENT_KEY, value);
    setConsent(value);
    window.dispatchEvent(new Event(CONSENT_EVENT));
  };

  return { consent, choose };
}

export function trackAnalytics(
  event: string,
  parameters: Record<string, string | number | boolean> = {},
) {
  if (
    typeof window === "undefined"
    || window.localStorage.getItem(CONSENT_KEY) !== "granted"
  ) {
    return;
  }
  window.gtag?.("event", event, parameters);
}

export function CheckoutAnalytics({
  product,
  checkoutId,
}: {
  product: string;
  checkoutId: string;
}) {
  useEffect(() => {
    const storageKey = `godfin_checkout_tracked_${checkoutId}`;
    if (window.sessionStorage.getItem(storageKey)) return;
    const timer = window.setTimeout(
      () => {
        trackAnalytics("purchase", { product_code: product });
        window.sessionStorage.setItem(storageKey, "true");
      },
      800,
    );
    return () => window.clearTimeout(timer);
  }, [checkoutId, product]);
  return null;
}

export function PrivacyAnalytics({ nonce }: { nonce?: string }) {
  const measurementId = process.env.NEXT_PUBLIC_GA_ID;
  const { consent, choose } = useAnalyticsConsent();

  if (!measurementId || !/^G-[A-Z0-9]{6,20}$/.test(measurementId)) return null;

  return (
    <>
      {consent === "granted" && (
        <>
          <Script
            src={`https://www.googletagmanager.com/gtag/js?id=${measurementId}`}
            strategy="afterInteractive"
            nonce={nonce}
          />
          <Script id="godfin-analytics" strategy="afterInteractive" nonce={nonce}>
            {`
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', '${measurementId}', {
                anonymize_ip: true,
                allow_google_signals: false,
                allow_ad_personalization_signals: false
              });
            `}
          </Script>
        </>
      )}
      {consent === null && (
        <aside className="consent-banner" aria-label="Analytics choice">
          <div>
            <strong>Private by default</strong>
            <p>
              With your permission, Google Analytics can receive website page,
              device, approximate-region, referrer, campaign, and interaction
              information. Desktop financial data is never included.
            </p>
          </div>
          <div className="consent-actions">
            <button className="button-ghost" onClick={() => choose("denied")}>
              No analytics
            </button>
            <button className="button" onClick={() => choose("granted")}>
              Allow site analytics
            </button>
          </div>
        </aside>
      )}
    </>
  );
}

export function AnalyticsPreferences() {
  const measurementId = process.env.NEXT_PUBLIC_GA_ID;
  const { consent, choose } = useAnalyticsConsent();

  if (!measurementId) {
    return <p>Website analytics are not configured in this environment.</p>;
  }

  return (
    <div className="consent-preferences">
      <p>
        Current choice: <strong>{consent || "not chosen"}</strong>. You can
        change it at any time on this device.
      </p>
      <div className="consent-actions">
        <button className="button-ghost" onClick={() => choose("denied")}>
          Disable analytics
        </button>
        <button className="button" onClick={() => choose("granted")}>
          Allow site analytics
        </button>
      </div>
    </div>
  );
}
