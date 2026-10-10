"use client";

import { useEffect, useMemo, useState } from "react";
import { Minus, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { fetchMenu, type CartLine, type MenuItem } from "@/lib/api";
import type { Persona } from "@/lib/personas";

const VegMarker = ({ veg }: { veg: boolean }) => (
  <span
    className={cn(
      "inline-flex size-3.5 shrink-0 items-center justify-center rounded-[3px] border-2",
      veg ? "border-emerald-600" : "border-red-600"
    )}
    aria-label={veg ? "Vegetarian" : "Non-vegetarian"}
  >
    <span className={cn("size-1.5 rounded-full", veg ? "bg-emerald-600" : "bg-red-600")} />
  </span>
);

export function ProductGrid({
  persona,
  cart,
  onAdd,
  onRemove,
}: {
  persona: Persona;
  cart: CartLine[];
  onAdd: (itemId: string) => void;
  onRemove: (itemId: string) => void;
}) {
  const [items, setItems] = useState<MenuItem[] | null>(null);
  const [category, setCategory] = useState<string>("All");

  useEffect(() => {
    setItems(null);
    setCategory("All");
    fetchMenu(persona.key)
      .then(setItems)
      .catch(() => setItems([]));
  }, [persona.key]);

  const categories = useMemo(() => {
    if (!items) return [];
    return ["All", ...Array.from(new Set(items.map((i) => i.category)))];
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    return category === "All" ? items : items.filter((i) => i.category === category);
  }, [items, category]);

  const quantityById = useMemo(() => {
    const map = new Map<string, number>();
    for (const line of cart) map.set(line.id, line.quantity);
    return map;
  }, [cart]);

  if (items === null) {
    return (
      <div className="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-48 rounded-lg" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <div className="flex flex-wrap gap-2">
        {categories.map((c) => (
          <Button
            key={c}
            size="sm"
            variant={c === category ? "default" : "outline"}
            onClick={() => setCategory(c)}
          >
            {c}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {filtered.map((item) => {
          const quantity = quantityById.get(item.id) ?? 0;
          return (
            <Card key={item.id} className="flex flex-col">
              <CardHeader className="gap-1">
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-sm leading-tight">{item.name}</CardTitle>
                  {item.veg !== undefined && <VegMarker veg={item.veg} />}
                </div>
                {item.brand && (
                  <p className="text-xs font-medium text-muted-foreground">{item.brand}</p>
                )}
                <CardDescription className="line-clamp-2 text-xs">
                  {item.description}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-1 items-end justify-between gap-2">
                <span className="text-sm font-semibold">${item.price.toFixed(2)}</span>
                {item.spice_level ? (
                  <Badge variant="outline" className="text-[10px] capitalize">
                    {item.spice_level}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px]">
                    {item.category}
                  </Badge>
                )}
              </CardContent>
              <CardFooter>
                {quantity === 0 ? (
                  <Button size="sm" className="w-full" onClick={() => onAdd(item.id)}>
                    Add
                  </Button>
                ) : (
                  <div className="flex w-full items-center justify-between rounded-md border">
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => onRemove(item.id)}
                      aria-label={`Remove one ${item.name}`}
                    >
                      <Minus className="size-3.5" />
                    </Button>
                    <span className="text-sm font-medium">{quantity}</span>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => onAdd(item.id)}
                      aria-label={`Add one more ${item.name}`}
                    >
                      <Plus className="size-3.5" />
                    </Button>
                  </div>
                )}
              </CardFooter>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
