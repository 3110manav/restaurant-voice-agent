"use client";

import { WaveGridBackground } from "@/components/ui/wave-grid-background";

export function Hero() {
  return (
    <WaveGridBackground
      className="h-[400px] sm:h-[500px]"
      colorBase="#0a0a0a"
      colorHigh="#8b5cf6"
    >
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <h1 className="text-6xl font-bold tracking-tight text-white sm:text-7xl">
          Sarthi
        </h1>
        <p className="max-w-md px-6 text-sm text-white/70 sm:text-base">
          One voice AI brand, four personas — each with its own name, its own
          job, and the same tool-calling engine underneath.
        </p>
      </div>
    </WaveGridBackground>
  );
}
