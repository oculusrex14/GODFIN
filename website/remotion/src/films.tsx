import type { CSSProperties, ReactNode } from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import demo from "../../public/demo/demo-data.json";

const colors = {
  ink: "#07131f",
  navy: "#102c46",
  paper: "#f2eee5",
  cream: "#fbf8f1",
  teal: "#54e1d0",
  tealDark: "#177c71",
  lime: "#c9f36b",
  amber: "#ffca65",
  muted: "#93a3b8",
  white: "#f6f7f3",
};

const disclosure = "Demo data - made-up household - nothing here is connected to a bank";

function useSceneMotion(duration: number) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 105 } });
  const opacity = interpolate(frame, [0, 14, duration - 14, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return { opacity, transform: `translateY(${(1 - enter) * 32}px)` };
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: compact ? 14 : 20 }}>
      <Img src={staticFile("assets/godfin-vault-dial.png")} style={{ width: compact ? 54 : 78, height: compact ? 54 : 78, objectFit: "contain" }} />
      <div><strong style={{ color: colors.white, fontSize: compact ? 28 : 42, letterSpacing: "0.04em" }}>GOD<span style={{ color: colors.lime }}>FIN</span></strong><small style={{ display: "block", marginTop: 4, color: "rgba(255,255,255,.38)", fontSize: compact ? 8 : 11, letterSpacing: "0.2em", textTransform: "uppercase" }}>Local-first. Private. In control.</small></div>
    </div>
  );
}

function Frame({ children, light = false }: { children: ReactNode; light?: boolean }) {
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: light ? colors.paper : colors.ink, color: light ? colors.ink : colors.white, fontFamily: "GODFIN Sans, Arial, sans-serif" }}>
      <style>{`@font-face{font-family:'GODFIN Sans';src:url('${staticFile("assets/geist-latin.woff2")}') format('woff2');font-weight:100 900;font-style:normal}`}</style>
      <div style={{ position: "absolute", inset: 0, background: light ? "radial-gradient(circle at 86% 12%, rgba(23,124,113,.16), transparent 30%)" : "radial-gradient(circle at 82% 14%, rgba(84,225,208,.19), transparent 29%)" }} />
      {children}
      <div style={{ position: "absolute", right: 56, bottom: 34, left: 56, display: "flex", justifyContent: "center", gap: 10, color: light ? "rgba(7,19,31,.52)" : "rgba(255,255,255,.5)", fontSize: 18, letterSpacing: "0.025em" }}><span style={{ width: 9, height: 9, marginTop: 6, borderRadius: "50%", background: colors.lime }} />{disclosure}</div>
    </AbsoluteFill>
  );
}

function CopyScene({ title, body, duration, eyebrow, children, light = false, align = "left" }: { title: string; body: string; duration: number; eyebrow?: string; children?: ReactNode; light?: boolean; align?: "left" | "center" }) {
  const motion = useSceneMotion(duration);
  return (
    <Frame light={light}>
      <div style={{ position: "absolute", top: 54, left: 66 }}><Brand compact /></div>
      <div style={{ position: "relative", zIndex: 1, height: "100%", display: "flex", alignItems: "center", justifyContent: "center", padding: "130px 110px 100px", textAlign: align }}>
        <div style={{ width: "100%", maxWidth: align === "center" ? 1380 : 1650, ...motion }}>
          {eyebrow ? <div style={{ marginBottom: 24, color: light ? colors.tealDark : colors.lime, fontSize: 24, fontWeight: 800, letterSpacing: "0.16em", textTransform: "uppercase" }}>{eyebrow}</div> : null}
          <h1 style={{ maxWidth: align === "center" ? 1450 : 1200, margin: align === "center" ? "0 auto 30px" : "0 0 30px", fontSize: align === "center" ? 112 : 98, lineHeight: 0.96, letterSpacing: "-0.065em" }}>{title}</h1>
          <p style={{ maxWidth: 1080, margin: align === "center" ? "0 auto" : 0, color: light ? "#596962" : "rgba(255,255,255,.62)", fontSize: 32, lineHeight: 1.45 }}>{body}</p>
          {children}
        </div>
      </div>
    </Frame>
  );
}

