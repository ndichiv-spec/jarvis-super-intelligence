"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Brain, Activity, Heart, Network, Database, Zap,
  TrendingUp, Users, BookOpen, Sparkles, Clock,
  RefreshCw, Eye, Target, MessageSquare, BarChart3
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { jarvisAPI } from "@/lib/api";
import { toast } from "sonner";
import { format } from "date-fns";

interface ConsciousnessReport {
  state: string;
  awareness_level: number;
  attention_focus: string;
  metacognitive_thoughts: string[];
  current_goals: string[];
  self_reflection: string;
}

interface EmotionAnalysis {
  primary_emotion: string;
  emotion_intensity: number;
  emotion_scores: Record<string, number>;
  sentiment: number;
}

interface UserProfile {
  user_id: string;
  total_interactions: number;
  relationship_strength: number;
  emotional_patterns: any;
  preferences: any;
  first_interaction?: string;
  last_interaction?: string;
}

interface MemoryStats {
  short_term_count: number;
  context_items: number;
  total_interactions: number;
}

const EMOTION_COLORS: Record<string, string> = {
  joy: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  sadness: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  anger: "bg-red-500/20 text-red-400 border-red-500/30",
  fear: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  surprise: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  trust: "bg-green-500/20 text-green-400 border-green-500/30",
  curiosity: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  neutral: "bg-gray-500/20 text-gray-400 border-gray-500/30",
};

