"use client";

import { LogIn, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function SignInButton({ next = "/account" }: { next?: string }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function signIn() {
    const supabase = createSupabaseBrowserClient();
    if (!supabase) {
      setError("Website sign-in is not configured yet.");
      return;
    }
    setPending(true);
    const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo },
    });
    if (authError) {
      setError(authError.message);
      setPending(false);
    }
  }

  return (
    <>
      <button className="button" disabled={pending} onClick={signIn} type="button">
        <LogIn size={17} />
        {pending ? "Opening Google…" : "Continue with Google"}
      </button>
      {error ? <p style={{ color: "#9c352d", marginTop: 12 }}>{error}</p> : null}
    </>
  );
}

export function SignOutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function signOut() {
    setPending(true);
    const supabase = createSupabaseBrowserClient();
    await supabase?.auth.signOut();
    router.refresh();
    setPending(false);
  }

  return (
    <button className="button-secondary" disabled={pending} onClick={signOut}>
      <LogOut size={16} /> {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
