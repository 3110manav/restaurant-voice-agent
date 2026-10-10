"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShoppingBag, Zap, UtensilsCrossed, BedDouble } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { PERSONAS } from "@/lib/personas";

const ICONS = {
  online: ShoppingBag,
  "quick-commerce": Zap,
  waiter: UtensilsCrossed,
  hotel: BedDouble,
} as const;

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader>
        <Link href="/" className="px-2 py-1.5">
          <span className="text-lg font-semibold tracking-tight">Sarthi</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Assistants</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {PERSONAS.map((persona) => {
                const Icon = ICONS[persona.slug as keyof typeof ICONS];
                const href = `/chat/${persona.slug}`;
                return (
                  <SidebarMenuItem key={persona.slug}>
                    <SidebarMenuButton
                      render={<Link href={href} />}
                      isActive={pathname === href}
                    >
                      <Icon />
                      <span>
                        {persona.vertical} — {persona.agentName}
                      </span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
