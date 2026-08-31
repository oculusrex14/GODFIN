import type { Metadata } from "next";
import { PublicDemo } from "@/components/public-demo";

export const metadata: Metadata = {
  title: "Try the demo",
  description: "Click through a made-up GODFIN household with no account, upload, or bank connection.",
};

export default function DemoPage() {
  return (
    <section className="demo-fullscreen-route" aria-label="GODFIN sample household demo">
      <PublicDemo />
    </section>
  );
}
