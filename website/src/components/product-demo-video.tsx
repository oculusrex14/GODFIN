"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

export function ProductDemoVideo() {
  const [motionAllowed, setMotionAllowed] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setMotionAllowed(!preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  if (!motionAllowed) {
    return (
      <Image
        src="/screenshots/import.png"
        width={1244}
        height={716}
        alt="GODFIN statement import screen using privacy-safe synthetic data"
      />
    );
  }

  return (
    <video
      autoPlay
      loop
      muted
      playsInline
      poster="/screenshots/import.png"
      preload="metadata"
      aria-label="Short screen recording of a privacy-safe GODFIN import workflow"
    >
      <source src="/demo/godfin-workflow.webm" type="video/webm" />
      <source src="/demo/godfin-workflow.mp4" type="video/mp4" />
    </video>
  );
}
