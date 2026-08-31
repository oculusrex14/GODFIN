import { Composition } from "remotion";

import { HeroFilm, SocialFilm, WalkthroughFilm } from "./films";

export const COMPOSITIONS = {
  hero: { id: "GodfinBetaHero16x9", width: 1920, height: 1080, fps: 30, durationInFrames: 720 },
  walkthrough: { id: "GodfinDemoWalkthrough16x9", width: 1920, height: 1080, fps: 30, durationInFrames: 1620 },
  social: { id: "GodfinBetaSocial9x16", width: 1080, height: 1920, fps: 30, durationInFrames: 540 },
} as const;

export function RemotionRoot() {
  return (
    <>
      <Composition component={HeroFilm} {...COMPOSITIONS.hero} />
      <Composition component={WalkthroughFilm} {...COMPOSITIONS.walkthrough} />
      <Composition component={SocialFilm} {...COMPOSITIONS.social} />
    </>
  );
}
