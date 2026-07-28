import Stripe from "stripe";

import { serverEnv } from "@/lib/env";

let stripeClient: Stripe | null = null;

export function stripe(): Stripe {
  if (!stripeClient) {
    stripeClient = new Stripe(serverEnv.stripeSecretKey());
  }
  return stripeClient;
}
