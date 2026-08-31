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
          <li>A clearer month, without moving your money life online.</li>
          <li>Preview a supported statement before reconciling it.</li>
          <li>See verified money in, included spending, and what was left.</li>
          <li>Correct a category and keep the reason visible.</li>
          <li>Review regular commitments and explainable goal progress.</li>
          <li>Try the made-up household at godfin.dev/demo.</li>
        </ol>
      </details>
    </div>
  );
}
