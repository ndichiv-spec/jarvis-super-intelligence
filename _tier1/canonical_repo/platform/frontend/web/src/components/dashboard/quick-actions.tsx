'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  MessageSquare, Activity, BarChart3,
  Globe,
} from 'lucide-react';

interface QuickAction {
  label: string;
  href: string;
  icon: React.ElementType;
  description: string;
  color: string;
}

const ACTIONS: QuickAction[] = [
  { label: 'Open Browser', href: '/dashboard/embedded-browser', icon: Globe, description: 'Embedded browser', color: 'from-blue-500 to-cyan-400' },
  { label: 'Open IDE', href: '/dashboard/self-reliant', icon: Activity, description: 'Self-Reliant IDE', color: 'from-purple-500 to-pink-400' },
  { label: 'Start Chat', href: '/dashboard', icon: MessageSquare, description: 'Neural conversation', color: 'from-emerald-500 to-teal-400' },
  { label: 'View Monitor', href: '/dashboard/monitoring', icon: BarChart3, description: 'System monitoring', color: 'from-amber-500 to-orange-400' },
];

export function QuickActions() {
  const router = useRouter();

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {ACTIONS.map((action) => {
        const Icon = action.icon;
        return (
          <motion.button
            key={action.href}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => router.push(action.href)}
            className="group relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.02] p-3 text-left transition-all hover:border-white/20 hover:bg-white/[0.04]"
          >
            <div className={`mb-2 inline-flex rounded-lg bg-gradient-to-br ${action.color} p-2 shadow-lg`}>
              <Icon className="h-4 w-4 text-white" />
            </div>
            <p className="text-sm font-medium text-foreground/80">{action.label}</p>
            <p className="text-[10px] text-muted-foreground/40">{action.description}</p>
          </motion.button>
        );
      })}
    </div>
  );
}
