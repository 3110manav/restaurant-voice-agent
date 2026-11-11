import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { tryLink, type Agent } from "@/lib/agents";

/** One agent in the bouquet on the landing page: who it helps, what problem it solves, and a way to try it. */
export function AgentCard({ agent }: { agent: Agent }) {
  const Icon = agent.icon;
  const link = tryLink(agent);
  const soon = agent.status === "soon";

  return (
    <article
      className={`flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-sm transition-shadow ${soon ? "border-dashed opacity-80" : "hover:shadow-md"}`}
      style={{ borderTopColor: agent.accent, borderTopWidth: 4 }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="flex size-11 shrink-0 items-center justify-center rounded-full text-white"
            style={{ backgroundColor: agent.accent }}
          >
            <Icon className="size-5" />
          </span>
          <div>
            <h3 className="text-xl leading-tight font-semibold">{agent.name}</h3>
            <p className="text-xs font-medium tracking-wide uppercase" style={{ color: agent.accent }}>
              {agent.works}
            </p>
          </div>
        </div>
        {soon && <span className="rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground">Coming next</span>}
      </div>

      <p className="text-sm text-muted-foreground">{agent.problem}</p>

      <ul className="flex flex-col gap-2 text-sm">
        {agent.does.map((line) => (
          <li key={line} className="flex gap-2">
            <Check className="mt-0.5 size-4 shrink-0" style={{ color: agent.accent }} />
            <span>{line}</span>
          </li>
        ))}
      </ul>

      {link && (
        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
          <Link
            href={link}
            className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg px-3 text-sm font-medium text-white transition-opacity hover:opacity-90"
            style={{ backgroundColor: agent.accent }}
          >
            Try {agent.name} <ArrowRight className="size-4" />
          </Link>
          <a href="#demo" className="text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
            {agent.stores.length === 1 ? "1 demo store" : `${agent.stores.length} demo stores`}
          </a>
        </div>
      )}
    </article>
  );
}
