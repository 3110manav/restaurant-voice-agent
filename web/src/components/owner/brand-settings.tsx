"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { brandTheme, contrastRatio, isHexColor, readableOn, type CornerStyle, type HeadingStyle, type ThemeMode } from "@/lib/brand";
import { updateRestaurant, type OwnerRestaurant } from "@/lib/owner-api";
import { cn } from "@/lib/utils";

function Choice<T extends string>({
  legend,
  value,
  options,
  onChange,
}: {
  legend: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            aria-pressed={o.value === value}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-9 rounded-lg border px-3 text-sm",
              o.value === value ? "border-foreground bg-foreground text-background" : "text-foreground"
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** The guest page's look, payment and review settings, with a live preview of the welcome card. */
export function BrandSettings({ restaurant, onChanged }: { restaurant: OwnerRestaurant; onChanged: () => Promise<void> }) {
  const [form, setForm] = useState({
    logo_url: restaurant.logo_url ?? "",
    theme_mode: (restaurant.theme_mode ?? "light") as ThemeMode,
    corner_style: (restaurant.corner_style ?? "soft") as CornerStyle,
    heading_style: (restaurant.heading_style ?? "modern") as HeadingStyle,
    google_review_url: restaurant.google_review_url ?? "",
    upi_id: restaurant.upi_id ?? "",
    upi_payee_name: restaurant.upi_payee_name ?? "",
    upi_is_merchant: Boolean(restaurant.upi_is_merchant),
    gst_rate: String(restaurant.gst_rate ?? 5),
    baseline_turn_minutes: restaurant.baseline_turn_minutes ? String(restaurant.baseline_turn_minutes) : "",
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => setForm((f) => ({ ...f, [key]: value }));

  const accent = isHexColor(restaurant.accent_color) ? restaurant.accent_color : "#b45309";
  const preview = brandTheme({ ...form, accent_color: accent });
  const textOnAccent = readableOn(accent) === "#ffffff" ? "white" : "dark";
  const lowOnLight = contrastRatio(accent, "#ffffff") < 3 && form.theme_mode === "light";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await updateRestaurant(restaurant.id, {
        ...form,
        gst_rate: Number(form.gst_rate),
        baseline_turn_minutes: form.baseline_turn_minutes ? Number(form.baseline_turn_minutes) : undefined,
      });
      setMessage("Saved. Guests see it on their next scan.");
      await onChanged();
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Guest page look, payments and reviews</CardTitle>
        <CardDescription>Guests see your name and look. Sarthi stays in the background.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-6 lg:grid-cols-[1fr_280px]">
          <div className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Logo link (https://…)</span>
              <Input value={form.logo_url} onChange={(e) => set("logo_url", e.target.value)} />
            </label>
            <p className="-mt-2 text-xs text-muted-foreground">
              Button text on your brand colour will be {textOnAccent} so guests can read it.
              {lowOnLight && " Your colour is light, so outlines may be hard to see on a light background."}
            </p>
            <Choice
              legend="Background"
              value={form.theme_mode}
              options={[{ value: "light", label: "Light" }, { value: "dark", label: "Dark" }]}
              onChange={(v) => set("theme_mode", v)}
            />
            <Choice
              legend="Corners"
              value={form.corner_style}
              options={[{ value: "sharp", label: "Sharp" }, { value: "soft", label: "Soft" }, { value: "round", label: "Round" }]}
              onChange={(v) => set("corner_style", v)}
            />
            <Choice
              legend="Heading style"
              value={form.heading_style}
              options={[{ value: "modern", label: "Modern" }, { value: "classic", label: "Classic" }, { value: "bold", label: "Bold" }]}
              onChange={(v) => set("heading_style", v)}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Business UPI ID</span>
                <Input value={form.upi_id} placeholder="name@bank" onChange={(e) => set("upi_id", e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Name on UPI</span>
                <Input value={form.upi_payee_name} onChange={(e) => set("upi_payee_name", e.target.value)} />
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4" checked={form.upi_is_merchant} onChange={(e) => set("upi_is_merchant", e.target.checked)} />
              This is a merchant UPI ID
            </label>
            <p className="-mt-2 text-xs text-muted-foreground">
              Without a UPI ID, guests are asked to pay at the counter. Staff confirm each payment on the Tonight screen.
            </p>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium">Google review link</span>
              <Input value={form.google_review_url} placeholder="https://g.page/r/…" onChange={(e) => set("google_review_url", e.target.value)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">GST on the bill (%)</span>
                <Input type="number" min={0} max={28} step={0.5} value={form.gst_rate} onChange={(e) => set("gst_rate", e.target.value)} />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="font-medium">Table time before Sarthi (min)</span>
                <Input
                  type="number"
                  min={1}
                  max={600}
                  value={form.baseline_turn_minutes}
                  placeholder="Time 20 tables by hand"
                  onChange={(e) => set("baseline_turn_minutes", e.target.value)}
                />
              </label>
            </div>
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save look and payments"}
              </Button>
              {message && <span className="text-sm text-muted-foreground">{message}</span>}
            </div>
          </div>

          <div aria-label="Preview of the guest page" className={cn("flex h-80 flex-col rounded-xl border p-4", preview.className)} style={preview.style}>
            <div className="flex flex-1 flex-col justify-center gap-3">
              {form.logo_url.startsWith("https://") ? (
                // eslint-disable-next-line @next/next/no-img-element -- the owner's logo, any host
                <img src={form.logo_url} alt="" className="size-12 rounded-md object-cover" />
              ) : (
                <div className="flex size-12 items-center justify-center rounded-[var(--radius)] bg-primary font-heading text-xl text-primary-foreground">
                  {restaurant.name.trim().charAt(0).toUpperCase()}
                </div>
              )}
              <p className="font-heading text-2xl leading-tight font-semibold">{restaurant.name}</p>
              <p className="text-sm">I&apos;m {restaurant.agent_name}, your waiter tonight. Tell me what you feel like eating.</p>
            </div>
            <div className="flex h-11 items-center justify-center rounded-[var(--radius)] bg-primary text-sm font-medium text-primary-foreground">
              Send to kitchen
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
