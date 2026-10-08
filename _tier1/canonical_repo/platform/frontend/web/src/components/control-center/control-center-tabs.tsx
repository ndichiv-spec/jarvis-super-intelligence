"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Brain,
  Puzzle,
  Plug,
  Key,
  Shield,
  Settings,
  Activity,
  Terminal,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { TabConfig } from "@/lib/types/control-center";

export const CONTROL_CENTER_TABS: TabConfig[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "providers", label: "AI Providers", icon: Brain },
  { id: "extensions", label: "Extension Hub", icon: Puzzle },
  { id: "connections", label: "Connected Services", icon: Plug },
  { id: "credentials", label: "Credentials", icon: Key },
  { id: "permissions", label: "Permissions", icon: Shield },
  { id: "security", label: "Security", icon: Settings },
  { id: "diagnostics", label: "Diagnostics", icon: Activity },
  { id: "developer", label: "Developer Settings", icon: Terminal },
];

export function ControlCenterTabs({ children }: { children?: React.ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";

  const handleTabChange = (tabId: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tabId);
    router.push(`/dashboard/settings?${params.toString()}`);
  };

  return (
    <>
      <nav className="mb-6">
        <div className="flex flex-wrap gap-2 p-1 bg-muted/30 rounded-lg">
          {CONTROL_CENTER_TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium",
                  "transition-all duration-200",
                  "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
                  isActive
                    ? "bg-primary text-primary-foreground shadow-md"
                    : "text-muted-foreground hover:text-foreground hover:bg-accent"
                )}
              >
                <Icon className="h-4 w-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
      {children}
    </>
  );
}

export function TabContent({
  tabId,
  children,
}: {
  tabId: string;
  children: React.ReactNode;
}) {
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";
  if (activeTab !== tabId) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.15 }}
    >
      {children}
    </motion.div>
  );
}
