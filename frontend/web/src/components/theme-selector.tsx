"use client";

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Sparkles, Zap, Brain, Heart, Eye, Palette } from 'lucide-react';
import { useNeuralTheme, NEURAL_THEMES } from '@/lib/neural-theme-engine';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export function ThemeSelector() {
  const { themeId, setThemeId, autoThemeEnabled, setAutoThemeEnabled, mood } = useNeuralTheme();
  const [open, setOpen] = React.useState(false);

  const getThemeIcon = (id: string) => {
    switch (id) {
      case 'stark-holographic': return <Sparkles className="h-6 w-6" />;
      case 'quantum-deep': return <Brain className="h-6 w-6" />;
      case 'neural-cyan': return <Zap className="h-6 w-6" />;
      case 'arc-reactor': return <Eye className="h-6 w-6" />;
      case 'midnight-emerald': return <Heart className="h-6 w-6" />;
      case 'neural-rose': return <Palette className="h-6 w-6" />;
      default: return <Sparkles className="h-6 w-6" />;
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button 
          variant="ghost" 
          size="icon" 
          className="h-9 w-9 relative text-muted-foreground/60 hover:text-foreground transition-all hover:scale-110"
          title="Select Neural Theme"
        >
          <Palette className="h-5 w-5" />
          <span className="absolute -top-1 -right-1 flex h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-4 w-4 bg-gradient-to-br from-blue-500 to-cyan-400"></span>
          </span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-4xl bg-[hsl(222,47%,8%)] border-white/10 max-h-[80vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold bg-gradient-to-r from-blue-400 via-cyan-400 to-blue-400 bg-clip-text text-transparent flex items-center gap-3">
            <Palette className="h-7 w-7 text-blue-400" />
            Neural Theme Engine
          </DialogTitle>
          <DialogDescription className="text-cyan-200/60">
            Choose from 6 AI-reactive holographic themes. Themes can auto-switch based on AI mood detection.
          </DialogDescription>
        </DialogHeader>

        {/* Auto-Theme Toggle */}
        <div className="flex items-center justify-between p-4 rounded-xl bg-white/[0.03] border border-white/5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-500/20">
              <Brain className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <Label className="text-sm font-medium text-white">AI Mood Auto-Switching</Label>
              <p className="text-xs text-muted-foreground/60 mt-0.5">
                Automatically change theme based on conversation context
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {autoThemeEnabled && (
              <Badge className="bg-purple-500/20 text-purple-400 border-purple-500/30 text-xs">
                Current Mood: {mood}
              </Badge>
            )}
            <Switch
              checked={autoThemeEnabled}
              onCheckedChange={setAutoThemeEnabled}
            />
          </div>
        </div>

        <ScrollArea className="h-[500px] pr-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {NEURAL_THEMES.map((theme, index) => {
              const isActive = themeId === theme.id;
              const Icon = getThemeIcon(theme.id);
              
              return (
                <motion.div
                  key={theme.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.05 }}
                  whileHover={{ scale: 1.02, y: -2 }}
                  onClick={() => setThemeId(theme.id)}
                  className={`relative p-5 rounded-2xl cursor-pointer transition-all duration-300 border-2 ${
                    isActive
                      ? 'bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border-blue-400/60 shadow-lg shadow-blue-500/20'
                      : 'bg-gradient-to-br from-slate-900/80 to-slate-800/80 border-white/5 hover:border-white/10'
                  }`}
                >
                  {/* Active Indicator */}
                  {isActive && (
                    <motion.div
                      layoutId="activeTheme"
                      className="absolute top-3 right-3"
                    >
                      <div className="h-6 w-6 rounded-full bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center shadow-lg">
                        <Check className="h-4 w-4 text-white" />
                      </div>
                    </motion.div>
                  )}

                  {/* Theme Preview */}
                  <div className="flex items-start gap-4 mb-4">
                    <div 
                      className="h-14 w-14 rounded-xl flex items-center justify-center shadow-lg transition-transform hover:scale-110"
                      style={{
                        background: `linear-gradient(135deg, ${theme.colors.primary}30, ${theme.colors.accent}20)`,
                        border: `2px solid ${theme.colors.primary}40`,
                        color: theme.colors.primary
                      }}
                    >
                      {Icon}
                    </div>
                    <div className="flex-1">
                      <h3 className="font-bold text-white text-lg mb-1">{theme.name}</h3>
                      <p className="text-xs text-muted-foreground/60 line-clamp-2">{theme.description}</p>
                    </div>
                  </div>

                  {/* Color Palette Preview */}
                  <div className="flex gap-2 mb-4">
                    {[
                      theme.colors.primary,
                      theme.colors.secondary,
                      theme.colors.accent,
                      theme.colors.success,
                      theme.colors.background
                    ].map((color, idx) => (
                      <div
                        key={idx}
                        className="h-8 flex-1 rounded-lg shadow-inner"
                        style={{ backgroundColor: color }}
                        title={color}
                      />
                    ))}
                  </div>

                  {/* Theme Metadata */}
                  <div className="flex items-center justify-between text-xs text-muted-foreground/50">
                    <span>v{theme.version}</span>
                    <span>{theme.author}</span>
                  </div>

                  {/* Glow Effect on Hover */}
                  <div 
                    className="absolute inset-0 rounded-2xl opacity-0 hover:opacity-100 transition-opacity duration-500 pointer-events-none"
                    style={{
                      background: `radial-gradient(circle at 50% 0%, ${theme.colors.primaryGlow}, transparent 70%)`
                    }}
                  />
                </motion.div>
              );
            })}
          </div>
        </ScrollArea>

        {/* Footer */}
        <div className="mt-4 pt-4 border-t border-white/5">
          <div className="flex items-center justify-between text-xs text-muted-foreground/50">
            <span>💡 Tip: Enable AI Mood Auto-Switching for dynamic theming</span>
            <span>{NEURAL_THEMES.length} themes available</span>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
