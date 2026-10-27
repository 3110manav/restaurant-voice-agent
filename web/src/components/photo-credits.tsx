"use client";

import { useEffect, useState } from "react";

import { fetchPhotoCredits, type PhotoCredit } from "@/lib/api";

/**
 * "Photo credits" for a restaurant's menu. Openly licensed photos (CC BY and similar) must be
 * credited where they are shown; this lists them, and renders nothing when there are none.
 */
export function PhotoCredits({ slug }: { slug: string }) {
  const [credits, setCredits] = useState<PhotoCredit[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetchPhotoCredits(slug)
      .then((list) => {
        if (!cancelled) setCredits(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (credits.length === 0) return null;

  return (
    <details className="border-t px-4 py-3 text-xs text-muted-foreground">
      <summary className="w-fit cursor-pointer underline-offset-4 hover:underline">Photo credits</summary>
      <ul className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
        {credits.map((c) => (
          <li key={c.dish}>
            <span className="font-medium text-foreground">{c.dish}:</span>{" "}
            {c.page ? (
              <a href={c.page} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">
                {c.credit}
              </a>
            ) : (
              c.credit
            )}
            {c.license_url && (
              <>
                {" "}
                (
                <a href={c.license_url} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">
                  licence
                </a>
                )
              </>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
