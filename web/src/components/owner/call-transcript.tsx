import type { TranscriptLine } from "@/lib/owner-api";
import { cn } from "@/lib/utils";

/** A phone call as a chat: the guest on the right, Kabir on the left. */
export function CallTranscript({ lines, empty }: { lines: TranscriptLine[]; empty?: string }) {
  if (lines.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty ?? "No transcript for this call."}</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {lines.map((line, i) => (
        <li
          key={i}
          className={cn(
            "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm",
            line.role === "user"
              ? "ml-auto rounded-br-sm bg-primary text-primary-foreground"
              : "rounded-bl-sm bg-muted"
          )}
        >
          <span className="mb-0.5 block text-[11px] opacity-70">
            {line.role === "user" ? "Guest" : line.role === "agent" ? "Kabir" : "Call"}
          </span>
          {line.text}
        </li>
      ))}
    </ul>
  );
}
