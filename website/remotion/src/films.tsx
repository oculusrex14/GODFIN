import type { CSSProperties, ReactNode } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const colors = {
  ink: "#07131f",
  navy: "#102c46",
  teal: "#54e1d0",
  lime: "#c9f36b",
  white: "#f6f7f3",
};

const disclosure = "Real GODFIN interface · made-up household · no bank connection";

function useSceneMotion(duration: number) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 20, stiffness: 92 } });
  const opacity = interpolate(frame, [0, 12, duration - 12, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return { enter, opacity };
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: compact ? 13 : 20 }}>
      <Img
        src={staticFile("assets/godfin-vault-dial.png")}
        style={{ width: compact ? 49 : 78, height: compact ? 49 : 78, objectFit: "contain" }}
      />
      <div>
        <strong style={{ color: colors.white, fontSize: compact ? 26 : 42, letterSpacing: "0.04em" }}>
          GOD<span style={{ color: colors.lime }}>FIN</span>
        </strong>
        <small style={{ display: "block", marginTop: 3, color: "rgba(255,255,255,.4)", fontSize: compact ? 8 : 11, letterSpacing: "0.18em", textTransform: "uppercase" }}>
          Local-first. Private. In control.
        </small>
      </div>
    </div>
  );
}

function FilmFrame({ children }: { children: ReactNode }) {
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: colors.ink, color: colors.white, fontFamily: "GODFIN Sans, Arial, sans-serif" }}>
      <style>{`@font-face{font-family:'GODFIN Sans';src:url('${staticFile("assets/geist-latin.woff2")}') format('woff2');font-weight:100 900;font-style:normal}`}</style>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 84% 10%, rgba(84,225,208,.18), transparent 34%)" }} />
      {children}
      <div style={{ position: "absolute", right: 42, bottom: 18, left: 42, display: "flex", justifyContent: "center", gap: 9, color: "rgba(255,255,255,.56)", fontSize: 15, letterSpacing: "0.02em" }}>
        <span style={{ width: 8, height: 8, marginTop: 5, borderRadius: "50%", background: colors.lime }} />
        {disclosure}
      </div>
    </AbsoluteFill>
  );
}

function IntroScene({ duration, social = false }: { duration: number; social?: boolean }) {
  const { enter, opacity } = useSceneMotion(duration);
  return (
    <FilmFrame>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: social ? 76 : 120, textAlign: "center", opacity, transform: `translateY(${(1 - enter) * 34}px)` }}>
        <div>
          <div style={{ display: "flex", justifyContent: "center" }}><Brand /></div>
          <h1 style={{ maxWidth: social ? 900 : 1450, margin: social ? "92px auto 28px" : "64px auto 30px", fontSize: social ? 126 : 124, lineHeight: 0.95, letterSpacing: "-0.07em" }}>
            {social ? "Your money. Your laptop." : "The real GODFIN app, filled only with made-up data."}
          </h1>
          <p style={{ color: "rgba(255,255,255,.6)", fontSize: social ? 34 : 30 }}>
            Every screen in this film is the actual desktop interface.
          </p>
        </div>
      </div>
    </FilmFrame>
  );
}

type AppSceneProps = {
  body: string;
  duration: number;
  image: string;
  label: string;
  objectPosition?: string;
  social?: boolean;
  title: string;
};

