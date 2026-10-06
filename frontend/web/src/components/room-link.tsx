import Link from 'next/link';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';

interface RoomLinkProps {
  label: string;
  href: string;
  icon: LucideIcon;
  description: string;
  badge?: string;
}

export function RoomLink({ label, href, icon: Icon, description, badge }: RoomLinkProps) {
  return (
    <Link href={href}>
      <motion.div
        whileHover={{ x: 4, scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground/70 hover:bg-white/5 hover:text-foreground transition-all cursor-pointer group"
      >
        <Icon className="h-4 w-4 text-muted-foreground/50 group-hover:text-blue-400 transition-colors" />
        <div className="flex-1">
          <div className="font-medium">{label}</div>
          <div className="text-[10px] text-muted-foreground/40">{description}</div>
        </div>
        {badge && (
          <span className="h-4 px-1.5 text-[9px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30 rounded">
            {badge}
          </span>
        )}
      </motion.div>
    </Link>
  );
}
