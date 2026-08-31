"use client";

import { useEffect, useRef, useState } from "react";

export function ProductDemoVideo() {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [motionAllowed, setMotionAllowed] = useState(false);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setMotionAllowed(!preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const target = wrapperRef.current;
    if (!target) return;
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      { rootMargin: "180px", threshold: 0.2 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !motionAllowed || !inView) {
      video?.pause();
      return;
    }
    void video.play().catch(() => undefined);
  }, [inView, motionAllowed]);

  return (
    <div className="story-video-wrap" ref={wrapperRef}>
      <video
        aria-describedby="hero-video-transcript"
        aria-label="Silent GODFIN product walkthrough using one made-up household"
        autoPlay={motionAllowed && inView}
        controls
        height={1080}
        loop
        muted
        playsInline
        poster="/video/godfin-beta-hero.poster.webp"
        preload={inView ? "metadata" : "none"}
        ref={videoRef}
        width={1920}
      >
        {inView || !motionAllowed ? (
          <>
            <source src="/video/godfin-beta-hero.webm" type="video/webm" />
            <source src="/video/godfin-beta-hero.mp4" type="video/mp4" />
            <track default kind="captions" label="English scene text" src="/video/godfin-beta-hero.en.vtt" srcLang="en" />
          </>
        ) : null}
      </video>
      <details className="story-video-transcript" id="hero-video-transcript">
        <summary>Read the 24-second video transcript</summary>
        <ol>
          <li>Meet the exact GODFIN desktop app using a made-up household.</li>
          <li>Preview a supported statement in the real Upload screen.</li>
          <li>See the real Dashboard, Transactions, and Review pages.</li>
          <li>Open goals and recurring commitments in the real Plan pages.</li>
          <li>Read reports and money-habit explanations from synthetic data.</li>
          <li>Explore every real app tab at godfin.dev/demo.</li>
        </ol>
      </details>
    </div>
  );
}
