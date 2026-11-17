"use client";

import type { Language } from "@/lib/api";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Language; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
];

/** Auto / English / हिन्दी. Auto (the default) answers in whatever language the guest just used; the other two fix the
 * reply language, and what speech recognition listens for, for a guest who wants that. */
export function LanguageToggle({
  value,
  onChange,
  disabled = false,
}: {
  value: Language;
  onChange: (next: Language) => void;
  disabled?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label="Language" className="inline-flex rounded-full border bg-muted p-0.5 text-xs">
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            "rounded-full px-3 py-1 font-medium transition-colors disabled:opacity-50",
            value === option.value ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