const card: CSSProperties = { border: "1px solid rgba(255,255,255,.12)", borderRadius: 24, background: "rgba(255,255,255,.055)", boxShadow: "0 26px 80px rgba(0,0,0,.18)" };

function ImportVisual() {
  return <div style={{ ...card, marginTop: 45, padding: 30, display: "grid", gridTemplateColumns: "1fr auto", gap: 24, textAlign: "left" }}><div><span style={{ color: colors.teal, fontSize: 19 }}>SUPPORTED STATEMENT PREVIEW</span><h3 style={{ margin: "14px 0 8px", fontSize: 34 }}>Synthetic July statement</h3><p style={{ margin: 0, color: colors.muted, fontSize: 20 }}>13 listed rows · period recognized · review before reconcile</p></div><div style={{ display: "flex", alignItems: "center", gap: 14 }}><span style={{ padding: "12px 18px", borderRadius: 99, background: "rgba(201,243,107,.14)", color: colors.lime }}>Ready for review</span><span style={{ padding: "15px 22px", borderRadius: 14, background: colors.lime, color: colors.ink, fontWeight: 800 }}>Reconcile</span></div></div>;
}

function DashboardVisual() {
  const metrics = [["Money in", "₹44,000"], ["Included spending", "₹11,000"], ["Left this month", "₹33,000"], ["Saved", "75%"]];
  return <div style={{ marginTop: 46 }}><div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }}>{metrics.map(([label, value]) => <div key={label} style={{ ...card, padding: 24, textAlign: "left" }}><span style={{ color: colors.muted, fontSize: 17 }}>{label}</span><strong style={{ display: "block", marginTop: 14, color: label === "Left this month" ? colors.teal : colors.white, fontSize: 35 }}>{value}</strong></div>)}</div><div style={{ ...card, marginTop: 16, padding: 20, borderColor: "rgba(255,202,101,.28)", color: colors.amber, textAlign: "left" }}><strong>Account balance unavailable</strong><span style={{ marginLeft: 18, color: colors.muted }}>Conflicting statement controls need review. GODFIN does not guess.</span></div></div>;
}

function TransactionVisual() {
  return <div style={{ ...card, marginTop: 46, overflow: "hidden", textAlign: "left" }}>{[
    ["SYNTHETIC GROCERIES", "Groceries", "−₹8,000", "Confirmed food-and-dining classification"],
    ["SYNTHETIC OWN TRANSFER", "Own transfer", "−₹5,000", "Excluded from spending to avoid double counting"],
    ["SYNTHETIC GENERIC CREDIT", "Other credit", "+₹7,000", "Not called income without evidence"],
  ].map((row, index) => <div key={row[0]} style={{ display: "grid", gridTemplateColumns: "1.2fr .7fr .5fr 1.4fr", gap: 22, padding: "22px 26px", borderTop: index ? "1px solid rgba(255,255,255,.09)" : 0, alignItems: "center" }}><strong>{row[0]}</strong><span style={{ color: colors.muted }}>{row[1]}</span><strong style={{ color: row[2].startsWith("+") ? colors.teal : colors.white }}>{row[2]}</strong><span style={{ color: colors.lime, fontSize: 17 }}>Why: {row[3]}</span></div>)}</div>;
}

function BillsVisual() {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 48, textAlign: "left" }}><div style={{ ...card, padding: 30 }}><span style={{ color: colors.muted }}>Regular commitments</span><strong style={{ display: "block", margin: "18px 0", fontSize: 58 }}>₹1,830 / month</strong><small style={{ color: colors.muted, fontSize: 19 }}>₹21,960 across a full year if nothing changes</small></div><div style={{ ...card, padding: 30 }}><p style={{ margin: "0 0 20px" }}>Synthetic INR subscription <strong style={{ float: "right" }}>₹1,000</strong></p><p style={{ margin: 0 }}>Synthetic USD subscription <strong style={{ float: "right" }}>₹830</strong></p></div></div>;
}

