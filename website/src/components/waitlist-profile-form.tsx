"use client";

import { FormEvent, useState } from "react";

type FormState = "idle" | "saving" | "saved" | "error";

const bankOptions = [
  ["hdfc", "HDFC statement"],
  ["sbi", "SBI relationship statement"],
  ["kotak", "Kotak savings statement"],
  ["other", "Another bank"],
  ["not_sure", "Not sure yet"],
] as const;

const useOptions = [
  ["spending", "See where money went"],
  ["cash_flow", "Understand income and cash flow"],
  ["recurring", "Find repeating bills"],
  ["goals", "Track a savings goal"],
  ["reports", "Prepare a review pack"],
  ["privacy", "Keep a finance ledger on my computer"],
] as const;

export function WaitlistProfileForm() {
  const [state, setState] = useState<FormState>("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("saving");
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/waitlist/profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          banks: form.getAll("banks"),
          primary_use: form.getAll("primary_use"),
          gmail_test_interest: form.get("gmail_test_interest") === "on",
          feedback_commitment: form.get("feedback_commitment") === "on",
          platform_detail: form.get("platform_detail"),
          additional_context: form.get("additional_context"),
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Could not save your profile.");
      setState("saved");
      setMessage("Thanks. Your optional tester profile is saved.");
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Could not save your profile.");
    }
  }

  if (state === "saved") {
    return <p className="form-message" role="status">{message}</p>;
  }

  return (
    <form className="waitlist-form" onSubmit={submit}>
      <fieldset>
        <legend>Which statement formats could you test? (optional)</legend>
        <div className="choice-grid">
          {bankOptions.map(([value, label]) => (
            <label className="choice-row" key={value}>
              <input name="banks" type="checkbox" value={value} />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset>
        <legend>What would you most like to understand? (optional)</legend>
        <div className="choice-grid">
          {useOptions.map(([value, label]) => (
            <label className="choice-row" key={value}>
              <input name="primary_use" type="checkbox" value={value} />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label>
        Your computer details (optional)
        <input name="platform_detail" maxLength={160} placeholder="For example: Mac mini M2, or Windows 11 laptop" />
      </label>
      <label className="choice-row">
        <input name="gmail_test_interest" type="checkbox" />
        <span>I may test the separate read-only Gmail import flow.</span>
      </label>
      <label className="choice-row">
        <input name="feedback_commitment" type="checkbox" />
        <span>I can share short weekly product feedback.</span>
      </label>
      <label>
        Anything else that would help us choose a useful mix of testers? (optional)
        <textarea name="additional_context" maxLength={1000} rows={4} />
      </label>
      <p className="form-privacy-note">
        Do not paste bank statements, account or card numbers, balances, UPI IDs,
        PINs, Gmail contents, tokens, or license keys.
      </p>
      <button className="button" disabled={state === "saving"} type="submit">
        {state === "saving" ? "Saving…" : "Save optional profile"}
      </button>
      {message ? (
        <p className={state === "error" ? "form-message error" : "form-message"} role="status">
          {message}
        </p>
      ) : null}
    </form>
  );
}
