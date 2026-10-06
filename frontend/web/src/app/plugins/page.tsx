"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Search, Plug, Download, Trash2, RefreshCw, Star, BookOpen, Package, Check, X } from "lucide-react";

interface Plugin {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  category: string;
  tags: string[];
  installed: boolean;
  enabled: boolean;
  downloads: number;
  rating: number;
}

const FEATURED_PLUGINS: Plugin[] = [
  {
    id: "weather",
    name: "Weather Integration",
    version: "1.2.0",
    description: "Get real-time weather data and forecasts for any location",
    author: "JARVIS Team",
    category: "Data",
    tags: ["weather", "api", "forecasts"],
    installed: false,
    enabled: false,
    downloads: 12500,
    rating: 4.8,
  },
  {
    id: "stock-market",
    name: "Stock Market Data",
    version: "2.0.0",
    description: "Real-time stock quotes, portfolio tracking, and alerts",
    author: "JARVIS Team",
    category: "Finance",
    tags: ["stocks", "finance", "market"],
    installed: false,
    enabled: false,
    downloads: 8900,
    rating: 4.6,
  },
  {
    id: "email-notify",
    name: "Email Notifications",
    version: "1.5.0",
    description: "Send and receive email notifications from JARVIS",
    author: "Community",
    category: "Communication",
    tags: ["email", "notifications"],
    installed: false,
    enabled: false,
    downloads: 5600,
    rating: 4.3,
  },
  {
    id: "code-assistant",
    name: "Code Assistant",
    version: "3.0.0",
    description: "Enhanced code generation, review, and debugging tools",
    author: "JARVIS Team",
    category: "Development",
    tags: ["code", "development", "assistant"],
    installed: false,
    enabled: false,
    downloads: 15000,
    rating: 4.9,
  },
  {
    id: "calendar-sync",
    name: "Calendar Sync",
    version: "1.1.0",
    description: "Sync with Google Calendar, Outlook, and more",
    author: "Community",
    category: "Productivity",
    tags: ["calendar", "scheduling"],
    installed: false,
    enabled: false,
    downloads: 4200,
    rating: 4.5,
  },
  {
    id: "slack-bot",
    name: "Slack Bot",
    version: "2.1.0",
    description: "Connect JARVIS to Slack for team collaboration",
    author: "JARVIS Team",
    category: "Communication",
    tags: ["slack", "bot", "team"],
    installed: false,
    enabled: false,
    downloads: 7800,
    rating: 4.7,
  },
  {
    id: "home-automation",
    name: "Home Automation",
    version: "1.0.0",
    description: "Control smart home devices (Philips Hue, Nest, etc.)",
    author: "Community",
    category: "IoT",
    tags: ["smart-home", "iot", "automation"],
    installed: false,
    enabled: false,
    downloads: 3200,
    rating: 4.4,
  },
  {
    id: "pdf-tools",
    name: "PDF Tools",
    version: "1.3.0",
    description: "Create, edit, and analyze PDF documents",
    author: "JARVIS Team",
    category: "Productivity",
    tags: ["pdf", "documents"],
    installed: false,
    enabled: false,
    downloads: 9200,
    rating: 4.6,
  },
];

const CATEGORIES = ["All", "Data", "Finance", "Communication", "Development", "Productivity", "IoT"];

export default function PluginMarketplacePage() {
  const [plugins, setPlugins] = useState<Plugin[]>(FEATURED_PLUGINS);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [loading, setLoading] = useState(false);

  const filteredPlugins = plugins.filter(p => {
    const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.tags.some(t => t.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesCategory = selectedCategory === "All" || p.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const installedPlugins = plugins.filter(p => p.installed);
  const availablePlugins = plugins.filter(p => !p.installed);

  const installPlugin = async (pluginId: string) => {
    setLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      setPlugins(prev => prev.map(p => 
        p.id === pluginId ? { ...p, installed: true, enabled: true } : p
      ));
      toast.success("Plugin installed successfully");
    } catch (error) {
      toast.error("Failed to install plugin");
    } finally {
      setLoading(false);
    }
  };

  const uninstallPlugin = async (pluginId: string) => {
    setLoading(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 500));
      
      setPlugins(prev => prev.map(p => 
        p.id === pluginId ? { ...p, installed: false, enabled: false } : p
      ));
      toast.success("Plugin uninstalled");
    } catch (error) {
      toast.error("Failed to uninstall plugin");
    } finally {
      setLoading(false);
    }
  };

  const togglePlugin = async (pluginId: string) => {
    setPlugins(prev => prev.map(p => 
      p.id === pluginId ? { ...p, enabled: !p.enabled } : p
    ));
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-3 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500">
          <Plug className="w-8 h-8 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">Plugin Marketplace</h1>
          <p className="text-muted-foreground">Extend JARVIS with plugins</p>
        </div>
      </div>

      <div className="flex gap-4 mb-6">
        <div className="flex-1">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search plugins..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>
        <Button variant="outline">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="browse" className="space-y-4">
        <TabsList>
          <TabsTrigger value="browse">Browse ({availablePlugins.length})</TabsTrigger>
          <TabsTrigger value="installed">Installed ({installedPlugins.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="browse">
          <div className="flex gap-2 mb-6">
            {CATEGORIES.map(cat => (
              <Button
                key={cat}
                variant={selectedCategory === cat ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedCategory(cat)}
              >
                {cat}
              </Button>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredPlugins.filter(p => !p.installed).map((plugin) => (
              <Card key={plugin.id}>
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <CardTitle className="text-lg">{plugin.name}</CardTitle>
                    <Badge variant="secondary">v{plugin.version}</Badge>
                  </div>
                  <CardDescription>{plugin.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2 mb-4">
                    <Badge variant="outline">{plugin.category}</Badge>
                    <div className="flex items-center gap-1">
                      <Star className="w-3 h-3 text-yellow-500" />
                      <span className="text-sm">{plugin.rating}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {plugin.downloads.toLocaleString()} downloads
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => installPlugin(plugin.id)}
                      disabled={loading}
                      className="flex-1"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      Install
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="installed">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {installedPlugins.map((plugin) => (
              <Card key={plugin.id}>
                <CardHeader className="pb-2">
                  <div className="flex justify-between items-start">
                    <CardTitle className="text-lg">{plugin.name}</CardTitle>
                    <Badge variant={plugin.enabled ? "default" : "secondary"}>
                      {plugin.enabled ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                  <CardDescription>{plugin.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2 mb-4 text-sm text-muted-foreground">
                    <span>v{plugin.version}</span>
                    <span>by {plugin.author}</span>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant={plugin.enabled ? "outline" : "default"}
                      onClick={() => togglePlugin(plugin.id)}
                      className="flex-1"
                    >
                      {plugin.enabled ? (
                        <>
                          <X className="w-4 h-4 mr-2" />
                          Disable
                        </>
                      ) : (
                        <>
                          <Check className="w-4 h-4 mr-2" />
                          Enable
                        </>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => uninstallPlugin(plugin.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}