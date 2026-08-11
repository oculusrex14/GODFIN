# Accessibility Verification

This record covers repository work for `GF-A11Y-001`. Browser execution remains in the final owner-requested browser tranche.

## Shared application contracts

- `DialogSurface` is the only modal-dialog primitive. It supplies dialog semantics, an accessible name, Escape handling, Tab and Shift+Tab containment, background isolation with `inert`/`aria-hidden`, body scroll locking, nested-dialog ordering, initial focus, and return focus.
- All 23 current dialogs, including the mobile navigation drawer, use that primitive. A repository check rejects raw `role="dialog"` or `aria-modal` implementations elsewhere.
- Every route rendered inside the application layout has a level-one heading. Route changes focus that heading after lazy content mounts. A keyboard-visible skip link targets the focusable main region.
- Icon-only buttons and raw form controls have programmatic names. Button groups expose selection state, and binary settings use switch semantics.
- Success/information notifications use polite status announcements; errors use assertive alerts. Notification dismiss buttons have an explicit name.
- Calculation explanations work with hover, focus, tap, Escape, scrolling, and viewport clamping. Escape returns focus to the explanation button.
- Framer Motion uses the operating-system reduced-motion preference. CSS also removes nonessential animation, smooth scrolling, and long transitions when reduced motion is requested. A high-visibility focus ring applies to keyboard-focusable controls.

## Repository gates

From `frontend/` run:

```sh
npm run verify:a11y
npm run lint
npm run build
```

`verify:a11y` parses every JSX/TSX source file and currently checks 163 buttons, 72 raw form fields, and 23 dialogs. It fails for an unnamed icon button, an unlabelled raw field, a dialog that bypasses `DialogSurface`, a missing skip/route-focus contract, missing notification semantics, missing reduced-motion support, or loss of the focus/inert/return behavior in the shared primitive.

The authored Playwright accessibility suite adds serious/critical axe checks, PIN touch targets, skip-link behavior, route-heading focus, modal Tab wrapping, Shift+Tab wrapping, inert background, Escape close, trigger focus return, reduced motion, and 400% text scaling. It deliberately has not been executed yet because browser-controlled work was deferred by the owner.

## Final manual and automated browser matrix

Before public launch, execute the authored suite and manually verify:

1. Chromium/Electron, Firefox, and WebKit at 100%, 200%, and 400% zoom.
2. Keyboard-only navigation through every route, drawer, tooltip, nested confirmation, long form, and toast.
3. VoiceOver on macOS and NVDA on Windows for headings, landmarks, status announcements, field errors, tables/charts, and dialogs.
4. Reduced-motion, increased-contrast, and operating-system text-size preferences.
5. No clipped action, two-dimensional page scrolling, hidden focused control, focus loss, or background interaction while a modal is open.
6. Contrast checks for text, controls, focus indicators, charts, validation states, and disabled states. Automated axe evidence supplements but does not replace this visual review.

Record browser versions, operating systems, failures, screenshots, and retest results in the final release evidence. Keep `GF-A11Y-001` partially verified until this matrix passes.