function AppScene({ body, duration, image, label, objectPosition = "top left", social = false, title }: AppSceneProps) {
  const frame = useCurrentFrame();
  const { enter, opacity } = useSceneMotion(duration);
  const drift = interpolate(frame, [0, duration], [1.015, 1.035], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const screenStyle: CSSProperties = social
    ? { position: "absolute", top: 620, left: 62, width: 956, height: 930, objectFit: "cover", objectPosition }
    : { position: "absolute", top: 184, left: 84, width: 1752, height: 808, objectFit: "cover", objectPosition };

  return (
    <FilmFrame>
      <div style={{ position: "absolute", top: social ? 64 : 38, left: social ? 54 : 66, zIndex: 2 }}><Brand compact /></div>
      <div style={{ position: "absolute", zIndex: 2, top: social ? 244 : 42, right: social ? 54 : 72, left: social ? 54 : 550, textAlign: social ? "left" : "right", opacity, transform: `translateY(${(1 - enter) * 18}px)` }}>
        <div style={{ color: colors.lime, fontSize: social ? 21 : 18, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase" }}>{label}</div>
        <h1 style={{ margin: "9px 0 6px", fontSize: social ? 66 : 47, lineHeight: 1, letterSpacing: "-0.045em" }}>{title}</h1>
        <p style={{ margin: 0, color: "rgba(255,255,255,.62)", fontSize: social ? 25 : 19, lineHeight: 1.35 }}>{body}</p>
      </div>
      <div style={{ ...screenStyle, overflow: "hidden", border: "1px solid rgba(255,255,255,.2)", borderRadius: social ? 30 : 22, background: colors.navy, boxShadow: "0 34px 90px rgba(0,0,0,.36)", opacity, transform: `scale(${drift})` }}>
        <div style={{ position: "absolute", zIndex: 2, top: 0, right: 0, left: 0, height: 24, borderBottom: "1px solid rgba(255,255,255,.08)", background: "rgba(3,12,21,.92)" }}>
          <span style={{ position: "absolute", top: 8, left: 12, width: 7, height: 7, borderRadius: "50%", background: "#ff6b62", boxShadow: "14px 0 #ffcb48, 28px 0 #50c878" }} />
        </div>
        <Img src={staticFile(`assets/captures/${image}`)} style={{ width: "100%", height: "100%", paddingTop: 24, objectFit: "cover", objectPosition }} />
      </div>
    </FilmFrame>
  );
}

function CopyScene({ duration, line, accent, social = false }: { duration: number; line: string; accent?: string; social?: boolean }) {
  const { enter, opacity } = useSceneMotion(duration);
  return (
    <FilmFrame>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: social ? "170px 74px" : "130px 120px", textAlign: "center", opacity, transform: `translateY(${(1 - enter) * 30}px)` }}>
        <div>
          <h1 style={{ margin: 0, fontSize: social ? 128 : 112, lineHeight: 0.95, letterSpacing: "-0.07em" }}>{line}</h1>
          {accent ? <p style={{ marginTop: 34, color: colors.lime, fontSize: social ? 37 : 30 }}>{accent}</p> : null}
        </div>
      </div>
    </FilmFrame>
  );
}

export function HeroFilm() {
  return (
    <AbsoluteFill>
      <Audio src={staticFile("assets/audio/godfin-beta-hero-narration.wav")} volume={0.94} />
      <Sequence from={0} durationInFrames={90}><IntroScene duration={90} /></Sequence>
      <Sequence from={90} durationInFrames={120}><AppScene duration={120} image="upload.png" label="Upload" title="Preview before you reconcile." body="The real statement-import page shows what GODFIN found before rows enter the local ledger." /></Sequence>
      <Sequence from={210} durationInFrames={150}><AppScene duration={150} image="dashboard.png" label="Dashboard" title="See the month in one place." body="₹44,000 in, ₹11,000 spent, and a 75% savings rate—from synthetic data." /></Sequence>
      <Sequence from={360} durationInFrames={60}><AppScene duration={60} image="transactions.png" label="Transactions" title="Keep every row inspectable." body="Search, filter, and review the explanation behind each category." /></Sequence>
      <Sequence from={420} durationInFrames={60}><AppScene duration={60} image="review.png" label="Review" title="Correct only what needs you." body="Made-up uncertain rows stay visible instead of being guessed away." /></Sequence>
      <Sequence from={480} durationInFrames={75}><AppScene duration={75} image="subscriptions.png" label="Subscriptions" title="Notice recurring commitments." body="The actual app shows the monthly weight and the evidence behind detection." /></Sequence>
      <Sequence from={555} durationInFrames={38}><AppScene duration={38} image="budget.png" label="Budget & goals" title="Move a goal forward." body="Manual contributions and a full history keep progress explainable." /></Sequence>
      <Sequence from={593} durationInFrames={37}><AppScene duration={37} image="reports.png" label="Reports" title="Read the verified story." body="Reports remain grounded in local calculations and visible caveats." /></Sequence>
      <Sequence from={630} durationInFrames={90}><CopyScene duration={90} line="Explore every real tab at godfin.dev/demo" accent="Early desktop testers wanted." /></Sequence>
    </AbsoluteFill>
  );
}

export function WalkthroughFilm() {
  return (
    <AbsoluteFill>
      <Sequence from={0} durationInFrames={120}><IntroScene duration={120} /></Sequence>
      <Sequence from={120} durationInFrames={120}><CopyScene duration={120} line="One made-up household. Fifteen real app tabs." accent="Nothing here belongs to a real person." /></Sequence>
      <Sequence from={240} durationInFrames={210}><AppScene duration={210} image="upload.png" label="1 · Upload" title="Start with a supported file." body="Preview its period, account, rows, and warnings before reconciling." /></Sequence>
      <Sequence from={450} durationInFrames={210}><AppScene duration={210} image="dashboard.png" label="2 · Dashboard" title="See what happened this month." body="Verified income and included spending stay separate from transfers, refunds, and reversals." /></Sequence>
      <Sequence from={660} durationInFrames={180}><AppScene duration={180} image="transactions.png" label="3 · Transactions" title="The reason is part of the answer." body="Inspect the category, evidence, confidence, and local memory behind a row." /></Sequence>
      <Sequence from={840} durationInFrames={180}><AppScene duration={180} image="cash-flow.png" label="4 · Cash flow" title="A credit is not always income." body="The real calendar keeps salary evidence separate from refunds and transfers." /></Sequence>
      <Sequence from={1020} durationInFrames={150}><AppScene duration={150} image="subscriptions.png" label="5 · Recurring commitments" title="See the monthly weight." body="Review a detected pattern without letting GODFIN cancel or change a payment." /></Sequence>
      <Sequence from={1170} durationInFrames={150}><AppScene duration={150} image="budget.png" label="6 · Budget & goals" title="Progress with entries behind it." body="Deposits and withdrawals remain visible instead of collapsing into a mystery number." /></Sequence>
      <Sequence from={1320} durationInFrames={75}><AppScene duration={75} image="reports.png" label="7 · Reports" title="A useful story with honest warnings." body="Verified calculations come first; optional AI can explain but never replace them." /></Sequence>
      <Sequence from={1395} durationInFrames={75}><AppScene duration={75} image="behavior-insights.png" label="8 · Money habits" title="Reflection in plain language." body="Simple observations come before the more technical ratios." /></Sequence>
      <Sequence from={1470} durationInFrames={150}><CopyScene duration={150} line="Your month belongs on your computer." accent="Try the exact app interface at godfin.dev/demo" /></Sequence>
    </AbsoluteFill>
  );
}

export function SocialFilm() {
  return (
    <AbsoluteFill>
      <Sequence from={0} durationInFrames={60}><CopyScene duration={60} line="Your money." social /></Sequence>
      <Sequence from={60} durationInFrames={60}><CopyScene duration={60} line="Your laptop." social /></Sequence>
      <Sequence from={120} durationInFrames={60}><CopyScene duration={60} line="A clearer month." accent="Inside the real GODFIN app." social /></Sequence>
      <Sequence from={180} durationInFrames={120}><AppScene duration={120} image="upload.png" label="Real Upload screen" title="Preview first." body="Made-up statement. Actual desktop interface." social /></Sequence>
      <Sequence from={300} durationInFrames={120}><AppScene duration={120} image="dashboard.png" label="Real Dashboard" title="₹33,000 left." body="₹44,000 verified income minus ₹11,000 included spending." social /></Sequence>
      <Sequence from={420} durationInFrames={60}><CopyScene duration={60} line="Ordinary finance records stay on your computer." social /></Sequence>
      <Sequence from={480} durationInFrames={60}><CopyScene duration={60} line="Try every real tab." accent="godfin.dev/demo" social /></Sequence>
    </AbsoluteFill>
  );
}
