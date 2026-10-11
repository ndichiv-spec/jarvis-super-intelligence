"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Library, Search, TrendingUp, Globe, BookOpen, Code2,
  Newspaper, MessageSquare, GraduationCap, Github, FileText,
  ExternalLink, Clock, Filter, RefreshCw,
  Star
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { format } from "date-fns";
import { jarvisAPI } from "@/lib/api";

interface KnowledgeItem {
  id: string;
  title: string;
  source: string;
  url?: string;
  summary?: string;
  content?: string;
  published_at?: string;
  relevance_score?: number;
  tags?: string[];
  category?: string;
}

interface TrendingTopic {
  topic: string;
  mention_count: number;
  trend_direction: "up" | "down" | "stable";
  percentage_change: number;
  sources: string[];
  first_seen: string;
  last_seen: string;
}

interface Source {
  name: string;
  icon: React.ElementType;
  color: string;
  description: string;
  item_count?: number;
  status?: "active" | "error" | "disabled";
}

const SOURCES: Source[] = [
  { name: "DuckDuckGo", icon: Globe, color: "text-blue-400", description: "Web search", item_count: 0 },
  { name: "Wikipedia", icon: BookOpen, color: "text-gray-400", description: "Encyclopedia", item_count: 0 },
  { name: "arXiv", icon: GraduationCap, color: "text-red-400", description: "Research papers", item_count: 0 },
  { name: "GitHub", icon: Github, color: "text-purple-400", description: "Code repositories", item_count: 0 },
  { name: "Google News", icon: Newspaper, color: "text-blue-400", description: "News articles", item_count: 0 },
  { name: "Reddit", icon: MessageSquare, color: "text-orange-400", description: "Community discussions", item_count: 0 },
  { name: "Hacker News", icon: Code2, color: "text-orange-400", description: "Tech news", item_count: 0 },
  { name: "PubMed", icon: FileText, color: "text-green-400", description: "Medical research", item_count: 0 },
  { name: "StackOverflow", icon: Code2, color: "text-yellow-400", description: "Developer Q&A", item_count: 0 },
];

const SOURCE_COLORS: Record<string, string> = {
  "DuckDuckGo": "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "Wikipedia": "bg-gray-500/20 text-gray-400 border-gray-500/30",
  "arXiv": "bg-red-500/20 text-red-400 border-red-500/30",
  "GitHub": "bg-purple-500/20 text-purple-400 border-purple-500/30",
  "Google News": "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "Reddit": "bg-orange-500/20 text-orange-400 border-orange-500/30",
  "Hacker News": "bg-orange-500/20 text-orange-400 border-orange-500/30",
  "PubMed": "bg-green-500/20 text-green-400 border-green-500/30",
  "StackOverflow": "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
};

