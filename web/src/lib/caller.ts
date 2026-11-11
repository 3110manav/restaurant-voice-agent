/**
 * The caller's number for a demo store: asked for in a prompt when a call starts, kept for this browser tab,
 * and sent in request bodies (never in the URL). A typed number is not proof of who someone is, so the backend
 * only uses it for stores marked as demos, and never sends a WhatsApp message to it.
 */
const KEY = "sarthi.caller";
const SKIPPED = "skip";

let promptEnabled = false;

/** Set by the store page: only demo stores ask for a number. */
export function setCallerPromptEnabled(enabled: boolean) {
  promptEnabled = enabled;
}

export function callerPromptEnabled(): boolean {
  return promptEnabled;
}

function read(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** The number to send with requests, or undefined for an anonymous guest. */
export function getCallerPhone(): string | undefined {
  const value = typeof window === "undefined" ? null : read();
  return value && value !== SKIPPED ? value : undefined;
}

/** Has the guest already answered the prompt (with a number, or by skipping)? */
export function callerDecided(): boolean {
  return typeof window !== "undefined" && read() !== null;
}

/** Remember the answer: a number, or null for "continue without one". */
export function setCallerPhone(number: string | null) {
  try {
    window.sessionStorage.setItem(KEY, number ?? SKIPPED);
  } catch {
    /* private mode: the prompt just asks again next time */
  }
}

/** An Indian mobile number as +91XXXXXXXXXX, or null if it isn't one. */
export function normalizeNumber(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  const local =
    digits.length === 10 ? digits : digits.length === 11 && digits.startsWith("0") ? digits.slice(1) : digits.length === 12 && digits.startsWith("91") ? digits.slice(2) : null;
  return local && /^[6-9]\d{9}$/.test(local) ? `+91${local}` : null;
}

export function maskNumber(number: string): string {
  return number.length > 6 ? `${number.slice(0, 3)}••••••${number.slice(-3)}` : number;
}
