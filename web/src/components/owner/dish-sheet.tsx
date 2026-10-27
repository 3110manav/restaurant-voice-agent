"use client";

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import type { MenuItem } from "@/lib/api";
import { saveDish, type DishInput, type OwnerRestaurant } from "@/lib/owner-api";

const SPICE_LEVELS = ["none", "mild", "medium", "hot"];

interface FormState {
  name: string;
  category: string;
  price: string;
  is_veg: boolean;
  spice_level: string;
  short_description: string;
  long_description: string;
  ingredients: string;
  allergens: string;
  tags: string;
  hasSizes: boolean;
  variants: { name: string; price: string }[];
}

const csv = (text: string) =>
  text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

function initialState(dish: MenuItem | null, categories: string[]): FormState {
  return {
    name: dish?.name ?? "",
    category: dish?.category ?? categories[0] ?? "",
    price: dish && !dish.variants?.length ? String(dish.price) : "",
    is_veg: dish?.veg ?? true,
    spice_level: dish?.spice_level ?? "mild",
    short_description: dish?.description ?? "",
    long_description: dish?.long_description ?? "",
    ingredients: (dish?.ingredients ?? []).join(", "),
    allergens: (dish?.allergens ?? []).join(", "),
    tags: (dish?.tags ?? []).join(", "),
    hasSizes: Boolean(dish?.variants?.length),
    variants: dish?.variants?.length
      ? dish.variants.map((v) => ({ name: v.name, price: String(v.price) }))
      : [
          { name: "Regular", price: "" },
          { name: "Large", price: "" },
        ],
  };
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

/** Create or edit one dish. Saving re-indexes just this dish for the waiter's search. */
export function DishSheet({
  open,
  onOpenChange,
  restaurant,
  dish,
  categories,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  restaurant: OwnerRestaurant;
  dish: MenuItem | null;
  categories: string[];
  onSaved: (message: string) => void;
}) {
  // The parent remounts this sheet per dish (via `key`), so the form starts from that dish.
  const [form, setForm] = useState<FormState>(() => initialState(dish, categories));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const payload: DishInput = {
      name: form.name,
      category: form.category || "Menu",
      is_veg: form.is_veg,
      spice_level: form.spice_level,
      short_description: form.short_description,
      long_description: form.long_description,
      ingredients: csv(form.ingredients),
      allergens: csv(form.allergens),
      tags: csv(form.tags),
    };
    if (form.hasSizes) {
      const variants = form.variants.map((v) => ({ name: v.name.trim(), price: Number(v.price) }));
      if (variants.length < 2 || variants.some((v) => !v.name || !Number.isFinite(v.price) || v.price < 0)) {
        setError("Give every size a name and a price, and add at least two sizes.");
        return;
      }
      payload.variants = variants;
    } else {
      const price = Number(form.price);
      if (form.price.trim() === "" || !Number.isFinite(price) || price < 0) {
        setError("Enter a price.");
        return;
      }
      payload.price = price;
      payload.variants = []; // clears any sizes this dish had before
    }

    setBusy(true);
    try {
      const result = await saveDish(restaurant.id, dish?.id ?? null, payload);
      onSaved(
        result.embedding_synced
          ? `Saved "${result.dish.name}" — ${restaurant.agent_name} can find it right away.`
          : `Saved "${result.dish.name}". Search will catch up shortly (use Settings → Re-sync).`
      );
      onOpenChange(false);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{dish ? `Edit ${dish.name}` : "Add a dish"}</SheetTitle>
          <SheetDescription>
            Changes go live for guests straight away. Only this dish is re-indexed for {restaurant.agent_name}&apos;s search.
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-4">
            <Field label="Name">
              <Input required value={form.name} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Category">
                <Input
                  list="dish-categories"
                  required
                  value={form.category}
                  onChange={(e) => set("category", e.target.value)}
                />
                <datalist id="dish-categories">
                  {categories.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </Field>
              <Field label="Spice">
                <select
                  className="h-8 rounded-lg border border-input bg-transparent px-2 text-sm capitalize"
                  value={form.spice_level}
                  onChange={(e) => set("spice_level", e.target.value)}
                >
                  {SPICE_LEVELS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </Field>
            </div>

            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" checked={form.is_veg} onChange={() => set("is_veg", true)} /> Vegetarian
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" checked={!form.is_veg} onChange={() => set("is_veg", false)} /> Non-vegetarian
              </label>
            </div>

            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={form.hasSizes} onChange={(e) => set("hasSizes", e.target.checked)} />
                Comes in sizes or portions (Regular / Large, Half / Full)
              </label>
              {form.hasSizes ? (
                <div className="flex flex-col gap-2">
                  {form.variants.map((v, i) => (
                    <div key={i} className="flex gap-2">
                      <Input
                        placeholder="Size name"
                        value={v.name}
                        onChange={(e) =>
                          set("variants", form.variants.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                        }
                      />
                      <Input
                        type="number"
                        min={0}
                        placeholder="Price ₹"
                        className="w-28"
                        value={v.price}
                        onChange={(e) =>
                          set("variants", form.variants.map((x, j) => (j === i ? { ...x, price: e.target.value } : x)))
                        }
                      />
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label="Remove size"
                        disabled={form.variants.length <= 2}
                        onClick={() => set("variants", form.variants.filter((_, j) => j !== i))}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="w-fit"
                    onClick={() => set("variants", [...form.variants, { name: "", price: "" }])}
                  >
                    <Plus className="size-3.5" /> Add a size
                  </Button>
                </div>
              ) : (
                <Input
                  type="number"
                  min={0}
                  placeholder="Price ₹"
                  className="w-40"
                  value={form.price}
                  onChange={(e) => set("price", e.target.value)}
                />
              )}
            </div>

            <Field label="Short description" hint="One line shown on the menu card and used while ordering.">
              <Input value={form.short_description} onChange={(e) => set("short_description", e.target.value)} />
            </Field>
            <Field
              label="Dish story"
              hint={`What ${restaurant.agent_name} says when a guest asks "what is this dish?" — taste, texture, how it's eaten. Leave empty and only the short description is used. Only write what's true: ${restaurant.agent_name} repeats this word for word.`}
            >
              <Textarea
                rows={5}
                value={form.long_description}
                onChange={(e) => set("long_description", e.target.value)}
              />
            </Field>
            <Field label="Ingredients" hint="Comma separated.">
              <Input value={form.ingredients} onChange={(e) => set("ingredients", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Allergens" hint="e.g. dairy, nuts, gluten">
                <Input value={form.allergens} onChange={(e) => set("allergens", e.target.value)} />
              </Field>
              <Field label="Tags" hint="e.g. bestseller, jain-friendly">
                <Input value={form.tags} onChange={(e) => set("tags", e.target.value)} />
              </Field>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
          <SheetFooter className="flex-row justify-end border-t">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save dish"}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