export default function KnowledgeHubPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [trendingTopics, setTrendingTopics] = useState<TrendingTopic[]>([]);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);
  const [trendingError, setTrendingError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    loadKnowledge();
    loadTrending();
  }, []);

  const loadKnowledge = async () => {
    try {
      setIsLoading(true);
      setKnowledgeError(null);
      const data = await jarvisAPI.globalTrends(50);
      setKnowledgeItems(data.items || data.results || []);
    } catch (error) {
      console.error("Failed to load knowledge:", error);
      setKnowledgeItems([]);
      setKnowledgeError(error instanceof Error ? error.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  };

  const loadTrending = async () => {
    try {
      setTrendingError(null);
      const data = await jarvisAPI.globalTrends(20);
      setTrendingTopics(data.trends || data.trending || []);
    } catch (error) {
      console.error("Failed to load trends:", error);
      setTrendingTopics([]);
      setTrendingError(error instanceof Error ? error.message : "Unknown error");
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      toast.error("Please enter a search query");
      return;
    }

    try {
      setIsSearching(true);
      setSearchError(null);
      toast.info(`Searching across ${selectedSources.length || 9} sources...`);

      const sources = selectedSources.length > 0 ? selectedSources.join(",") : undefined;
      const data = await jarvisAPI.globalKnowledgeSearch(searchQuery, sources, 20);

      setKnowledgeItems(data.items || data.results || []);
      toast.success(`Found ${data.items?.length || data.results?.length || 0} results`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setSearchError(message);
      toast.error(`Search failed: ${message}`);
    } finally {
      setIsSearching(false);
    }
  };

  const filteredItems = knowledgeItems.filter((item) => {
    const matchesSearch =
      item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.summary?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.tags?.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()));

    if (activeTab === "all") return matchesSearch;
    if (activeTab === "research") return item.category === "research" && matchesSearch;
    if (activeTab === "tech") return item.category === "tech" && matchesSearch;
    if (activeTab === "programming") return item.category === "programming" && matchesSearch;
    if (activeTab === "science") return item.category === "science" && matchesSearch;

    if (selectedSources.length > 0) {
      return matchesSearch && selectedSources.includes(item.source);
    }

    return matchesSearch;
  });

  const getSourceIcon = (sourceName: string) => {
    const source = SOURCES.find((s) => s.name === sourceName);
    const Icon = source?.icon || Globe;
    const color = source?.color || "text-gray-400";
    return <Icon className={`h-4 w-4 ${color}`} />;
  };

  const getSourceBadge = (source: string) => {
    const colorClass = SOURCE_COLORS[source] || "bg-gray-500/20 text-gray-400 border-gray-500/30";
    return (
      <Badge className={`${colorClass} border`}>
        {getSourceIcon(source)}
        <span className="ml-1">{source}</span>
      </Badge>
    );
  };

  const toggleSource = (sourceName: string) => {
    setSelectedSources((prev) =>
      prev.includes(sourceName) ? prev.filter((s) => s !== sourceName) : [...prev, sourceName]
    );
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-orange-400 bg-clip-text text-transparent">
            Knowledge Hub
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Browse indexed knowledge and search supported sources
          </p>
        </div>
        <Button variant="outline" onClick={loadKnowledge} disabled={isLoading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </motion.div>

      {/* Source Overview */}
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="text-lg">Knowledge Sources</CardTitle>
          <CardDescription>
            Select sources to include in the search request
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 md:grid-cols-9 gap-3">
            {SOURCES.map((source, i) => {
              const Icon = source.icon;
              const isSelected = selectedSources.includes(source.name);
              return (
                <motion.button
                  key={source.name}
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.05 }}
                  onClick={() => toggleSource(source.name)}
                  className={`p-3 rounded-lg border transition-all text-center ${
                    isSelected
                      ? "border-blue-500/50 bg-blue-500/10"
                      : "border-white/5 bg-white/[0.02] hover:border-white/10"
                  }`}
                >
                  <Icon className={`h-6 w-6 mx-auto mb-1 ${source.color}`} />
                  <p className="text-xs font-medium truncate">{source.name}</p>
                  <p className="text-[10px] text-muted-foreground/40">{source.description}</p>
                </motion.button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Search Bar */}
      <Card className="bg-white/[0.02] border-white/5">
        <CardContent className="p-4">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/40" />
              <Input
                className="pl-10 bg-white/[0.02] border-white/5"
                placeholder="Search across all knowledge sources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
            </div>
            <Button
              onClick={handleSearch}
              disabled={isSearching}
              className="bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600"
            >
              <Search className="mr-2 h-4 w-4" />
              Search
            </Button>
          </div>
        </CardContent>
      </Card>
      {searchError && (
        <p role="alert" className="text-sm text-red-400">
          Search is unavailable: {searchError}
        </p>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex items-center justify-between">
          <TabsList className="bg-white/[0.02] border-white/5">
            <TabsTrigger value="all" className="text-sm">
              <Library className="mr-2 h-4 w-4" />
              All
            </TabsTrigger>
            <TabsTrigger value="trending" className="text-sm">
              <TrendingUp className="mr-2 h-4 w-4" />
              Trending
            </TabsTrigger>
            <TabsTrigger value="research" className="text-sm">
              <GraduationCap className="mr-2 h-4 w-4" />
              Research
            </TabsTrigger>
            <TabsTrigger value="tech" className="text-sm">
              <Globe className="mr-2 h-4 w-4" />
              Tech
            </TabsTrigger>
            <TabsTrigger value="programming" className="text-sm">
              <Code2 className="mr-2 h-4 w-4" />
              Programming
            </TabsTrigger>
          </TabsList>

          {selectedSources.length > 0 && (
            <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
              <Filter className="mr-1 h-3 w-3" />
              {selectedSources.length} source{selectedSources.length > 1 ? "s" : ""} selected
            </Badge>
          )}
        </div>

        {/* All Knowledge Tab */}
        <TabsContent value="all" className="mt-4">
          <ScrollArea className="h-[600px]">
            <div className="space-y-3">
              {isLoading ? (
                <div className="flex items-center justify-center py-20">
                  <RefreshCw className="h-8 w-8 animate-spin text-blue-400" />
                </div>
              ) : knowledgeError ? (
                <div role="alert" className="text-center py-20">
                  <p className="text-sm text-red-400">Knowledge data is unavailable: {knowledgeError}</p>
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="text-center py-20">
                  <Library className="h-16 w-16 text-muted-foreground/20 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-muted-foreground/60 mb-2">
                    No knowledge items found
                  </h3>
                  <p className="text-sm text-muted-foreground/40">
                    Try adjusting your search or filters
                  </p>
                </div>
              ) : (
                filteredItems.map((item, i) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <Card className="bg-white/[0.02] border-white/5 hover:border-purple-500/20 transition-all">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              {getSourceBadge(item.source)}
                              {item.relevance_score && (
                                <Badge variant="outline" className="text-xs">
                                  <Star className="mr-1 h-3 w-3 text-amber-400" />
                                  {item.relevance_score}%
                                </Badge>
                              )}
                            </div>
                            <h3 className="text-lg font-semibold mb-1">{item.title}</h3>
                            {item.summary && (
                              <p className="text-sm text-muted-foreground/60 mb-2">{item.summary}</p>
                            )}
                            {item.tags && item.tags.length > 0 && (
                              <div className="flex gap-1 flex-wrap">
                                {item.tags.map((tag, idx) => (
                                  <Badge key={idx} variant="outline" className="text-[10px] bg-white/[0.02]">
                                    {tag}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            {item.url && (
                              <Button variant="ghost" size="sm" asChild>
                                <a href={item.url} target="_blank" rel="noopener noreferrer">
                                  <ExternalLink className="h-4 w-4" />
                                </a>
                              </Button>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-muted-foreground/40 mt-3">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {item.published_at ? format(new Date(item.published_at), "MMM d, HH:mm") : "Unknown"}
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Trending Tab */}
        <TabsContent value="trending" className="mt-4">
          <Card className="bg-gradient-to-br from-orange-500/5 to-pink-500/5 border-orange-500/10">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-orange-400" />
                Trending Topics
              </CardTitle>
              <CardDescription>
                Topics gaining momentum across knowledge sources
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {trendingError ? (
                  <p role="alert" className="py-8 text-center text-sm text-red-400">
                    Trending data is unavailable: {trendingError}
                  </p>
                ) : trendingTopics.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">No trending topics were returned.</p>
                ) : trendingTopics.map((trend, i) => (
                  <motion.div
                    key={trend.topic}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                  >
                    <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5 hover:border-orange-500/20 transition-all">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h4 className="text-lg font-bold">{trend.topic}</h4>
                            <Badge
                              className={
                                trend.trend_direction === "up"
                                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                                  : trend.trend_direction === "down"
                                  ? "bg-red-500/20 text-red-400 border-red-500/30"
                                  : "bg-gray-500/20 text-gray-400 border-gray-500/30"
                              }
                            >
                              <TrendingUp
                                className={`h-3 w-3 mr-1 ${
                                  trend.trend_direction === "down" ? "rotate-180" : ""
                                }`}
                              />
                              {trend.percentage_change > 0 ? "+" : ""}
                              {trend.percentage_change}%
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground/60 mb-2">
                            {trend.mention_count} mentions across {trend.sources.length} sources
                          </p>
                          <div className="flex gap-1 flex-wrap">
                            {trend.sources.map((source, idx) => (
                              <Badge key={idx} variant="outline" className="text-[10px] bg-white/[0.02]">
                                {getSourceIcon(source)}
                                <span className="ml-1">{source}</span>
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <div className="text-right text-xs text-muted-foreground/40">
                          <p>First seen:</p>
                          <p className="font-medium">
                            {format(new Date(trend.first_seen), "MMM d")}
                          </p>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Research Tab */}
        <TabsContent value="research" className="mt-4">
          <div className="text-center py-20">
            <GraduationCap className="h-16 w-16 text-muted-foreground/20 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-muted-foreground/60 mb-2">
              Research Papers
            </h3>
            <p className="text-sm text-muted-foreground/40">
              Showing {filteredItems.filter((i) => i.category === "research").length} research items
            </p>
          </div>
        </TabsContent>

        {/* Tech Tab */}
        <TabsContent value="tech" className="mt-4">
          <div className="text-center py-20">
            <Globe className="h-16 w-16 text-muted-foreground/20 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-muted-foreground/60 mb-2">
              Technology News
            </h3>
            <p className="text-sm text-muted-foreground/40">
              Showing {filteredItems.filter((i) => i.category === "tech").length} tech items
            </p>
          </div>
        </TabsContent>

        {/* Programming Tab */}
        <TabsContent value="programming" className="mt-4">
          <div className="text-center py-20">
            <Code2 className="h-16 w-16 text-muted-foreground/20 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-muted-foreground/60 mb-2">
              Programming & Development
            </h3>
            <p className="text-sm text-muted-foreground/40">
              Showing {filteredItems.filter((i) => i.category === "programming").length} programming items
            </p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
