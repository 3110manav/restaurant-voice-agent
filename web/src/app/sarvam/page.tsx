import type { Metadata } from "next";

import { SarvamCall } from "@/components/voice/sarvam-call";

export const metadata: Metadata = { title: "Call a restaurant — Sarthi on Sarvam" };

export default function SarvamPage() {
  return (
    <main className="min-h-dvh bg-background">
      <SarvamCall />
    </main>
  );
}
