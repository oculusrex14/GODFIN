import { NextResponse } from "next/server";

import { checkRateLimit, rateLimitResponse } from "@/lib/abuse-control";
import { cleanText, containsSensitiveFeedback } from "@/lib/beta";
import { betaPortalState } from "@/lib/beta-access";
import { createAdminClient } from "@/lib/supabase/admin";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

const CATEGORIES = new Set(["bug", "ux", "parser", "performance", "feature", "other"]);
const SEVERITIES = new Set(["low", "medium", "high", "blocking"]);

export async function POST(request: Request) {
  try {
    if (request.headers.get("content-type")?.includes("multipart/form-data")) {
      return NextResponse.json({ message: "File uploads are not accepted." }, { status: 415 });
    }
    const addressLimit = await checkRateLimit(request, {
      bucket: "beta-feedback:address",
      limit: 20,
      windowSeconds: 60 * 60,
    });
    if (!addressLimit.allowed) return rateLimitResponse(addressLimit);
    const supabase = await createSupabaseServerClient();
    const { data: { user } } = (await supabase?.auth.getUser()) || { data: { user: null } };
    if (!user) return NextResponse.json({ message: "Sign in to share beta feedback." }, { status: 401 });
    const userLimit = await checkRateLimit(request, {
      bucket: "beta-feedback:user",
      limit: 10,
      windowSeconds: 24 * 60 * 60,
      subject: `user:${user.id}`,
    });
    if (!userLimit.allowed) return rateLimitResponse(userLimit);
    const tester = await betaPortalState(user.id);
    if (!tester || tester.status !== "active") {
      return NextResponse.json({ message: "Active beta access is required." }, { status: 403 });
    }
    const body = (await request.json()) as Record<string, unknown>;
    const category = cleanText(body.category, 24).toLowerCase();
    const featureScreen = cleanText(body.feature_screen, 100);
    const happened = cleanText(body.happened, 2000);
    const expected = cleanText(body.expected, 2000);
    const reproductionSteps = cleanText(body.reproduction_steps, 3000);
    const severity = cleanText(body.severity, 24).toLowerCase();
    const appVersion = cleanText(body.app_version, 64);
    const platform = cleanText(body.platform, 100);
    const combined = [featureScreen, happened, expected, reproductionSteps].join("\n");
    if (
      !CATEGORIES.has(category) ||
      !SEVERITIES.has(severity) ||
      featureScreen.length < 2 ||
      happened.length < 10 ||
      expected.length < 10
    ) {
      return NextResponse.json({ message: "Complete the required feedback fields." }, { status: 400 });
    }
    if (containsSensitiveFeedback(combined)) {
      return NextResponse.json(
        { message: "Remove account details, email addresses, long numbers, PINs, tokens, or license keys." },
        { status: 400 },
      );
    }
    const admin = createAdminClient();
    const { error } = await admin.from("beta_feedback").insert({
      beta_tester_id: tester.id,
      user_id: user.id,
      category,
      feature_screen: featureScreen,
      happened,
      expected,
      reproduction_steps: reproductionSteps || null,
      severity,
      may_contact: body.may_contact === true,
      app_version: appVersion || null,
      platform: platform || null,
    });
    if (error) throw error;
    return NextResponse.json({ saved: true }, { status: 201 });
  } catch (error) {
    console.error("Beta feedback submission failed", {
      errorType: error instanceof Error ? error.name : "UnknownError",
    });
    return NextResponse.json({ message: "Feedback could not be saved right now." }, { status: 503 });
  }
}
