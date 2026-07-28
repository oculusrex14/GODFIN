import { createClient } from "@supabase/supabase-js";

import { serverEnv, supabasePublicConfig } from "@/lib/env";

export function createAdminClient() {
  const config = supabasePublicConfig();
  if (!config) {
    throw new Error("Supabase public configuration is missing.");
  }
  return createClient(config.url, serverEnv.supabaseServiceRoleKey(), {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
}
