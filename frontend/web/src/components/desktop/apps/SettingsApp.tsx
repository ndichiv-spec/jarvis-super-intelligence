'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Settings,
  Palette,
  Monitor,
  Bell,
  Shield,
  Wifi,
  Volume2,
  Battery,
  HardDrive,
  Cpu,
  MemoryStick,
  Eye,
  Moon,
  Sun,
  Check,
  ChevronRight,
  Layout,
  Type,
  MousePointer2,
  Globe,
  Key,
  Database,
} from 'lucide-react';

interface SettingItem {
  id: string;
  label: string;
  icon: React.ElementType;
  category: string;
}

const SETTINGS_ITEMS: SettingItem[] = [
  { id: 'appearance', label: 'Appearance', icon: Palette, category: 'General' },
  { id: 'display', label: 'Display', icon: Monitor, category: 'General' },
  { id: 'notifications', label: 'Notifications', icon: Bell, category: 'General' },
  { id: 'wallpaper', label: 'Wallpaper', icon: Eye, category: 'Personalization' },
  { id: 'theme', label: 'Theme', icon: Moon, category: 'Personalization' },
  { id: 'fonts', label: 'Fonts', icon: Type, category: 'Personalization' },
  { id: 'network', label: 'Network', icon: Wifi, category: 'System' },
  { id: 'sound', label: 'Sound', icon: Volume2, category: 'System' },
  { id: 'battery', label: 'Battery', icon: Battery, category: 'System' },
  { id: 'storage', label: 'Storage', icon: HardDrive, category: 'System' },
  { id: 'performance', label: 'Performance', icon: Cpu, category: 'System' },
  { id: 'memory', label: 'Memory', icon: MemoryStick, category: 'System' },
  { id: 'security', label: 'Security', icon: Shield, category: 'Privacy' },
  { id: 'privacy', label: 'Privacy', icon: Eye, category: 'Privacy' },
  { id: 'api-keys', label: 'API Keys', icon: Key, category: 'Developer' },
  { id: 'database', label: 'Database', icon: Database, category: 'Developer' },
];

const WALLPAPERS = [
  { id: 'default', name: 'Deep Space', gradient: 'from-slate-950 via-[#0a0f1a] to-slate-950' },
  { id: 'ocean', name: 'Ocean', gradient: 'from-blue-950 via-[#0a1628] to-cyan-950' },
  { id: 'aurora', name: 'Aurora', gradient: 'from-purple-950 via-[#0f0a1a] to-emerald-950' },
  { id: 'nebula', name: 'Nebula', gradient: 'from-indigo-950 via-[#120a28] to-rose-950' },
  { id: 'midnight', name: 'Midnight', gradient: 'from-gray-950 via-[#080810] to-slate-900' },
  { id: 'sunset', name: 'Sunset', gradient: 'from-orange-950 via-[#1a0a08] to-red-950' },
];