export default function CognitivePage() {
  const [isLoading, setIsLoading] = useState(true);
  const [consciousness, setConsciousness] = useState<ConsciousnessReport | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const [emotionTest, setEmotionTest] = useState<EmotionAnalysis | null>(null);
  const [testInput, setTestInput] = useState("I'm really excited about this new feature!");

  useEffect(() => {
    loadCognitiveData();
    // Auto-refresh every 10 seconds
    const interval = setInterval(loadCognitiveData, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadCognitiveData = async () => {
    try {
      setIsLoading(true);

      // Load consciousness report
      try {
        const report = await jarvisAPI.getCognitiveReport();
        setConsciousness(report);
      } catch (e) {
        console.error("Failed to load consciousness:", e);
      }

      // Load user profile
      try {
        const profile = await jarvisAPI.getUserProfile("default");
        setUserProfile(profile);
      } catch (e) {
        console.error("Failed to load user profile:", e);
      }

      // Load memory stats
      try {
        const stats = await jarvisAPI.getMemoryStats();
        setMemoryStats(stats);
      } catch (e) {
        console.error("Failed to load memory stats:", e);
      }
    } catch (error) {
      console.error("Failed to load cognitive data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const testEmotionAnalysis = async () => {
    try {
      const result = await jarvisAPI.analyzeEmotions(testInput);
      setEmotionTest(result);
      toast.success("Emotion analysis completed");
    } catch (error: any) {
      toast.error(`Analysis failed: ${error.message}`);
    }
  };

  const triggerReflection = async () => {
    try {
      toast.info("Triggering self-reflection...");
      await jarvisAPI.triggerCognitiveReflection();
      toast.success("Self-reflection completed");
      await loadCognitiveData();
    } catch (error: any) {
      toast.error(`Reflection failed: ${error.message}`);
    }
  };

  const triggerConsolidation = async () => {
    try {
      toast.info("Consolidating memories...");
      await jarvisAPI.consolidateMemories();
      toast.success("Memory consolidation completed");
      await loadCognitiveData();
    } catch (error: any) {
      toast.error(`Consolidation failed: ${error.message}`);
    }
  };

  const getAwarenessLevel = () => {
    if (!consciousness) return 0;
    return consciousness.awareness_level * 100;
  };

  const getStateBadge = (state: string) => {
    const config: Record<string, string> = {
      fully_aware: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
      focused: "bg-blue-500/20 text-blue-400 border-blue-500/30",
      reflective: "bg-purple-500/20 text-purple-400 border-purple-500/30",
      monitoring: "bg-amber-500/20 text-amber-400 border-amber-500/30",
      dormant: "bg-gray-500/20 text-gray-400 border-gray-500/30",
    };
    return config[state] || config.monitoring;
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
          <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent">
            Cognitive Systems
          </h1>
          <p className="text-muted-foreground/60 mt-1">
            Advanced memory, consciousness & emotional intelligence
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={triggerReflection}>
            <Sparkles className="mr-2 h-4 w-4" />
            Self-Reflect
          </Button>
          <Button variant="outline" onClick={triggerConsolidation}>
            <Database className="mr-2 h-4 w-4" />
            Consolidate
          </Button>
          <Button onClick={loadCognitiveData} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </motion.div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          {
            label: "Awareness Level",
            value: `${getAwarenessLevel().toFixed(0)}%`,
            icon: Eye,
            color: "from-purple-500 to-pink-400",
            progress: getAwarenessLevel(),
          },
          {
            label: "Short-Term Memories",
            value: memoryStats?.short_term_count || 0,
            icon: Database,
            color: "from-blue-500 to-cyan-400",
          },
          {
            label: "Total Interactions",
            value: userProfile?.total_interactions || 0,
            icon: Users,
            color: "from-emerald-500 to-green-400",
          },
          {
            label: "Relationship Strength",
            value: `${((userProfile?.relationship_strength || 0) * 100).toFixed(0)}%`,
            icon: Heart,
            color: "from-pink-500 to-rose-400",
            progress: (userProfile?.relationship_strength || 0) * 100,
          },
        ].map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
          >
            <Card className="bg-white/[0.02] border-white/5">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <stat.icon className={`h-6 w-6 bg-gradient-to-br ${stat.color} bg-clip-text opacity-50`} />
                  <span className="text-2xl font-bold">{stat.value}</span>
                </div>
                <p className="text-xs text-muted-foreground/60">{stat.label}</p>
                {stat.progress !== undefined && (
                  <Progress value={stat.progress} className="mt-2" />
                )}
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Tabs */}
      <Tabs defaultValue="consciousness">
        <TabsList className="bg-white/[0.02] border-white/5">
          <TabsTrigger value="consciousness" className="text-sm">
            <Brain className="mr-2 h-4 w-4" />
            Consciousness
          </TabsTrigger>
          <TabsTrigger value="memory" className="text-sm">
            <Database className="mr-2 h-4 w-4" />
            Memory
          </TabsTrigger>
          <TabsTrigger value="emotion" className="text-sm">
            <Heart className="mr-2 h-4 w-4" />
            Emotions
          </TabsTrigger>
          <TabsTrigger value="user" className="text-sm">
            <Users className="mr-2 h-4 w-4" />
            User Profile
          </TabsTrigger>
        </TabsList>

        {/* Consciousness Tab */}
        <TabsContent value="consciousness" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Eye className="h-5 w-5 text-purple-400" />
                  Consciousness State
                </CardTitle>
                <CardDescription>
                  Current self-awareness and internal monitoring
                </CardDescription>
              </CardHeader>
              <CardContent>
                {consciousness ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-muted-foreground/60">State</span>
                      <Badge className={getStateBadge(consciousness.state)}>
                        {consciousness.state.replace('_', ' ')}
                      </Badge>
                    </div>
                    <Separator />
                    <div>
                      <div className="flex justify-between mb-2">
                        <span className="text-sm text-muted-foreground/60">Awareness Level</span>
                        <span className="text-sm font-medium">{(consciousness.awareness_level * 100).toFixed(0)}%</span>
                      </div>
                      <Progress value={consciousness.awareness_level * 100} />
                    </div>
                    <Separator />
                    <div>
                      <p className="text-sm font-medium mb-2">Attention Focus</p>
                      <p className="text-sm text-muted-foreground/60">
                        {consciousness.attention_focus || "Not currently focused"}
                      </p>
                    </div>
                    <Separator />
                    <div>
                      <p className="text-sm font-medium mb-2">Self-Reflection</p>
                      <p className="text-sm text-muted-foreground/60">
                        {consciousness.self_reflection || "No recent reflection"}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground/40">
                    <Brain className="h-12 w-12 mx-auto mb-2 opacity-50" />
                    <p>Loading consciousness data...</p>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="bg-white/[0.02] border-white/5">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-cyan-400" />
                  Metacognitive Thoughts
                </CardTitle>
                <CardDescription>
                  Recent thinking about thinking
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[300px]">
                  <div className="space-y-2">
                    {consciousness?.metacognitive_thoughts.map((thought, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.1 }}
                        className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-sm"
                      >
                        <div className="flex items-start gap-2">
                          <MessageSquare className="h-4 w-4 text-cyan-400 mt-0.5 flex-shrink-0" />
                          <span className="text-muted-foreground/70">{thought}</span>
                        </div>
                      </motion.div>
                    ))}
                    {(!consciousness?.metacognitive_thoughts || consciousness.metacognitive_thoughts.length === 0) && (
                      <div className="text-center py-8 text-muted-foreground/40">
                        <Sparkles className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p>No metacognitive thoughts recorded</p>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          </div>

          {/* Current Goals */}
          <Card className="bg-white/[0.02] border-white/5 mt-4">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Target className="h-5 w-5 text-emerald-400" />
                Active Goals
              </CardTitle>
              <CardDescription>
                Current objectives and purposes
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {consciousness?.current_goals.map((goal, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.05 }}
                    className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20"
                  >
                    <div className="flex items-center gap-2">
                      <Target className="h-4 w-4 text-emerald-400" />
                      <span className="text-sm">{goal}</span>
                    </div>
                  </motion.div>
                ))}
                {(!consciousness?.current_goals || consciousness.current_goals.length === 0) && (
                  <div className="col-span-3 text-center py-8 text-muted-foreground/40">
                    <Target className="h-12 w-12 mx-auto mb-2 opacity-50" />
                    <p>No active goals</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Memory Tab */}
        <TabsContent value="memory" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-blue-400" />
                Memory System
              </CardTitle>
              <CardDescription>
                Multi-layered memory architecture
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { layer: "Short-Term", count: memoryStats?.short_term_count || 0, color: "from-blue-500 to-cyan-400", desc: "Recent conversations" },
                  { layer: "Long-Term", count: 0, color: "from-purple-500 to-pink-400", desc: "Consolidated memories" },
                  { layer: "Episodic", count: 0, color: "from-emerald-500 to-green-400", desc: "Specific events" },
                  { layer: "Semantic", count: 0, color: "from-amber-500 to-orange-400", desc: "Facts & knowledge" },
                ].map((layer, i) => (
                  <motion.div
                    key={layer.layer}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.1 }}
                  >
                    <Card className="bg-white/[0.02] border-white/5">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-lg font-bold">{layer.count}</span>
                          <div className={`h-8 w-8 rounded-full bg-gradient-to-br ${layer.color}`} />
                        </div>
                        <p className="text-sm font-medium">{layer.layer} Memory</p>
                        <p className="text-xs text-muted-foreground/40">{layer.desc}</p>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Emotion Tab */}
        <TabsContent value="emotion" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Heart className="h-5 w-5 text-pink-400" />
                Emotional Intelligence
              </CardTitle>
              <CardDescription>
                Test emotion detection and sentiment analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium mb-2 block">Test Input</label>
                  <input
                    type="text"
                    value={testInput}
                    onChange={(e) => setTestInput(e.target.value)}
                    className="w-full p-2 rounded bg-white/[0.02] border border-white/5 text-sm"
                    placeholder="Enter text to analyze emotions..."
                  />
                </div>
                <Button onClick={testEmotionAnalysis}>
                  <Heart className="mr-2 h-4 w-4" />
                  Analyze Emotions
                </Button>

                {emotionTest && (
                  <div className="space-y-3 mt-4">
                    <Separator />
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="p-3 rounded-lg bg-white/[0.02]">
                        <p className="text-xs text-muted-foreground/60 mb-1">Primary Emotion</p>
                        <Badge className={EMOTION_COLORS[emotionTest.primary_emotion] || EMOTION_COLORS.neutral}>
                          {emotionTest.primary_emotion}
                        </Badge>
                      </div>
                      <div className="p-3 rounded-lg bg-white/[0.02]">
                        <p className="text-xs text-muted-foreground/60 mb-1">Intensity</p>
                        <p className="text-lg font-bold">{(emotionTest.emotion_intensity * 100).toFixed(0)}%</p>
                      </div>
                      <div className="p-3 rounded-lg bg-white/[0.02]">
                        <p className="text-xs text-muted-foreground/60 mb-1">Sentiment</p>
                        <p className={`text-lg font-bold ${emotionTest.sentiment > 0 ? 'text-emerald-400' : emotionTest.sentiment < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                          {emotionTest.sentiment > 0 ? '+' : ''}{emotionTest.sentiment.toFixed(2)}
                        </p>
                      </div>
                    </div>

                    <div>
                      <p className="text-sm font-medium mb-2">All Emotion Scores</p>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {Object.entries(emotionTest.emotion_scores)
                          .filter(([_, score]) => score > 0.05)
                          .sort((a, b) => b[1] - a[1])
                          .map(([emotion, score]) => (
                            <div key={emotion} className="p-2 rounded bg-white/[0.02]">
                              <div className="flex items-center justify-between text-xs mb-1">
                                <span className="capitalize">{emotion}</span>
                                <span className="text-muted-foreground/60">{(score * 100).toFixed(0)}%</span>
                              </div>
                              <Progress value={score * 100} className="h-1" />
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* User Profile Tab */}
        <TabsContent value="user" className="mt-4">
          <Card className="bg-white/[0.02] border-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-emerald-400" />
                User Profile & Learning
              </CardTitle>
              <CardDescription>
                Learned information about user preferences and patterns
              </CardDescription>
            </CardHeader>
            <CardContent>
              {userProfile && userProfile.total_interactions > 0 ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="p-4 rounded-lg bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">Total Interactions</p>
                      <p className="text-2xl font-bold">{userProfile.total_interactions}</p>
                    </div>
                    <div className="p-4 rounded-lg bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">Relationship Strength</p>
                      <p className="text-2xl font-bold">{(userProfile.relationship_strength * 100).toFixed(0)}%</p>
                    </div>
                    <div className="p-4 rounded-lg bg-white/[0.02]">
                      <p className="text-xs text-muted-foreground/60 mb-1">Last Interaction</p>
                      <p className="text-sm">
                        {userProfile.last_interaction
                          ? format(new Date(userProfile.last_interaction), "MMM d, HH:mm")
                          : "Never"}
                      </p>
                    </div>
                  </div>

                  {userProfile.emotional_patterns?.dominant_emotions && (
                    <div>
                      <p className="text-sm font-medium mb-2">Dominant Emotions</p>
                      <div className="flex gap-2">
                        {userProfile.emotional_patterns.dominant_emotions.slice(0, 3).map(([emotion, count]: [string, number], i: number) => (
                          <Badge key={i} className={EMOTION_COLORS[emotion] || EMOTION_COLORS.neutral}>
                            {emotion} ({count})
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12 text-muted-foreground/40">
                  <Users className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-semibold mb-2">No User Data Yet</h3>
                  <p className="text-sm">
                    Interact with JARVIS to build user profile and learn preferences
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
