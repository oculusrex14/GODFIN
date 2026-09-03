"use client";

import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

type State = "idle" | "sending" | "sent" | "confirmed" | "error";

function detectedOs(): string {
  if (typeof navigator === "undefined") return "other";
  const value = navigator.userAgent.toLowerCase();
  if (value.includes("mac")) return "macos";
  if (value.includes("win")) return "windows";
  if (value.includes("linux")) return "linux";
  return "other";
}

function detectedCountry(): string {
  if (typeof navigator === "undefined") return "";
  const locale = Intl.DateTimeFormat().resolvedOptions().locale;
  const country = locale.split("-")[1]?.toUpperCase();
  return country && /^[A-Z]{2}$/.test(country) ? country : "";
}

export function WaitlistForm({ enabled = true }: { enabled?: boolean }) {
  const searchParams = useSearchParams();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");
  const [localeCountry, setLocaleCountry] = useState("");
  const [os, setOs] = useState("other");

  useEffect(() => {
    setLocaleCountry(detectedCountry());
    setOs(detectedOs());
    const result = searchParams.get("waitlist");
    if (result === "confirmed") {
      setState("confirmed");
      setMessage("You’re confirmed. We’ll only send meaningful GODFIN updates.");
    } else if (result === "expired") {
      setState("error");
      setMessage("That confirmation link expired. Submit the form again for a fresh link.");
    } else if (result === "invalid") {
      setState("error");
      setMessage("That confirmation link is invalid. Submit the form again.");
    }
  }, [searchParams]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setState("sending");
    setMessage("");
    const form = new FormData(formElement);
    const params = new URLSearchParams(window.location.search);
    try {
      const response = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          locale_country: localeCountry,
          os,
          occupation: form.get("occupation"),
          bank_count: form.get("bank_count"),
          banks: form.get("banks"),
          intended_use: form.get("intended_use"),
          consent: form.get("consent") === "on",
          company: form.get("company"),
          attribution: {
            source: params.get("utm_source") || "",
            medium: params.get("utm_medium") || "",
            campaign: params.get("utm_campaign") || "",
            content: params.get("utm_content") || "",
            referrer: document.referrer,
          },
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message || "Could not join the waitlist.");
      setState(body.already_confirmed ? "confirmed" : "sent");
      setMessage(
        body.already_confirmed
          ? "You’re already confirmed."
          : "Check your inbox and confirm your place. The link expires in 24 hours.",
      );
      formElement.reset();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Could not join the waitlist.");
    }
  }

  return (
    <form className="waitlist-form" onSubmit={submit}>
      {!enabled ? (
        <p className="form-message" role="status">
          Confirmation email setup is being finalized. The form will open as
          soon as the private launch mailbox is verified.
        </p>
      ) : null}
      <div className="waitlist-grid waitlist-grid-primary">
        <label htmlFor="waitlist-name">
          Name
          <input
            autoComplete="name"
            disabled={!enabled}
            id="waitlist-name"
            maxLength={100}
            name="name"
            required
          />
        </label>
        <label htmlFor="waitlist-email">
          Email
          <input
            autoComplete="email"
            disabled={!enabled}
            id="waitlist-email"
            name="email"
            required
            type="email"
          />
        </label>
        <label htmlFor="waitlist-computer">
          System
          <select
            disabled={!enabled}
            id="waitlist-computer"
            name="os"
            value={os}
            onChange={(event) => setOs(event.target.value)}
          >
            <option value="macos">Apple Silicon Mac</option>
            <option value="windows">Windows x64</option>
            <option value="linux">Linux / Other</option>
            <option value="other">Another computer</option>
          </select>
        </label>
      </div>
      <div className="waitlist-grid waitlist-grid-secondary">
        <label htmlFor="waitlist-occupation">
          Occupation <span className="optional-label">Optional</span>
          <input
            autoComplete="organization-title"
            disabled={!enabled}
            id="waitlist-occupation"
            maxLength={120}
            name="occupation"
            placeholder="For example: student, designer, teacher"
          />
        </label>
        <label htmlFor="waitlist-bank-count">
          How many banks do you use? <span className="optional-label">Optional</span>
          <input
            disabled={!enabled}
            id="waitlist-bank-count"
            inputMode="numeric"
            max={25}
            min={0}
            name="bank_count"
            placeholder="For example: 2"
            type="number"
          />
        </label>
      </div>
      <label htmlFor="waitlist-banks">
        Which banks do you use? <span className="optional-label">Optional</span>
        <input
          aria-describedby="waitlist-sensitive-note"
          disabled={!enabled}
          id="waitlist-banks"
          maxLength={600}
          name="banks"
          placeholder="For example: HDFC Bank, SBI"
        />
      </label>
      <label htmlFor="waitlist-context">
        Tell us about yourself and what you want help with <span className="optional-label">Optional</span>
        <textarea
          aria-describedby="waitlist-selection-note waitlist-sensitive-note"
          id="waitlist-context"
          name="intended_use"
          maxLength={1000}
          placeholder="Share your money-management struggles, what you hope GODFIN can help with, or how you would like to help test the project."
          disabled={!enabled}
          rows={4}
        />
      </label>
      <p className="waitlist-selection-note" id="waitlist-selection-note">
        Optional details help us choose testers whose needs match the current beta and show genuine interest in participating.
      </p>
      <p className="waitlist-sensitive-note" id="waitlist-sensitive-note">
        Bank names only. Never share account numbers, statements, balances, UPI addresses, PINs, passwords, keys, or Gmail content.
      </p>
      <label className="honeypot" aria-hidden="true">
        Company
        <input name="company" tabIndex={-1} autoComplete="off" />
      </label>
      <label className="consent-row">
        <input name="consent" type="checkbox" required disabled={!enabled} />
        <span>
          Email me product and launch updates. I can unsubscribe at any time.
          This consent is separate from any future data-sharing program.
        </span>
      </label>
      <button className="button" disabled={!enabled || state === "sending"} type="submit">
        {state === "sending" ? "Sending confirmation…" : "Join the early testers"}
      </button>
      {message ? (
        <p className={state === "error" ? "form-message error" : "form-message"} role="status">
          {message}
        </p>
      ) : null}
    </form>
  );
}
