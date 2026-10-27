"use client";

import { useEffect } from "react";

/** Renders nothing. Pings the backend once when the page opens so a sleeping free-tier server is
 * already waking by the time someone scans a QR code or opens a menu. */
export function WarmBackend() {
  useEffect(() => {
    fetch("/api/health", { cache: "no-store" }).catch(() => {});
  }, []);
  return null;
}
