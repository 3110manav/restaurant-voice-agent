import { Suspense } from "react";

import { RestaurantConsole } from "@/components/owner/restaurant-console";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata = { title: "Restaurant console — Sarthi" };

export default function ConsoleRoute({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-64" />}>
      <Console params={params} />
    </Suspense>
  );
}

async function Console({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RestaurantConsole id={id} />;
}
