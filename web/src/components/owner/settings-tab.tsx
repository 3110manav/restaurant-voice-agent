"use client";

import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { syncEmbeddings, updateRestaurant, type OwnerRestaurant } from "@/lib/owner-api";

export function SettingsTab({
  restaurant,
  onChanged,
}: {
  restaurant: OwnerRestaurant;
  onChanged: () => Promise<void>;
}) {
  const [form, setForm] = useState({
    name: restaurant.name,
    cuisine: restaurant.cuisine ?? "",
    tagline: restaurant.tagline ?? "",
    agent_name: restaurant.agent_name,
    accent_color: restaurant.accent_color ?? "#b45309",
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [table, setTable] = useState("1");
  const [origin, setOrigin] = useState("");
  const set = (key: keyof typeof form, value: string) => setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => setOrigin(window.location.origin), []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await updateRestaurant(restaurant.id, form);
      setMessage("Saved. New guest sessions use the updated details.");
      await onChanged();
    } catch (err) {
      setMessage((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function resync() {
    setSyncMessage("Checking…");
    try {
      const r = await syncEmbeddings(restaurant.id);
      setSyncMessage(`Done — ${r.embedded} dish(es) re-indexed, ${r.unchanged} already up to date.`);
    } catch (err) {
      setSyncMessage((err as Error).message);
    }
  }

  const link = `${origin}/r/${restaurant.slug}${table.trim() ? `?table=${encodeURIComponent(table.trim())}` : ""}`;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Restaurant details</CardTitle>
          <CardDescription>Shown to guests, and used by your waiter when it introduces itself.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={save} className="flex flex-col gap-3">
            <Input required placeholder="Name" value={form.name} onChange={(e) => set("name", e.target.value)} />
            <Input placeholder="Cuisine" value={form.cuisine} onChange={(e) => set("cuisine", e.target.value)} />
            <Input placeholder="Tagline" value={form.tagline} onChange={(e) => set("tagline", e.target.value)} />
            <Input
              required
              placeholder="Waiter's name"
              value={form.agent_name}
              onChange={(e) => set("agent_name", e.target.value)}
            />
            <label className="flex items-center gap-3 text-sm">
              Brand colour
              <input
                type="color"
                value={form.accent_color}
                onChange={(e) => set("accent_color", e.target.value)}
                className="h-8 w-12 rounded border"
              />
            </label>
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save changes"}
              </Button>
              {message && <span className="text-sm text-muted-foreground">{message}</span>}
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Table QR codes</CardTitle>
            <CardDescription>Guests scan it, the menu opens, and orders arrive tagged with the table.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <label className="flex items-center gap-2 text-sm">
              Table
              <Input className="w-24" value={table} onChange={(e) => setTable(e.target.value)} />
            </label>
            {origin && (
              <div className="flex items-center gap-4">
                <div className="rounded-lg border bg-white p-2">
                  <QRCodeSVG value={link} size={140} />
                </div>
                <div className="flex flex-col gap-2 text-xs break-all text-muted-foreground">
                  {link}
                  <Button size="sm" variant="outline" className="w-fit" onClick={() => navigator.clipboard.writeText(link)}>
                    Copy link
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Search index</CardTitle>
            <CardDescription>
              Every save keeps {restaurant.agent_name}&apos;s search up to date automatically. If a save ever reported that
              search would catch up later, this brings it in line — it only re-indexes dishes that changed.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-3">
            <Button size="sm" variant="outline" onClick={resync}>
              Re-sync search index
            </Button>
            {syncMessage && <span className="text-sm text-muted-foreground">{syncMessage}</span>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
