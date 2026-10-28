"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { useVisualViewport } from "@/hooks/use-is-mobile";
import { cn } from "@/lib/utils";

type Size = "half" | "full";

/**
 * A bottom sheet for phones: dims the page behind it, opens at about half height (the menu stays
 * visible above), and grows to nearly full height. Drag the handle up or down, or tap it, to change
 * size; drag down from the half height, tap the dimmed area, press Escape, or use the X to close.
 * It rises above the on-screen keyboard, and the page behind it doesn't scroll while it's open.
 */
export function BottomSheet({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const [size, setSize] = useState<Size>("half");
  const drag = useRef<number | null>(null);
  const { height: visible, keyboard } = useVisualViewport();

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  function release(clientY: number) {
    if (drag.current === null) return;
    const dy = clientY - drag.current;
    drag.current = null;
    if (Math.abs(dy) < 8) setSize((s) => (s === "half" ? "full" : "half")); // a tap
    else if (dy > 50) {
      if (size === "full") setSize("half");
      else onClose();
    } else if (dy < -50) setSize("full");
  }

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-black/45 backdrop-blur-[1px]" />
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{ bottom: keyboard, maxHeight: visible ? visible - 8 : undefined }}
        className={cn(
          "absolute inset-x-0 flex flex-col overflow-hidden rounded-t-3xl border-t bg-background shadow-2xl",
          "animate-in slide-in-from-bottom duration-200",
          size === "half" ? "h-[58dvh]" : "h-[92dvh]"
        )}
      >
        <div
          className="flex shrink-0 cursor-grab touch-none flex-col items-center pt-2.5 pb-1"
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            drag.current = e.clientY;
          }}
          onPointerUp={(e) => release(e.clientY)}
          onPointerCancel={() => (drag.current = null)}
        >
          <span className="h-1.5 w-11 rounded-full bg-muted-foreground/30" aria-hidden />
        </div>
        <header className="flex shrink-0 items-center justify-between px-4 pb-2">
          <div>
            <h2 className="text-sm font-semibold">{title}</h2>
            {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-9 items-center justify-center rounded-full hover:bg-muted">
            <X className="size-4" />
          </button>
        </header>
        <div className="flex min-h-0 flex-1 flex-col px-3 pb-3">{children}</div>
      </section>
    </div>
  );
}
