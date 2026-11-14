"use client";

import { useSpeechChoice, type SpeechStack } from "@/lib/speech";
import { cn } from "@/lib/utils";

const OPTIONS: { value: SpeechStack; label: string }[] = [
  { value: "groq", label: "Groq" },
  { value: "sarvam", label: "Sarvam" },
];

/** Groq or Sarvam for the voice (what hears the guest and what speaks). Shown only where the API allows
 * choosing, so a public site doesn't offer it. Sits beside the English / हिन्दी switch. */
export function SpeechToggle({ className }: { className?: string }) {
  const { available, value, set } = useSpeechChoice();
  if (!available) return null;
  return (
    <div
      role="radiogroup"
      aria-label="Voice engine"
      title="Which speech engine hears and speaks"
      className={cn("inline-flex items-center rounded-full border bg-muted p-0.5 text-xs", className)}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => set(option.value)}
          className={cn(
            "rounded-full px-3 py-1 font-medium transition-colors",
            value === option.value ? "bg-foreground text-background shadow-sm" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
