"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SignInButton } from "@/components/auth-controls";

type State = "checking" | "signin" | "error";

export function BetaInviteAccept() {
  const router = useRouter();
  const [state, setState] = useState<State>("checking");
  const [message, setMessage] = useState("Checking your one-time invitation…");

  useEffect(() => {
    let cancelled = false;
    async function run() {
      const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const token = hash.get("token");
      if (token) {
        window.history.replaceState(null, "", "/beta/accept");
        const claim = await fetch("/api/beta/invite/claim", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!claim.ok) {
          const result = await claim.json();
          throw new Error(result.message || "Invitation is invalid or expired.");
        }
      }

      const accept = await fetch("/api/beta/invite/accept", { method: "POST" });
      if (accept.status === 401) {
        if (!cancelled) {
          setState("signin");
          setMessage("Continue with the same Google email address that received the invitation.");
        }
        return;
      }
      const result = await accept.json();
      if (!accept.ok) throw new Error(result.message || "Invitation could not be accepted.");
      router.replace("/beta");
      router.refresh();
    }
    run().catch((error) => {
      if (!cancelled) {
        setState("error");
        setMessage(error instanceof Error ? error.message : "Invitation could not be accepted.");
      }
    });
    return () => { cancelled = true; };
  }, [router]);

  return (
    <div className="account-card narrow">
      <h2>{state === "signin" ? "Match your invited email" : "Private beta invitation"}</h2>
      <p className={state === "error" ? "form-message error" : "lead"} role="status">
        {message}
      </p>
      {state === "signin" ? <SignInButton next="/beta/accept" /> : null}
    </div>
  );
}
