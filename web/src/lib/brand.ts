import type { CSSProperties } from "react";

export type ThemeMode = "light" | "dark";
export type CornerStyle = "sharp" | "soft" | "round";
export type HeadingStyle = "modern" | "classic" | "bold";

export interface BrandSettings {
  accent_color?: string | null;
  theme_mode?: ThemeMode | null;
  corner_style?: CornerStyle | null;
  heading_style?: HeadingStyle | null;
}

const RADIUS: Record<CornerStyle, string> = { sharp: "0.25rem", soft: "0.625rem", round: "1rem" };

// System font stacks only: nothing to download, and they cover Hindi on phones.
const HEADING_FONT: Record<HeadingStyle, string> = {
  modern: "var(--font-sans)",
  classic: 'Georgia, "Noto Serif", "Times New Roman", serif',
  bold: '"Arial Black", "Helvetica Neue", Arial, sans-serif',
};

const DARK_TEXT = "#1a1205";
const WHITE = "#ffffff";

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

export function isHexColor(value: string | null | undefined): value is string {
  return Boolean(value && /^#[0-9a-fA-F]{6}$/.test(value));
}

/** White text on the brand colour when it reads well enough (4.5:1), otherwise near-black. */
export function readableOn(accent: string): string {
  return contrastRatio(accent, WHITE) >= 4.5 ? WHITE : DARK_TEXT;
}

/** The restaurant's look as CSS variables (and the dark class) for its guest pages. */
export function brandTheme(brand: BrandSettings): { className: string; style: CSSProperties } {
  const style: Record<string, string> = {
    "--radius": RADIUS[brand.corner_style ?? "soft"] ?? RADIUS.soft,
    "--font-heading": HEADING_FONT[brand.heading_style ?? "modern"] ?? HEADING_FONT.modern,
  };
  if (isHexColor(brand.accent_color)) {
    style["--primary"] = brand.accent_color;
    style["--primary-foreground"] = readableOn(brand.accent_color);
    style["--ring"] = brand.accent_color;
  }
  const dark = brand.theme_mode === "dark";
  return { className: dark ? "dark bg-background text-foreground" : "bg-background text-foreground", style: style as CSSProperties };
}