function GoalVisual() {
  return <div style={{ ...card, marginTop: 46, padding: 34, textAlign: "left" }}><span style={{ color: colors.teal }}>SYNTHETIC EMERGENCY FUND</span><div style={{ display: "flex", alignItems: "baseline", gap: 16, margin: "20px 0" }}><strong style={{ fontSize: 62 }}>₹8,000</strong><span style={{ color: colors.muted, fontSize: 24 }}>of ₹50,000</span></div><div style={{ height: 13, overflow: "hidden", borderRadius: 99, background: "rgba(255,255,255,.1)" }}><div style={{ width: "16%", height: "100%", background: colors.lime }} /></div><p style={{ color: colors.muted, fontSize: 19 }}>₹10,000 deposit − ₹2,000 withdrawal = ₹8,000 explained balance</p></div>;
}

function ReportVisual() {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 46, textAlign: "left" }}><div style={{ ...card, padding: 30 }}><span style={{ color: colors.teal }}>YOUR JULY MONEY STORY</span><strong style={{ display: "block", margin: "16px 0", fontSize: 58 }}>₹33,000 left</strong><p style={{ color: colors.muted, fontSize: 19 }}>after ₹11,000 of included spending</p></div><div style={{ ...card, padding: 30 }}><span style={{ color: colors.lime }}>NET WORTH IN THIS DEMO</span><strong style={{ display: "block", margin: "16px 0", fontSize: 58 }}>₹88,300</strong><p style={{ color: colors.muted, fontSize: 19 }}>Review evidence, not filing-ready tax advice</p></div></div>;
}

function IntroScene({ duration, social = false }: { duration: number; social?: boolean }) {
  const motion = useSceneMotion(duration);
  return <Frame><div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: social ? 80 : 120, textAlign: "center" }}><div style={motion}><Brand /><h1 style={{ maxWidth: social ? 900 : 1450, margin: social ? "100px auto 28px" : "70px auto 30px", fontSize: social ? 126 : 128, lineHeight: .94, letterSpacing: "-.07em" }}>{social ? "Your money. Your laptop." : "A clearer month, without moving your money life online."}</h1><p style={{ color: "rgba(255,255,255,.58)", fontSize: social ? 34 : 32 }}>Desktop-first personal finance for supported Indian bank statements.</p></div></div></Frame>;
}

export function HeroFilm() {
  return <AbsoluteFill>
    <Sequence from={0} durationInFrames={90}><IntroScene duration={90} /></Sequence>
    <Sequence from={90} durationInFrames={120}><CopyScene duration={120} eyebrow="Bring in the month" title="Preview before you reconcile." body="See the period, account, rows, and warnings before anything joins the local ledger."><ImportVisual /></CopyScene></Sequence>
    <Sequence from={210} durationInFrames={150}><CopyScene duration={150} eyebrow="See what happened" title="Money in. Spending. What was left." body="Verified totals stay separate from transfers, refunds, reversals, and unsupported guesses."><DashboardVisual /></CopyScene></Sequence>
    <Sequence from={360} durationInFrames={120}><CopyScene duration={120} eyebrow="Keep the reasoning" title="Correct it. See why next time." body="Confirmed local memory helps with future reviews while finalized months stay untouched."><TransactionVisual /></CopyScene></Sequence>
    <Sequence from={480} durationInFrames={75}><CopyScene duration={75} eyebrow="Notice what repeats" title="₹1,830 a month, made visible." body="Review regular commitments without letting the app cancel or change a payment."><BillsVisual /></CopyScene></Sequence>
    <Sequence from={555} durationInFrames={75}><CopyScene duration={75} eyebrow="Make it useful" title="A goal and report that add up." body="Contribution history and verified monthly totals keep the story explainable."><GoalVisual /></CopyScene></Sequence>
    <Sequence from={630} durationInFrames={90}><CopyScene duration={90} eyebrow="Early desktop beta" title="Try the made-up household at godfin.dev/demo" body="Join the selected Apple Silicon Mac and Windows x64 tester cohort." align="center" /></Sequence>
  </AbsoluteFill>;
}

