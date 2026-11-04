"use client";

import { Phone, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { NumberPrompt } from "@/hooks/use-realtime-call";
import { normalizeNumber } from "@/lib/caller";

/**
 * "Who's calling?": shown by a demo store when a call is about to start. The number lets the agent recognise
 * a customer who has ordered before (a real phone call would carry it as caller ID). It is only used to find
 * past orders: a typed number is never messaged.
 */
export function CallerNumberDialog({ prompt, agentName }: { prompt: NumberPrompt; agentName: string }) {
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!prompt.open) return;
    input.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") prompt.cancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prompt]);

  if (!prompt.open) return null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const number = normalizeNumber(value);
    if (!number) {
      setProblem("Enter a 10-digit mobile number, like 98765 43210.");
      return;
    }
    setProblem(null);
    prompt.submit(number);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="caller-dialog-title"
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/50 p-4 sm:items-center"
      onClick={(event) => event.target === event.currentTarget && prompt.cancel()}
    >
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl border bg-background p-5 shadow-xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-9 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Phone className="size-4" />
            </span>
            <h2 id="caller-dialog-title" className="text-base font-semibold">
              Who&apos;s calling {agentName}?
            </h2>
          </div>
          <button type="button" onClick={prompt.cancel} aria-label="Cancel the call" className="text-muted-foreground">
            <X className="size-4" />
          </button>
        </div>
        <p className="mb-4 text-sm text-muted-foreground">
          This is a demo. Enter the mobile number you would call from, and {agentName} will recognise you if you have
          ordered here before. It is only used to find your past orders, and is never messaged.
        </p>
        <label htmlFor="caller-number" className="mb-1 block text-xs font-medium">
          Mobile number
        </label>
        <Input
          id="caller-number"
          ref={input}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="98765 43210"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-invalid={problem !== null}
        />
        {problem && <p className="mt-1 text-xs text-destructive">{problem}</p>}
        <div className="mt-4 flex flex-col gap-2">
          <Button type="submit" className="gap-2">
            <Phone className="size-4" />
            Start the call
          </Button>
          <button type="button" onClick={prompt.skip} className="text-xs text-muted-foreground underline-offset-4 hover:underline">
            Continue without a number
          </button>
        </div>
      </form>
    </div>
  );
}
