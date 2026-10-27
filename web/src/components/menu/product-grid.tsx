"use client";

import { useEffect, useMemo, useState } from "react";
import { Minus, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { dishEmoji } from "@/lib/dish-emoji";
import { cn, formatPrice } from "@/lib/utils";
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

/** A dish photo, or a food tile (an emoji on the restaurant's accent colour) when there is none or it fails to load. */
function DishImage({ src, name, category }: { src?: string | null; name: string; category?: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="relative aspect-[4/3] w-full overflow-hidden bg-gradient-to-br from-primary/20 via-primary/10 to-primary/5">
      {src && !failed ? (
        // Plain <img>: photos live on arbitrary hosts (a restaurant's own CDN, Supabase Storage).
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={name}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="size-full object-cover transition-transform duration-300 group-hover/card:scale-105"
        />
      ) : (
        <div className="flex size-full items-center justify-center text-5xl drop-shadow-sm sm:text-6xl" role="img" aria-label={name}>
          {dishEmoji(name, category)}
        </div>
      )}
    </div>
  );
}

const lineKey = (id: string, variant?: string) => `${id}|${variant ?? ""}`;

function AddControl({
  quantity,
  label,
  onAdd,
  onRemove,
  compact = false,
}: {
  quantity: number;
  label: string;
  onAdd: () => void;
  onRemove: () => void;
  compact?: boolean;
}) {
  if (quantity === 0) {
    return (
      <Button size="sm" className={compact ? "w-20" : "w-full"} onClick={onAdd} aria-label={`Add ${label}`}>
        Add
      </Button>
    );
  }
  return (
    <div className={cn("flex items-center justify-between rounded-md border", compact ? "w-20" : "w-full")}>
      <Button size="icon-sm" variant="ghost" onClick={onRemove} aria-label={`Remove one ${label}`}>
        <Minus className="size-3.5" />
      </Button>
      <span className="text-sm font-medium">{quantity}</span>
      <Button size="icon-sm" variant="ghost" onClick={onAdd} aria-label={`Add one more ${label}`}>
        <Plus className="size-3.5" />
      </Button>
    </div>
  );
}

function DishCard({
  item,
  quantityOf,
  onAdd,
  onRemove,
}: {
  item: MenuItem;
  quantityOf: (id: string, variant?: string) => number;
  onAdd: (itemId: string, variant?: string) => void;
  onRemove: (itemId: string, variant?: string) => void;
}) {
  const [showStory, setShowStory] = useState(false);
  const variants = item.variants ?? [];
  const unavailable = item.is_available === false;

  return (
    <Card className={cn("flex flex-col pt-0", unavailable && "opacity-60")}>
      <DishImage src={item.image_url} name={item.name} category={item.category} />
      <CardHeader className="gap-1">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm leading-tight">{item.name}</CardTitle>
          {item.veg !== undefined && <VegMarker veg={item.veg} />}
        </div>
        {item.brand && <p className="text-xs font-medium text-muted-foreground">{item.brand}</p>}
        <CardDescription className="line-clamp-2 text-xs">{item.description}</CardDescription>
        {item.long_description && (
          <button
            type="button"
            onClick={() => setShowStory((open) => !open)}
            className="w-fit text-xs text-primary underline-offset-4 hover:underline"
          >
            {showStory ? "Hide details" : "About this dish"}
          </button>
        )}
        {showStory && (
          <div className="flex flex-col gap-1 text-xs text-muted-foreground">
            <p>{item.long_description}</p>
            {item.allergens && item.allergens.length > 0 && <p>Contains: {item.allergens.join(", ")}</p>}
          </div>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 items-end justify-between gap-2">
        {variants.length === 0 ? (
          <span className="text-sm font-semibold">{formatPrice(item.price)}</span>
        ) : (
          <span className="text-xs text-muted-foreground">Pick a size</span>
        )}
        {unavailable ? (
          <Badge variant="outline" className="text-[10px]">
            Unavailable
          </Badge>
        ) : item.spice_level && item.spice_level !== "none" ? (
          <Badge variant="outline" className="text-[10px] capitalize">
            {item.spice_level}
          </Badge>
        ) : (
          <Badge variant="outline" className="text-[10px]">
            {item.category}
          </Badge>
        )}
      </CardContent>
      <CardFooter className="flex-col gap-2">
        {unavailable ? (
          <Button size="sm" className="w-full" disabled>
            Unavailable
          </Button>
        ) : variants.length === 0 ? (
          <AddControl
            quantity={quantityOf(item.id)}
            label={item.name}
            onAdd={() => onAdd(item.id)}
            onRemove={() => onRemove(item.id)}
          />
        ) : (
          variants.map((v) => (
            <div key={v.name} className="flex w-full items-center justify-between gap-2">
              <span className="text-xs">
                {v.name} · <span className="font-semibold">{formatPrice(v.price)}</span>
              </span>
              <AddControl
                compact
                quantity={quantityOf(item.id, v.name)}
                label={`${item.name} (${v.name})`}
                onAdd={() => onAdd(item.id, v.name)}
                onRemove={() => onRemove(item.id, v.name)}
              />
            </div>
          ))
        )}
      </CardFooter>
    </Card>
  );
}

export function ProductGrid({
  persona,
  restaurant,
  cart,
  onAdd,
  onRemove,
}: {
  persona: Persona;
  /** A restaurant slug: show that restaurant's menu instead of a legacy catalog. */
  restaurant?: string;
  cart: CartLine[];
  onAdd: (itemId: string, variant?: string) => void;
  onRemove: (itemId: string, variant?: string) => void;
}) {
  const [items, setItems] = useState<MenuItem[] | null>(null);
  const [category, setCategory] = useState<string>("All");
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    setItems(null);
    setCategory("All");
    setLoadError(false);
    fetchMenu(persona.key, restaurant)
      .then(setItems)
      .catch(() => {
        setItems([]);
        setLoadError(true);
      });
  }, [persona.key, restaurant]);

  const categories = useMemo(() => {
    if (!items) return [];
    return ["All", ...Array.from(new Set(items.map((i) => i.category)))];
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    return category === "All" ? items : items.filter((i) => i.category === category);
  }, [items, category]);

  const quantities = useMemo(() => {
    const map = new Map<string, number>();
    for (const line of cart) map.set(lineKey(line.id, line.variant), line.quantity);
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

  if (loadError) {
    return (
      <p className="p-6 text-sm text-muted-foreground">
        Couldn&apos;t load the menu right now. If the server was asleep, give it a minute and refresh.
      </p>
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
        {filtered.map((item) => (
          <DishCard
            key={item.id}
            item={item}
            quantityOf={(id, variant) => quantities.get(lineKey(id, variant)) ?? 0}
            onAdd={onAdd}
            onRemove={onRemove}
          />
        ))}
      </div>
    </div>
  );
}
