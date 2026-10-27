import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { CartLine, ServiceLogEntry } from "@/lib/api";
import { formatPrice } from "@/lib/utils";

function formatRequestType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function OrderPanel({
  cart,
  serviceLog,
  serviceLogLabel,
}: {
  cart: CartLine[];
  serviceLog: ServiceLogEntry[];
  serviceLogLabel: string | null;
}) {
  const total = cart.reduce((sum, line) => sum + line.price * line.quantity, 0);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Cart</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {cart.length === 0 ? (
            <p className="text-muted-foreground">Nothing in the cart yet.</p>
          ) : (
            <>
              {cart.map((line) => (
                <div key={`${line.id}|${line.variant ?? ""}`} className="flex justify-between gap-2">
                  <span>
                    {line.quantity} x {line.name}
                    {line.variant && <span className="text-muted-foreground"> ({line.variant})</span>}
                  </span>
                  <span className="text-muted-foreground">
                    {formatPrice(line.price * line.quantity)}
                  </span>
                </div>
              ))}
              <Separator className="my-1" />
              <div className="flex justify-between font-medium">
                <span>Total</span>
                <span>{formatPrice(total)}</span>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {serviceLogLabel && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">{serviceLogLabel}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            {serviceLog.length === 0 ? (
              <p className="text-muted-foreground">No requests yet.</p>
            ) : (
              serviceLog.map((entry, i) => (
                <div key={i} className="flex flex-col">
                  <span className="font-medium">{formatRequestType(entry.type)}</span>
                  {entry.details && (
                    <span className="text-muted-foreground">{entry.details}</span>
                  )}
                  {entry.notes && (
                    <span className="text-muted-foreground text-xs">{entry.notes}</span>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
