"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain, Menu, X, Home, Activity, Bot, Atom, Mic, Layers,
  Settings, Bell, User, ChevronRight, Smartphone, Tablet, Monitor
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function MobileResponsiveDashboard() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [deviceType, setDeviceType] = useState<'mobile' | 'tablet' | 'desktop'>('desktop');

  // Detect device type
  React.useEffect(() => {
    const checkDevice = () => {
      const width = window.innerWidth;
      if (width < 768) {
        setDeviceType('mobile');
      } else if (width < 1024) {
        setDeviceType('tablet');
      } else {
        setDeviceType('desktop');
      }
    };

    checkDevice();
    window.addEventListener('resize', checkDevice);
    return () => window.removeEventListener('resize', checkDevice);
  }, []);

  const mobileMenuItems = [
    { icon: Home, label: "Overview", id: "overview" },
    { icon: Activity, label: "Dashboard", id: "dashboard" },
    { icon: Bot, label: "Advanced Agents", id: "agents" },
    { icon: Atom, label: "3D Visualization", id: "3d" },
    { icon: Mic, label: "Voice Interface", id: "voice" },
    { icon: Layers, label: "Tiers", id: "tiers" },
    { icon: Settings, label: "Settings", id: "settings" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950">
      {/* Mobile Header */}
      <div className="md:hidden sticky top-0 z-50 bg-slate-900/95 backdrop-blur border-b border-white/10">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-500 rounded-lg">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">JARVIS</h1>
              <p className="text-xs text-gray-400">Mobile Dashboard</p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="text-white">
              <Bell className="w-5 h-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="text-white"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            >
              {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile Menu */}
        <AnimatePresence>
          {isMobileMenuOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="p-4 space-y-2 border-t border-white/10">
                {mobileMenuItems.map((item) => (
                  <Button
                    key={item.id}
                    variant="ghost"
                    className="w-full justify-start text-white"
                    onClick={() => setIsMobileMenuOpen(false)}
                  >
                    <item.icon className="w-4 h-4 mr-3" />
                    {item.label}
                    <ChevronRight className="w-4 h-4 ml-auto" />
                  </Button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Device Type Indicator */}
      <div className="fixed bottom-4 right-4 z-50">
        <Badge className={`${
          deviceType === 'mobile' ? 'bg-blue-500' :
          deviceType === 'tablet' ? 'bg-purple-500' : 'bg-green-500'
        } text-white`}>
          {deviceType === 'mobile' && <Smartphone className="w-3 h-3 mr-1" />}
          {deviceType === 'tablet' && <Tablet className="w-3 h-3 mr-1" />}
          {deviceType === 'desktop' && <Monitor className="w-3 h-3 mr-1" />}
          {deviceType.charAt(0).toUpperCase() + deviceType.slice(1)}
        </Badge>
      </div>

      {/* Responsive Content Grid */}
      <div className="p-4 md:p-6 lg:p-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {/* System Status Card */}
          <Card className="bg-white/[0.02] border-white/5 col-span-1 md:col-span-2 lg:col-span-3">
            <CardHeader>
              <CardTitle className="text-lg md:text-xl">System Status</CardTitle>
              <CardDescription>Real-time JARVIS system metrics</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "CPU", value: "45%", color: "purple" },
                  { label: "Memory", value: "62%", color: "pink" },
                  { label: "Disk", value: "38%", color: "cyan" },
                  { label: "Network", value: "Active", color: "green" }
                ].map((metric, idx) => (
                  <div key={idx} className="p-3 bg-white/[0.02] rounded-lg">
                    <p className="text-xs text-gray-400 mb-1">{metric.label}</p>
                    <p className={`text-lg md:text-xl font-bold text-${metric.color}-400`}>
                      {metric.value}
                    </p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card className="bg-white/[0.02] border-white/5 col-span-1 md:col-span-2 lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-lg">Quick Actions</CardTitle>
              <CardDescription>Frequently used features</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { icon: Bot, label: "Agents", color: "purple" },
                  { icon: Atom, label: "3D View", color: "pink" },
                  { icon: Mic, label: "Voice", color: "cyan" },
                  { icon: Layers, label: "Tiers", color: "green" }
                ].map((action, idx) => (
                  <Button
                    key={idx}
                    variant="outline"
                    className="flex flex-col items-center gap-2 h-20 bg-white/[0.02] border-white/10 text-white hover:bg-white/[0.05]"
                  >
                    <action.icon className={`w-6 h-6 text-${action.color}-400`} />
                    <span className="text-xs">{action.label}</span>
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Active Agents */}
          <Card className="bg-white/[0.02] border-white/5 col-span-1 md:col-span-2 lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-lg">Active Agents</CardTitle>
              <CardDescription>Currently running advanced agents</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { name: "Quantum Core Agent", status: "Active", performance: 95 },
                  { name: "Neural Synthesis Agent", status: "Active", performance: 88 },
                  { name: "Global Knowledge Agent", status: "Active", performance: 92 }
                ].map((agent, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-white/[0.02] rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-purple-500/20 rounded-lg">
                        <Bot className="w-4 h-4 text-purple-400" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{agent.name}</p>
                        <p className="text-xs text-gray-400">{agent.status}</p>
                      </div>
                    </div>
                    <Badge className="bg-green-500">{agent.performance}%</Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Recent Activity */}
          <Card className="bg-white/[0.02] border-white/5 col-span-1 md:col-span-2 lg:col-span-3">
            <CardHeader>
              <CardTitle className="text-lg">Recent Activity</CardTitle>
              <CardDescription>Latest system events and updates</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { event: "Agent task completed", time: "2 min ago", type: "success" },
                  { event: "Knowledge graph updated", time: "5 min ago", type: "info" },
                  { event: "System optimization started", time: "10 min ago", type: "warning" },
                  { event: "New agent registered", time: "15 min ago", type: "success" }
                ].map((activity, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-white/[0.02] rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg ${
                        activity.type === 'success' ? 'bg-green-500/20' :
                        activity.type === 'warning' ? 'bg-yellow-500/20' :
                        'bg-blue-500/20'
                      }`}>
                        <Activity className={`w-4 h-4 ${
                          activity.type === 'success' ? 'text-green-400' :
                          activity.type === 'warning' ? 'text-yellow-400' :
                          'text-blue-400'
                        }`} />
                      </div>
                      <p className="text-sm text-white">{activity.event}</p>
                    </div>
                    <span className="text-xs text-gray-400">{activity.time}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900/95 backdrop-blur border-t border-white/10 p-2">
        <div className="grid grid-cols-5 gap-1">
          {[
            { icon: Home, label: "Home" },
            { icon: Bot, label: "Agents" },
            { icon: Atom, label: "3D" },
            { icon: Mic, label: "Voice" },
            { icon: Settings, label: "Settings" }
          ].map((item, idx) => (
            <Button
              key={idx}
              variant="ghost"
              className="flex flex-col items-center gap-1 h-16 text-white"
            >
              <item.icon className="w-5 h-5" />
              <span className="text-xs">{item.label}</span>
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
