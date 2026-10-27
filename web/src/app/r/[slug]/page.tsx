import { Suspense } from "react";

import { RestaurantPage, RestaurantSkeleton } from "@/components/restaurant-page";

// Restaurants are created at runtime, so the slug can't be known at build time:
// the page shell prerenders and only this region waits for the request's params.
export default function RestaurantRoute({ params }: { params: Promise<{ slug: string }> }) {
  return (
    <Suspense fallback={<RestaurantSkeleton />}>
      <Restaurant params={params} />
    </Suspense>
  );
}

async function Restaurant({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <RestaurantPage slug={slug} />;
}
