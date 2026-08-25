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
  if (typeof navigator === "undefined") return "IN";
  const locale = Intl.DateTimeFormat().resolvedOptions().locale;
  const country = locale.split("-")[1]?.toUpperCase();
  return country && /^[A-Z]{2}$/.test(country) ? country : "IN";
}

export function WaitlistForm({ enabled = true }: { enabled?: boolean }) {
  const searchParams = useSearchParams();
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");
  const [country, setCountry] = useState("IN");
  const [os, setOs] = useState("other");

  useEffect(() => {
    setCountry(detectedCountry());
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
    setState("sending");
    setMessage("");
    const form = new FormData(event.currentTarget);
    const params = new URLSearchParams(window.location.search);
    try {
      const response = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.get("email"),
          country,
          os,
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
      event.currentTarget.reset();
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
      <div className="waitlist-grid">
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required disabled={!enabled} />
        </label>
        <label>
          Country
          <input
            aria-label="Country code"
            maxLength={2}
            pattern="[A-Za-z]{2}"
            required
            disabled={!enabled}
            value={country}
            onChange={(event) => setCountry(event.target.value.toUpperCase())}
          />
        </label>
        <label>
          Computer
          <select disabled={!enabled} value={os} onChange={(event) => setOs(event.target.value)}>
            <option value="macos">macOS</option>
            <option value="windows">Windows</option>
            <option value="linux">Linux</option>
            <option value="other">Other</option>
          </select>
        </label>
      </div>
      <label>
        What would you use GODFIN for?
        <textarea
          name="intended_use"
          maxLength={500}
          placeholder="For example: understand family spending without uploading statements to a cloud service."
          required
          disabled={!enabled}
          rows={3}
        />
      </label>
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
        {state === "sending" ? "Sending confirmation…" : "Join the waitlist"}
      </button>
      {message ? (
        <p className={state === "error" ? "form-message error" : "form-message"} role="status">
          {message}
        </p>
      ) : null}
    </form>
  );
}
