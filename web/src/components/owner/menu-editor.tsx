"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { DishSheet } from "@/components/owner/dish-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { MenuItem } from "@/lib/api";
import { deleteDish, saveDish, type OwnerMenu } from "@/lib/owner-api";
import { cn, formatPrice } from "@/lib/utils";

function priceLabel(dish: MenuItem): string {
  if (dish.variants?.length) return dish.variants.map((v) => `${v.name} ${formatPrice(v.price)}`).join(" · ");
  return formatPrice(dish.price);
}

const STORY_BADGE: Record<string, string> = { approved: "Story ✓", ai_draft: "Story: draft", missing: "No story" };

export function MenuEditor({ menu, onChanged }: { menu: OwnerMenu; onChanged: () => Promise<void> }) {
  const { restaurant, categories, dishes } = menu;
  const [editing, setEditing] = useState<MenuItem | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [sheetKey, setSheetKey] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 5000);
    return () => clearTimeout(t);
  }, [notice]);

  const grouped = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const visible = q ? dishes.filter((d) => d.name.toLowerCase().includes(q)) : dishes;
    return categories
      .map((c) => ({ category: c, items: visible.filter((d) => d.category === c) }))
      .filter((g) => g.items.length > 0);
  }, [categories, dishes, filter]);

  const withStory = dishes.filter((d) => d.long_description).length;
  const unavailable = dishes.filter((d) => d.is_available === false).length;

  function openSheet(dish: MenuItem | null) {
    setEditing(dish);
    setSheetKey((k) => k + 1); // fresh form per dish
    setSheetOpen(true);
  }

  async function toggleAvailable(dish: MenuItem) {
    setError(null);
    try {
      await saveDish(restaurant.id, dish.id, { is_available: dish.is_available === false });
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(dish: MenuItem) {
    if (!window.confirm(`Delete "${dish.name}" from the menu?`)) return;
    setError(null);
    try {
      await deleteDish(restaurant.id, dish.id);
      setNotice(`Deleted "${dish.name}".`);
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {dishes.length} dishes · {withStory} with a story · {unavailable} unavailable
        </p>
        <div className="flex gap-2">
          <input
            placeholder="Search dishes…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-8 w-44 rounded-lg border border-input bg-transparent px-2.5 text-sm"
          />
          <Button size="sm" onClick={() => openSheet(null)}>
            <Plus className="size-3.5" /> Add dish
          </Button>
        </div>
      </div>

      {notice && <p className="rounded-lg border bg-muted/50 px-3 py-2 text-sm">{notice}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}

      {grouped.map(({ category, items }) => (
        <section key={category} className="flex flex-col gap-1">
          <h3 className="text-sm font-semibold text-muted-foreground">
            {category} ({items.length})
          </h3>
          <div className="divide-y rounded-lg border">
            {items.map((dish) => (
              <div
                key={dish.id}
                className={cn("flex flex-wrap items-center gap-3 px-3 py-2", dish.is_available === false && "opacity-60")}
              >
                <span
                  className={cn("size-2.5 shrink-0 rounded-full", dish.veg ? "bg-emerald-600" : "bg-red-600")}
                  aria-label={dish.veg ? "Vegetarian" : "Non-vegetarian"}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{dish.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{priceLabel(dish)}</p>
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {STORY_BADGE[dish.knowledge_status ?? "missing"]}
                </Badge>
                <label className="flex items-center gap-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={dish.is_available !== false}
                    onChange={() => toggleAvailable(dish)}
                    aria-label={`${dish.name} available`}
                  />
                  Available
                </label>
                <Button size="icon" variant="ghost" onClick={() => openSheet(dish)} aria-label={`Edit ${dish.name}`}>
                  <Pencil className="size-4" />
                </Button>
                <Button size="icon" variant="ghost" onClick={() => remove(dish)} aria-label={`Delete ${dish.name}`}>
                  <Trash2 className="size-4" />
                </Button>
              </div>
            ))}
          </div>
        </section>
      ))}
      {grouped.length === 0 && <p className="text-sm text-muted-foreground">No dishes match.</p>}

      <DishSheet
        key={sheetKey}
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        restaurant={restaurant}
        dish={editing}
        categories={categories}
        onSaved={(message) => {
          setNotice(message);
          void onChanged();
        }}
      />
    </div>
  );
}
