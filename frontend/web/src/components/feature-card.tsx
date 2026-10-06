import React, { memo } from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, CheckCircle2, AlertCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';

interface FeatureCardProps {
  feature: {
    name: string;
    desc: string;
    icon: React.ElementType;
    href: string;
    status?: string;
    badge?: string;
  };
  categoryColor: string;
}

// Memoized Feature Card Component for Performance
export const FeatureCard = memo(function FeatureCard({ feature, categoryColor }: FeatureCardProps) {
  const FeatureIcon = feature.icon;
  
  return (
    <Link key={feature.name} href={feature.href}>
      <motion.div
        whileHover={{ scale: 1.05, y: -5 }}
        whileTap={{ scale: 0.98 }}
        className="group relative p-5 rounded-2xl glass border-holo hover:border-cyan-400/60 hover:bg-gradient-to-br hover:from-slate-800/90 hover:to-slate-900/90 transition-all duration-300 cursor-pointer holo-shimmer shadow-lg hover:shadow-2xl hover:shadow-cyan-500/20"
      >
        <div className="flex items-start gap-4">
          <div className={`h-12 w-12 rounded-xl bg-gradient-to-br ${categoryColor} opacity-90 group-hover:opacity-100 flex items-center justify-center flex-shrink-0 shadow-lg group-hover:scale-110 transition-transform duration-300 holo-shimmer`}>
            <FeatureIcon className="h-6 w-6 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="font-bold text-white text-base truncate drop-shadow">{feature.name}</h3>
              {feature.badge && (
                <Badge className={`h-5 px-2 text-[10px] font-bold shadow-lg hud-readout ${
                  feature.badge === 'LIVE'
                    ? 'bg-emerald-500/30 text-emerald-300 border-emerald-400/50 animate-pulse'
                    : feature.badge === 'NEW'
                    ? 'bg-cyan-500/30 text-cyan-300 border-cyan-400/50'
                    : feature.badge === 'OMEGA'
                    ? 'bg-purple-500/30 text-purple-300 border-purple-400/50'
                    : feature.badge === 'SUPREME'
                    ? 'bg-amber-500/30 text-amber-300 border-amber-400/50'
                    : 'bg-gray-500/30 text-gray-300 border-gray-400/50'
                }`}>
                  {feature.badge}
                </Badge>
              )}
            </div>
            <p className="text-sm text-cyan-100/70 line-clamp-2 leading-relaxed">{feature.desc}</p>
          </div>
          <ChevronRight className="h-5 w-5 text-cyan-400/50 group-hover:text-cyan-300 group-hover:translate-x-1 transition-all flex-shrink-0" />
        </div>

        {/* Real-time status indicator */}
        <div className="absolute top-4 right-4">
          {feature.status === 'active' ? (
            <div className="relative">
              <CheckCircle2 className="h-5 w-5 text-emerald-400 drop-shadow-lg" />
              <span className="absolute -top-1 -right-1 flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
              </span>
            </div>
          ) : feature.status === 'degraded' ? (
            <AlertCircle className="h-5 w-5 text-amber-400 drop-shadow-lg" />
          ) : (
            <AlertCircle className="h-5 w-5 text-red-400 drop-shadow-lg" />
          )}
        </div>

        {/* Glow effect on hover */}
        <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-cyan-500/0 to-teal-500/0 group-hover:from-cyan-500/10 group-hover:to-teal-500/10 transition-all duration-500 pointer-events-none" />
      </motion.div>
    </Link>
  );
});
