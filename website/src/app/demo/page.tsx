import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Try the demo",
  description: "Click through the exact GODFIN desktop interface with a made-up household and no bank connection.",
};

export default function DemoPage() {
  redirect("/demo-app/index.html");
}
