"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(max-width: 1023px)"; // below Tailwind's `lg`: the phone and tablet layout

function subscribe(callback: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

/** True on phone-sized screens. Rendered as false on the server and corrected right after hydration. */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => false);
}

function subscribeViewport(callback: () => void) {
  const viewport = window.visualViewport;
  viewport?.addEventListener("resize", callback);
  viewport?.addEventListener("scroll", callback);
  return () => {
    viewport?.removeEventListener("resize", callback);
    viewport?.removeEventListener("scroll", callback);
  };
}

function viewportKey(): string {
  const viewport = window.visualViewport;
  if (!viewport) return "0|0";
  // How much of the bottom of the screen the on-screen keyboard covers, and the height left over.
  const covered = Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop));
  return `${Math.round(viewport.height)}|${covered}`;
}

/** The visible height and the on-screen keyboard's height, so a bottom sheet can sit above the keyboard. */
export function useVisualViewport(): { height: number; keyboard: number } {
  const key = useSyncExternalStore(subscribeViewport, viewportKey, () => "0|0");
  const [height, keyboard] = key.split("|").map(Number);
  return { height, keyboard };
}