export default function SettingsApp() {
  const [activeCategory, setActiveCategory] = useState('General');
  const [selectedSetting, setSelectedSetting] = useState<string | null>(null);
  const [theme, setTheme] = useState('dark');
  const [accentColor, setAccentColor] = useState('blue');
  const [wallpaper, setWallpaper] = useState('default');
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [autoUpdate, setAutoUpdate] = useState(true);

  const categories = ['General', 'Personalization', 'System', 'Privacy', 'Developer'];

  const filteredSettings = SETTINGS_ITEMS.filter((s) => s.category === activeCategory);

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-56 border-r border-border/50 bg-card/30 flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50">
          <Settings className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Settings</span>
        </div>

        {/* Categories */}
        <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
          {categories.map((category) => (
            <button
              key={category}
              onClick={() => {
                setActiveCategory(category);
                setSelectedSetting(null);
              }}
              className={`w-full flex items-center justify-between px-4 py-2 text-sm transition-colors ${
                activeCategory === category
                  ? 'text-primary bg-primary/10'
                  : 'text-foreground/60 hover:text-foreground hover:bg-white/5'
              }`}
            >
              <span>{category}</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          ))}
        </div>

        {/* System Info */}
        <div className="p-3 border-t border-border/50">
          <div className="glass rounded-lg p-2 border border-border/30">
            <p className="text-[10px] text-foreground/40">JARVIS Desktop</p>
            <p className="text-xs font-mono text-primary">v3.0.0</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="p-6 max-w-2xl">
          <h2 className="text-lg font-semibold text-foreground mb-6">{activeCategory}</h2>

          {/* Settings Grid */}
          <div className="grid grid-cols-2 gap-3 mb-6">
            {filteredSettings.map((setting) => {
              const Icon = setting.icon;
              return (
                <motion.button
                  key={setting.id}
                  className={`flex items-center gap-3 p-4 rounded-xl border transition-all text-left ${
                    selectedSetting === setting.id
                      ? 'bg-primary/10 border-primary/30'
                      : 'bg-white/[0.02] border-border/30 hover:bg-white/5 hover:border-border/50'
                  }`}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setSelectedSetting(setting.id)}
                >
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary/20 to-accent/20 border border-primary/10 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-primary" />
                  </div>
                  <span className="text-sm text-foreground/80">{setting.label}</span>
                </motion.button>
              );
            })}
          </div>

          {/* Quick Settings */}
          <div className="glass rounded-xl border border-border/50 overflow-hidden">
            <h3 className="text-xs font-semibold text-foreground/50 uppercase tracking-wider px-4 py-3 border-b border-border/50">
              Quick Settings
            </h3>

            <div className="divide-y divide-border/50">
              {/* Theme Toggle */}
              <SettingRow label="Theme" description="Choose your preferred theme">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setTheme('light')}
                    className={`h-7 px-3 rounded-lg text-xs flex items-center gap-1.5 transition-all ${
                      theme === 'light'
                        ? 'bg-primary/20 text-primary border border-primary/30'
                        : 'bg-white/5 text-foreground/50 hover:text-foreground/70'
                    }`}
                  >
                    <Sun className="w-3.5 h-3.5" />
                    Light
                  </button>
                  <button
                    onClick={() => setTheme('dark')}
                    className={`h-7 px-3 rounded-lg text-xs flex items-center gap-1.5 transition-all ${
                      theme === 'dark'
                        ? 'bg-primary/20 text-primary border border-primary/30'
                        : 'bg-white/5 text-foreground/50 hover:text-foreground/70'
                    }`}
                  >
                    <Moon className="w-3.5 h-3.5" />
                    Dark
                  </button>
                </div>
              </SettingRow>

              {/* Notifications */}
              <SettingRow label="Notifications" description="Enable system notifications">
                <ToggleSwitch value={notificationsEnabled} onChange={setNotificationsEnabled} />
              </SettingRow>

              {/* Auto Update */}
              <SettingRow label="Auto Update" description="Automatically update the system">
                <ToggleSwitch value={autoUpdate} onChange={setAutoUpdate} />
              </SettingRow>

              {/* Accent Color */}
              <SettingRow label="Accent Color" description="Choose your accent color">
                <div className="flex items-center gap-1.5">
                  {['blue', 'purple', 'emerald', 'rose', 'amber'].map((color) => (
                    <button
                      key={color}
                      onClick={() => setAccentColor(color)}
                      className={`w-6 h-6 rounded-full transition-all ${
                        accentColor === color
                          ? 'ring-2 ring-primary ring-offset-2 ring-offset-background scale-110'
                          : 'hover:scale-110'
                      }`}
                      style={{
                        backgroundColor:
                          color === 'blue'
                            ? '#3b82f6'
                            : color === 'purple'
                              ? '#8b5cf6'
                              : color === 'emerald'
                                ? '#10b981'
                                : color === 'rose'
                                  ? '#f43f5e'
                                  : '#f59e0b',
                      }}
                    />
                  ))}
                </div>
              </SettingRow>
            </div>
          </div>

          {/* Wallpaper Picker */}
          <div className="glass rounded-xl border border-border/50 overflow-hidden mt-4">
            <h3 className="text-xs font-semibold text-foreground/50 uppercase tracking-wider px-4 py-3 border-b border-border/50">
              Wallpaper
            </h3>
            <div className="p-4">
              <div className="grid grid-cols-3 gap-2">
                {WALLPAPERS.map((wp) => (
                  <button
                    key={wp.id}
                    onClick={() => setWallpaper(wp.id)}
                    className={`relative h-16 rounded-lg bg-gradient-to-br ${wp.gradient} border-2 transition-all overflow-hidden ${
                      wallpaper === wp.id ? 'border-primary' : 'border-border/30 hover:border-border/50'
                    }`}
                  >
                    {wallpaper === wp.id && (
                      <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                        <Check className="w-5 h-5 text-white" />
                      </div>
                    )}
                    <span className="absolute bottom-1 left-2 text-[10px] text-white/70 font-medium">
                      {wp.name}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==================== Setting Row ====================

function SettingRow({
  label,
  description,
  children,
}: {
  label: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div>
        <p className="text-sm text-foreground/80">{label}</p>
        <p className="text-[10px] text-foreground/40">{description}</p>
      </div>
      {children}
    </div>
  );
}

// ==================== Toggle Switch ====================

function ToggleSwitch({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`relative w-10 h-5 rounded-full transition-colors ${
        value ? 'bg-primary' : 'bg-white/10'
      }`}
    >
      <motion.div
        className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow"
        animate={{ x: value ? 20 : 0 }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
    </button>
  );
}
