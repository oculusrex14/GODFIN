import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { supabasePublicConfig } from "@/lib/env";

function contentSecurityPolicy(
  nonce: string,
  upgradeInsecureRequests: boolean,
): string {
  const development = process.env.NODE_ENV === "development";
  const directives = [
    "default-src 'self'",
    "base-uri 'none'",
    `connect-src 'self'${development ? " ws: wss:" : ""} https://*.supabase.co https://sdk.cashfree.com https://sandbox.cashfree.com https://api.cashfree.com https://payments.cashfree.com https://payments-test.cashfree.com https://www.google-analytics.com https://region1.google-analytics.com`,
    "font-src 'self' data:",
    "form-action 'self' https://payments.cashfree.com https://payments-test.cashfree.com",
    "frame-ancestors 'none'",
    "frame-src https://payments.cashfree.com https://payments-test.cashfree.com https://accounts.google.com",
    "img-src 'self' data: blob: https://www.google-analytics.com",
    "manifest-src 'self'",
    "media-src 'self'",
    "object-src 'none'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    `style-src-elem 'self' 'nonce-${nonce}'`,
    "style-src-attr 'unsafe-hashes' 'sha256-zlqnbDt84zf1iSefLU/ImC54isoprH/MRiVZGskwexk='",
  ];
  if (upgradeInsecureRequests) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export async function middleware(request: NextRequest) {
  const nonce = crypto.randomUUID().replaceAll("-", "");
  const forwardedProtocol = request.headers
    .get("x-forwarded-proto")
    ?.split(",", 1)[0]
    ?.trim();
  const secureTransport = forwardedProtocol
    ? forwardedProtocol === "https"
    : request.nextUrl.protocol === "https:";
  const csp = contentSecurityPolicy(nonce, secureTransport);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const securedResponse = () => {
    const next = NextResponse.next({ request: { headers: requestHeaders } });
    next.headers.set("Content-Security-Policy", csp);
    return next;
  };

  const config = supabasePublicConfig();
  if (!config) return securedResponse();

  let response = securedResponse();
  const supabase = createServerClient(config.url, config.key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll(cookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = securedResponse();
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  await supabase.auth.getUser();
  return response;
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
