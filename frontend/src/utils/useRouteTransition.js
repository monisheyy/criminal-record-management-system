import { useEffect, useRef, useState } from 'react';

// Curtain timings (ms). The new page is swapped in while the curtain fully
// covers the screen, so the old page never flashes into the new one.
const COVER_MS = 520;
const HOLD_MS = 520;
const INTRO_HOLD_MS = 900;
const REVEAL_MS = 650;

function shouldAnimate() {
  if (typeof window === 'undefined') return false;
  // Automated browsers (Playwright e2e and visual tests) get instant navigation.
  if (navigator.webdriver) return false;
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Delays the rendered location behind a branded curtain on every page change.
 * Returns the location <Routes> should render and the curtain phase:
 * idle → cover → hold → reveal → idle (intro → reveal on first load).
 */
export function useRouteTransition(location) {
  const [animate] = useState(shouldAnimate);
  const [displayLocation, setDisplayLocation] = useState(location);
  const [phase, setPhase] = useState(animate ? 'intro' : 'idle');
  const timers = useRef([]);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;
  // Path the curtain is currently heading to, and the newest location for it.
  const targetPath = useRef(null);
  const latestLocation = useRef(location);
  latestLocation.current = location;

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const after = (ms, fn) => timers.current.push(setTimeout(fn, ms));

  useEffect(() => {
    if (!animate) return undefined;
    after(INTRO_HOLD_MS, () => setPhase('reveal'));
    after(INTRO_HOLD_MS + REVEAL_MS, () => setPhase('idle'));
    return clearTimers;
  }, [animate]);

  useEffect(() => {
    // Query-string changes (filters, pagination) stay instant.
    if (location.pathname === displayLocation.pathname) {
      targetPath.current = null;
      if (location !== displayLocation) setDisplayLocation(location);
      return;
    }
    // A repeat navigation to the page the curtain is already heading to (for
    // example a <Navigate> on the outgoing page re-firing) must not restart
    // the curtain, or it never finishes: the newest location is picked up
    // when the swap happens.
    if (location.pathname === targetPath.current) return;
    if (!animate) {
      setDisplayLocation(location);
      return;
    }
    // Already fully covered (first load, or a redirect mid-transition): swap at once.
    const cover = phaseRef.current === 'intro' || phaseRef.current === 'hold' ? 0 : COVER_MS;
    clearTimers();
    targetPath.current = location.pathname;
    if (cover) setPhase('cover');
    after(cover, () => {
      targetPath.current = null;
      setDisplayLocation(latestLocation.current);
      window.scrollTo(0, 0);
      setPhase('hold');
    });
    // Signing out skips the hold so the sign-in page appears straight away.
    const hold = location.pathname === '/login' ? 0 : HOLD_MS;
    after(cover + hold, () => setPhase('reveal'));
    after(cover + hold + REVEAL_MS, () => setPhase('idle'));
    // displayLocation is deliberately left out: only a new target restarts the curtain.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location, animate]);

  useEffect(() => clearTimers, []);

  return { displayLocation, phase };
}
