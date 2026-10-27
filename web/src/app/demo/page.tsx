import type { Metadata } from "next";

import { QrSheet } from "@/components/demo/qr-sheet";

export const metadata: Metadata = { title: "Demo QR codes — Sarthi" };

export default function DemoPage() {
  return <QrSheet />;
}
