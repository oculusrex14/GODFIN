"use client";

import { FormEvent, useState } from "react";

type State = "idle" | "saving" | "saved" | "error";

export function BetaFeedbackForm() {
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setState("saving");
    setMessage("");
    const form = new FormData(formElement);
    try {
      const response = await fetch("/api/beta/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: form.get("category"),
          feature_screen: form.get("feature_screen"),
          happened: form.get("happened"),
          expected: form.get("expected"),
          reproduction_steps: form.get("reproduction_steps"),
          severity: form.get("severity"),
          may_contact: form.get("may_contact") === "on",
          app_version: form.get("app_version"),
          platform: form.get("platform"),
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || "Could not save feedback.");
      formElement.reset();
      setState("saved");
      setMessage("Feedback saved. Thank you for keeping it specific and privacy-safe.");
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : "Could not save feedback.");
    }
  }

  return (
    <form className="waitlist-form" onSubmit={submit}>
      <div className="notice error-notice">
        Do not paste account numbers, balances, statement rows, PINs, license keys,
        tokens, email contents, or personal financial details. File uploads are disabled.
      </div>
      <div className="form-two-column">
        <label>
          Category
          <select name="category" required defaultValue="">
            <option value="" disabled>Choose one</option>
            <option value="bug">Bug</option>
            <option value="ux">User experience</option>
            <option value="parser">Statement parser</option>
            <option value="performance">Performance</option>
            <option value="feature">Feature</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          How serious was it for you?
          <select name="severity" required defaultValue="medium">
            <option value="low">Small inconvenience</option>
            <option value="medium">Slowed me down</option>
            <option value="high">Could not finish the task</option>
            <option value="blocking">Could not use the beta</option>
          </select>
        </label>
      </div>
      <label>
        Feature or screen
        <input name="feature_screen" minLength={2} maxLength={100} required />
      </label>
      <label>
        What happened?
        <textarea name="happened" minLength={10} maxLength={2000} rows={5} required />
      </label>
      <label>
        What did you expect?
        <textarea name="expected" minLength={10} maxLength={2000} rows={4} required />
      </label>
      <label>
        Steps to reproduce (optional)
        <textarea name="reproduction_steps" maxLength={3000} rows={5} />
      </label>
      <div className="form-two-column">
        <label>
          App version (optional)
          <input name="app_version" maxLength={64} />
        </label>
        <label>
          Computer (optional)
          <input name="platform" maxLength={100} placeholder="Apple Silicon Mac or Windows x64" />
        </label>
      </div>
      <label className="choice-row">
        <input name="may_contact" type="checkbox" />
        <span>GODFIN may contact me about this feedback.</span>
      </label>
      <button className="button" disabled={state === "saving"} type="submit">
        {state === "saving" ? "Saving feedback…" : "Send privacy-safe feedback"}
      </button>
      {message ? (
        <p className={state === "error" ? "form-message error" : "form-message"} role="status">
          {message}
        </p>
      ) : null}
    </form>
  );
}
