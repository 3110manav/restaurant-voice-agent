import Link from "next/link";

import { Hero } from "@/components/hero";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { PERSONAS } from "@/lib/personas";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <Hero />

      <section className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-6 py-16">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {PERSONAS.map((persona) => (
            <Card key={persona.slug}>
              <CardHeader>
                <CardTitle>
                  {persona.agentName}{" "}
                  <span className="font-normal text-muted-foreground">
                    · {persona.vertical}
                  </span>
                </CardTitle>
                <CardDescription>{persona.tagline}</CardDescription>
              </CardHeader>
              <CardContent>
                <Link href={`/chat/${persona.slug}`} className={buttonVariants()}>
                  Talk to {persona.agentName}
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
