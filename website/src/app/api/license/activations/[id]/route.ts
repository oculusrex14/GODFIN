import { NextResponse } from "next/server";

import { createAdminClient } from "@/lib/supabase/admin";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { user },
    } = (await supabase?.auth.getUser()) || { data: { user: null } };
    if (!user) {
      return NextResponse.json({ message: "Sign in required." }, { status: 401 });
    }

    const { id } = await context.params;
    if (!/^[0-9a-f-]{36}$/i.test(id)) {
      return NextResponse.json({ message: "Invalid device." }, { status: 400 });
    }

    const admin = createAdminClient();
    const { data: activation, error: activationError } = await admin
      .from("license_activations")
      .select("id,license_id,deactivated_at")
      .eq("id", id)
      .maybeSingle();
    if (activationError) throw activationError;
    if (!activation) {
      return NextResponse.json({ message: "Device not found." }, { status: 404 });
    }
    const { data: license, error: licenseError } = await admin
      .from("licenses")
      .select("id")
      .eq("id", activation.license_id)
      .eq("user_id", user.id)
      .maybeSingle();
    if (licenseError) throw licenseError;
    if (!license) {
      return NextResponse.json({ message: "Device not found." }, { status: 404 });
    }

    const { error: updateError } = await admin
      .from("license_activations")
      .update({ deactivated_at: new Date().toISOString() })
      .eq("id", activation.id);
    if (updateError) throw updateError;
    return NextResponse.json({ deactivated: true });
  } catch (error) {
    console.error("Device deactivation failed", error);
    return NextResponse.json(
      { message: "The device could not be deactivated." },
      { status: 500 },
    );
  }
}
