export { cn } from "cn"

export function formatPrice(amount: number): string {
  return `₹${amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`
}
