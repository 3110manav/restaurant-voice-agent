"use client";

import { Minus, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchMenu, type CartLine, type MenuItem, type RestaurantInfo } from "@/lib/api";
import type { Persona } from "@/lib/personas";
import { cn } from "@/lib/utils";

/** What the guest's pages share, whichever layout shows them (phone column in guest-app.tsx, desktop in guest-desktop.tsx). */

export const lineKey = (id: string, variant?: string | null) => `${id}|${variant ?? ""}`;
export const lineLabel = (line: { name: string; variant?: string | null; note?: string | null }) => {
  const label = line.variant ? `${line.name} (${line.variant})` : line.name;
  return line.note ? `${label} · ${line.note}` : label;
};
export const sum = (lines: CartLine[]) => lines.reduce((total, line) => total + line.price * line.quantity, 0);

/** A kirana or a pharmacy: ordered by chat or voice for delivery, with no table, kitchen or bill. */
export const isStore = (info: RestaurantInfo) => info.business_type === "kirana" || info.business_type === "pharmacy";

/** How the agent introduces itself, by the kind of place it works for. */
export function agentRole(info: RestaurantInfo): string {
  if (info.business_type === "pharmacy") return "pharmacy assistant";
  if (info.business_type === "kirana") return "store assistant";
  return "waiter";
}

export function welcomeLine(info: RestaurantInfo, persona: Persona): string {
  const name = persona.agentName;
  if (info.business_type === "pharmacy") {
    return `Hello! I'm ${name}, your pharmacy assistant. Tell me what you need, in Hindi, English or both, or pick from the list. Your pharmacist confirms every order.`;
  }
  if (info.business_type === "kirana") {
    return `Hello! I'm ${name}. Tell me what you need, in Hindi, English or both, or pick from the list, and we'll bring it to your door.`;
  }
  return `Welcome! I'm ${name}, your waiter today. Order from the menu, or just tell me what you feel like eating, in Hindi, English or both.`;
}

/** An example of what to type, for the kind of place it is. */
export function placeholderFor(info: RestaurantInfo, persona: Persona): string {
  if (info.business_type === "pharmacy") return "Add a Dolo 650 and two ORS sachets...";
  if (info.business_type === "kirana") return "Add two bars of soap and a pack of batteries...";
  return persona.placeholder;
}

/** A store's items or a restaurant's menu, fetched once per store. `null` while loading, `[]` after a failure. */
export function useMenu(persona: Persona, info: RestaurantInfo): { items: MenuItem[] | null; failed: boolean } {
  const [items, setItems] = useState<MenuItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMenu(persona.key, info.slug)
      .then((menu) => !cancelled && setItems(menu))
      .catch(() => {
        if (cancelled) return;
        setItems([]);
        setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [info.slug, persona.key]);

  return { items, failed };
}

export function Monogram({ info, className }: { info: RestaurantInfo; className?: string }) {
  if (info.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element -- the owner's logo, any host
    return <img src={info.logo_url} alt="" className={cn("rounded-[var(--radius)] object-cover", className)} />;
  }
  return (
    <div
      aria-hidden="true"
      className={cn("flex items-center justify-center rounded-[var(--radius)] bg-primary font-heading text-primary-foreground", className)}
    >
      {info.name.trim().charAt(0).toUpperCase()}
    </div>
  );
}

export function VegMark({ veg }: { veg: boolean }) {
  return (
    <span
      role="img"
      aria-label={veg ? "Vegetarian" : "Non-vegetarian"}
      className={cn(
        "inline-flex size-3.5 shrink-0 items-center justify-center rounded-[2px] border-[1.5px]",
        veg ? "border-emerald-600 dark:border-emerald-400" : "border-amber-800 dark:border-amber-400"
      )}
    >
      {veg ? (
        <span className="size-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
      ) : (
        <span className="size-0 border-x-[3.5px] border-b-[6px] border-x-transparent border-b-amber-800 dark:border-b-amber-400" />
      )}
    </span>
  );
}

export function Stepper({
  quantity,
  label,
  onAdd,
  onRemove,
  filled = true,
  compact = false,
}: {
  quantity: number;
  label: string;
  onAdd: () => void;
  onRemove: () => void;
  filled?: boolean;
  /** A smaller control for dense desktop cards. */
  compact?: boolean;
}) {
  const height = compact ? "h-9" : "h-11";
  if (quantity === 0) {
    return (
      <Button variant="outline" className={cn(height, "w-20 border-primary text-primary")} onClick={onAdd} aria-label={`Add ${label}`}>
        Add
      </Button>
    );
  }
  return (
    <div className={cn(height, "flex w-24 items-center justify-between rounded-[var(--radius)]", filled ? "bg-primary text-primary-foreground" : "border")}>
      <button type="button" className={cn(height, "flex w-9 items-center justify-center")} onClick={onRemove} aria-label={`Remove one ${label}`}>
        <Minus className="size-4" />
      </button>
      <span className="text-sm font-semibold">{quantity}</span>
      <button type="button" className={cn(height, "flex w-9 items-center justify-center")} onClick={onAdd} aria-label={`Add one more ${label}`}>
        <Plus className="size-4" />
      </button>
    </div>
  );
}
