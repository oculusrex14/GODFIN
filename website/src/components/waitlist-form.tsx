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
          email: form.get("email"),
          locale_country: localeCountry,
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
      <div className="waitlist-grid">
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required disabled={!enabled} />
        </label>
        <label>
          Computer
          <select disabled={!enabled} value={os} onChange={(event) => setOs(event.target.value)}>
            <option value="macos">Apple Silicon Mac</option>
            <option value="windows">Windows x64</option>
            <option value="linux">Linux / Other</option>
            <option value="other">Another computer</option>
          </select>
        </label>
      </div>
      <label>
        What do you want to understand?
        <textarea
          name="intended_use"
          maxLength={500}
          placeholder="For example: where my money went each month, or which bills keep repeating."
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