export function WalkthroughFilm() {
  return <AbsoluteFill>
    <Sequence from={0} durationInFrames={120}><IntroScene duration={120} /></Sequence>
    <Sequence from={120} durationInFrames={120}><CopyScene duration={120} eyebrow="One made-up household" title="Nothing here belongs to a real person." body="The same golden acceptance ledger powers every scene, from July totals to the goal and net worth." align="center" /></Sequence>
    <Sequence from={240} durationInFrames={210}><CopyScene duration={210} eyebrow="1 · Statement review" title="Start with a supported file." body="Preview recognized rows and warnings before reconciling the month."><ImportVisual /></CopyScene></Sequence>
    <Sequence from={450} durationInFrames={210}><CopyScene duration={210} eyebrow="2 · Monthly picture" title="₹44,000 in. ₹11,000 spent. ₹33,000 left." body="The 75% savings rate uses verified income and included spending only."><DashboardVisual /></CopyScene></Sequence>
    <Sequence from={660} durationInFrames={180}><CopyScene duration={180} eyebrow="3 · Classification" title="The reason is part of the answer." body="Transfers are excluded, ordinary spending is included, and an unexplained credit is not promoted to income."><TransactionVisual /></CopyScene></Sequence>
    <Sequence from={840} durationInFrames={180}><CopyScene duration={180} eyebrow="4 · Cash flow and income" title="A credit is not always income." body="Salary and freelance evidence total ₹44,000; refunds, reimbursements, transfers, and reversals stay separate."><DashboardVisual /></CopyScene></Sequence>
    <Sequence from={1020} durationInFrames={150}><CopyScene duration={150} eyebrow="5 · Regular bills" title="See the monthly weight." body="₹1,000 in INR plus a fixed synthetic ₹830 reference conversion make ₹1,830 a month."><BillsVisual /></CopyScene></Sequence>
    <Sequence from={1170} durationInFrames={150}><CopyScene duration={150} eyebrow="6 · Goal history" title="₹8,000—and the entries behind it." body="A deposit and withdrawal remain visible instead of collapsing into a mystery number."><GoalVisual /></CopyScene></Sequence>
    <Sequence from={1320} durationInFrames={150}><CopyScene duration={150} eyebrow="7 · Report" title="A useful story with honest warnings." body="The balance remains unavailable when statement controls conflict. Reports do not pretend to choose or file a tax return."><ReportVisual /></CopyScene></Sequence>
    <Sequence from={1470} durationInFrames={150}><CopyScene duration={150} eyebrow="Local-first boundary" title="Your month belongs on your computer." body="Explore the auth-free synthetic demo, then join the early desktop tester list at godfin.dev." align="center" /></Sequence>
  </AbsoluteFill>;
}

function SocialCopy({ duration, line, accent }: { duration: number; line: string; accent?: string }) {
  const motion = useSceneMotion(duration);
  return <Frame><div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: "170px 80px", textAlign: "center" }}><div style={motion}><h1 style={{ margin: 0, fontSize: 132, lineHeight: .94, letterSpacing: "-.07em" }}>{line}</h1>{accent ? <p style={{ marginTop: 38, color: colors.lime, fontSize: 38 }}>{accent}</p> : null}</div></div></Frame>;
}

export function SocialFilm() {
  return <AbsoluteFill>
    <Sequence from={0} durationInFrames={60}><SocialCopy duration={60} line="Your money." /></Sequence>
    <Sequence from={60} durationInFrames={60}><SocialCopy duration={60} line="Your laptop." /></Sequence>
    <Sequence from={120} durationInFrames={60}><SocialCopy duration={60} line="A clearer month." accent="Without the spreadsheet maze." /></Sequence>
    <Sequence from={180} durationInFrames={120}><CopyScene duration={120} eyebrow="Preview the month" title="13 made-up rows. Review first." body="Supported statement imports stay in the desktop workflow."><ImportVisual /></CopyScene></Sequence>
    <Sequence from={300} durationInFrames={120}><CopyScene duration={120} eyebrow="July 2026" title="₹33,000 left." body="₹44,000 verified income minus ₹11,000 included spending."><DashboardVisual /></CopyScene></Sequence>
    <Sequence from={420} durationInFrames={60}><SocialCopy duration={60} line="Ordinary finance records stay on your computer." /></Sequence>
    <Sequence from={480} durationInFrames={60}><SocialCopy duration={60} line="Early desktop testers wanted." accent="godfin.dev" /></Sequence>
  </AbsoluteFill>;
}

void demo;
