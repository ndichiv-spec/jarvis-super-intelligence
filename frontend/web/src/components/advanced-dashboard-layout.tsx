'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import { useAdvancedTheme } from './advanced-theme-system';
import { GlassCard, AdvancedButton, AnimatedBackground, FloatingActionButton } from './advanced-ui-components';
import AdvancedJarvisLogo from './advanced-jarvis-logo';
import { 
  Brain, 
  Zap, 
  Shield, 
  Globe, 
  Cpu, 
  Activity,
  Settings,
  Menu,
  X,
  Layers,
  Sparkles,
  Terminal
} from 'lucide-react';

interface AdvancedDashboardLayoutProps {
  children: React.ReactNode;
}

export const AdvancedDashboardLayout: React.FC<AdvancedDashboardLayoutProps> = ({ children }) => {
  const { theme, currentTheme, setTheme, availableThemes } = useAdvancedTheme();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeSection, setActiveSection] = useState('overview');

  const navigationItems = [
    { id: 'overview', label: 'Neural Overview', icon: Brain },
    { id: 'cascade', label: 'Cascade AI', icon: Sparkles },
    { id: 'browser', label: 'Quantum Browser', icon: Globe },
    { id: 'desktop', label: 'Virtual Desktop', icon: Layers },
    { id: 'terminal', label: 'Neural Terminal', icon: Terminal },
    { id: 'monitor', label: 'System Monitor', icon: Activity },
    { id: 'settings', label: 'Quantum Settings', icon: Settings }
  ];

  const statsCards = [
    { title: 'Neural Processing', value: '98.7%', change: '+2.3%', icon: Cpu },
    { title: 'Quantum Coherence', value: '0.998', change: '+0.002', icon: Zap },
    { title: 'System Integrity', value: '100%', change: '0%', icon: Shield },
    { title: 'Active Connections', value: '1,247', change: '+142', icon: Globe }
  ];

  return (
    <AnimatedBackground>
      <div className="min-h-screen flex">
        {/* Advanced Sidebar */}
        <AnimatePresence>
          {sidebarOpen && (
            <motion.aside
              initial={{ x: -300, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -300, opacity: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              className="w-80 h-screen fixed left-0 top-0 z-40"
            >
              <GlassCard className="h-full m-4 flex flex-col">
                {/* Logo Section */}
                <div className="flex items-center justify-between mb-8">
                  <div className="flex items-center space-x-3">
                    <AdvancedJarvisLogo variant="quantum" size="md" />
                    <div>
                      <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-600 bg-clip-text text-transparent">
                        JARVIS
                      </h1>
                      <p className="text-xs opacity-70">Quantum Intelligence</p>
                    </div>
                  </div>
                  <AdvancedButton
                    variant="neon"
                    size="sm"
                    onClick={() => setSidebarOpen(false)}
                  >
                    <X className="w-4 h-4" />
                  </AdvancedButton>
                </div>

                {/* Theme Selector */}
                <div className="mb-8">
                  <h3 className="text-sm font-medium mb-3 opacity-70">Neural Theme</h3>
                  <div className="grid grid-cols-2 gap-2">
                    {availableThemes.map((themeName) => (
                      <motion.button
                        key={themeName}
                        className={cn(
                          'px-3 py-2 rounded-lg text-xs font-medium transition-all',
                          currentTheme === themeName
                            ? 'bg-gradient-to-r from-blue-500 to-purple-600 text-white'
                            : 'bg-white/10 text-white/70 hover:bg-white/20'
                        )}
                        onClick={() => setTheme(themeName)}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                      >
                        {themeName.split('-').map(word => 
                          word.charAt(0).toUpperCase() + word.slice(1)
                        ).join(' ')}
                      </motion.button>
                    ))}
                  </div>
                </div>

                {/* Navigation */}
                <nav className="flex-1">
                  <h3 className="text-sm font-medium mb-4 opacity-70">Neural Navigation</h3>
                  <div className="space-y-2">
                    {navigationItems.map((item) => {
                      const Icon = item.icon;
                      return (
                        <motion.button
                          key={item.id}
                          className={cn(
                            'w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all',
                            activeSection === item.id
                              ? 'bg-gradient-to-r from-blue-500/20 to-purple-600/20 border-l-4 border-blue-400'
                              : 'hover:bg-white/10'
                          )}
                          onClick={() => setActiveSection(item.id)}
                          whileHover={{ x: 5 }}
                          transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                        >
                          <Icon className="w-5 h-5" style={{ color: theme.colors.primary }} />
                          <span className="text-sm font-medium">{item.label}</span>
                        </motion.button>
                      );
                    })}
                  </div>
                </nav>

                {/* System Stats */}
                <div className="mt-8 space-y-3">
                  <h3 className="text-sm font-medium mb-3 opacity-70">Neural Statistics</h3>
                  {statsCards.map((stat, index) => (
                    <motion.div
                      key={stat.title}
                      className="flex items-center justify-between p-3 rounded-lg bg-white/5"
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.1 }}
                    >
                      <div className="flex items-center space-x-2">
                        <stat.icon className="w-4 h-4" style={{ color: theme.colors.primary }} />
                        <span className="text-xs">{stat.title}</span>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold">{stat.value}</div>
                        <div className="text-xs text-green-400">{stat.change}</div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </GlassCard>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* Main Content Area */}
        <div className={cn('flex-1 transition-all duration-300', sidebarOpen ? 'ml-80' : 'ml-0')}>
          {/* Header */}
          <motion.header
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="sticky top-0 z-30 backdrop-blur-xl bg-white/5 border-b border-white/10"
          >
            <div className="flex items-center justify-between p-6">
              <div className="flex items-center space-x-4">
                {!sidebarOpen && (
                  <AdvancedButton
                    variant="neon"
                    size="sm"
                    onClick={() => setSidebarOpen(true)}
                  >
                    <Menu className="w-4 h-4" />
                  </AdvancedButton>
                )}
                <div>
                  <h2 className="text-2xl font-bold">Neural Command Center</h2>
                  <p className="text-sm opacity-70">Advanced AI Interface</p>
                </div>
              </div>

              <div className="flex items-center space-x-4">
                <AdvancedButton variant="holographic" size="sm">
                  <Sparkles className="w-4 h-4 mr-2" />
                  Enhance
                </AdvancedButton>
                <AdvancedButton variant="glow" size="sm">
                  <Zap className="w-4 h-4 mr-2" />
                  Boost
                </AdvancedButton>
              </div>
            </div>
          </motion.header>

          {/* Page Content */}
          <main className="p-6">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              {children}
            </motion.div>
          </main>
        </div>

        {/* Floating Action Button */}
        <FloatingActionButton position="bottom-right">
          <Terminal className="w-6 h-6 text-white" />
        </FloatingActionButton>
      </div>
    </AnimatedBackground>
  );
};
