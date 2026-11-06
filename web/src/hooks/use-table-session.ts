"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ChatSession } from "@/hooks/use-chat-session";
import {
  dismissTableSuggestion,
  fetchTableState,
  fetchTableSuggestion,
  markFoodServed,
  openTable,
  sendToKitchen,
  unsentLines,
  type TableContext,
  type TableSuggestion,
  type TableView,
} from "@/lib/api";

/**
 * The guest's table session (app/table/state.py): what went to the kitchen, what is still only in
 * the cart, and the suggestion card. It follows the cart, so an order placed by chat or voice shows
 * up here too. Inactive without a table number (a menu opened from a link, not a table's QR code).
 */
export function useTableSession(session: ChatSession) {
  const { sessionId, restaurant, tableNo, cart } = session;
  const ctx = useMemo<TableContext | null>(
    () => (sessionId && restaurant && tableNo ? { sessionId, restaurant, tableNo } : null),
    [restaurant, sessionId, tableNo]
  );
  const [table, setTable] = useState<TableView | null>(null);
  const [suggestion, setSuggestion] = useState<TableSuggestion | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The scan itself is the "seated" moment of the turn tracker.
  useEffect(() => {
    if (!ctx) return;
    let cancelled = false;
    openTable(ctx)
      .then((view) => !cancelled && setTable(view))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [ctx]);

  // The cart changed (a tap, the chat or a voice call): catch up on rounds and the next suggestion.
  useEffect(() => {
    if (!ctx) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchTableState(ctx)
        .then((view) => !cancelled && setTable(view))
        .catch(() => undefined);
      fetchTableSuggestion(ctx)
        .then((next) => !cancelled && setSuggestion(next))
        .catch(() => undefined);
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [cart, ctx]);

  const run = useCallback(async <T,>(action: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError((err as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const send = useCallback(async () => {
    if (!ctx) return;
    const result = await run(() => sendToKitchen(ctx));
    if (result) setTable(result.table);
  }, [ctx, run]);

  const foodServed = useCallback(async () => {
    if (!ctx) return;
    const view = await run(() => markFoodServed(ctx));
    if (view) setTable(view);
  }, [ctx, run]);

  const acceptSuggestion = useCallback(async () => {
    if (!suggestion) return;
    setSuggestion(null);
    await session.addItemDirect(suggestion.id, 1, undefined, { suggested: true });
  }, [session, suggestion]);

  const dismissSuggestion = useCallback(async () => {
    if (!ctx || !suggestion) return;
    setSuggestion(null);
    await dismissTableSuggestion(ctx, suggestion.id).catch(() => undefined);
  }, [ctx, suggestion]);

  const unsent = useMemo(() => unsentLines(cart, table?.ordered ?? []), [cart, table]);

  return {
    ctx,
    active: ctx !== null,
    table,
    unsent,
    suggestion,
    busy,
    error,
    setTable,
    send,
    foodServed,
    acceptSuggestion,
    dismissSuggestion,
    run,
  };
}

export type TableSession = ReturnType<typeof useTableSession>;
