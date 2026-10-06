/**
 * JARVIS Voice Control Panel
 * ===========================
 * Tony Stark-inspired voice interface control.
 * Talk to JARVIS naturally - "JARVIS, run diagnostics"
 *
 * Features:
 * - Real-time voice chat via WebSocket
 * - Text-to-Speech (TTS) controls with voice selection
 * - Speech-to-Text (ASR) controls
 * - Voice profile management
 * - Live conversation history
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Mic,
  MicOff,
  Volume2,
  VolumeX,
  MessageSquare,
  Settings,
  Play,
  Square,
  Phone,
  PhoneOff,
  Activity,
  User,
  Plus,
  Save,
  Trash2,
  Folder,
  File,
  FileText,
  Image,
  Code,
  Package,
  Lock,
  Search,
  MoreHorizontal,
} from "lucide-react";
import { toast } from "sonner";
import { jarvisAPI } from "@/lib/api";
import { VoicePresence } from "@/components/voice/voice-presence";

interface VoiceMessage {
  id: string;
  type: "user" | "assistant" | "system";
  text: string;
  timestamp: Date;
  confidence?: number;
  engine?: string;
}

interface VoiceStatus {
  is_initialized: boolean;
  tts_available: boolean;
  asr_available: boolean;
  whisper_available: boolean;
  continuous_listening: boolean;
  listener_count: number;
}

interface VoiceProfile {
  name: string;
  rate: number;
  volume: number;
}

const VOICE_OPTIONS = [
  "default", "nova", "alloy", "echo", "fable", "onyx", "shimmer",
];

export default function VoiceControlPanel() {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [activeProfile, setActiveProfile] = useState<string>("jarvis_default");
  const [selectedVoice, setSelectedVoice] = useState<string>("default");
  const [availableVoices, setAvailableVoices] = useState<string[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [activeTab, setActiveTab] = useState("chat");
  const [profileForm, setProfileForm] = useState({ name: "", rate: 150, volume: 0.9 });

  const wsRef = useRef<WebSocket | null>(null);
  const wsRequestId = useRef(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch voice status, voices, and profiles on mount
  useEffect(() => {
    fetchVoiceStatus();
    fetchVoices();
    fetchProfiles();
  }, []);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const fetchVoiceStatus = async () => {
    try {
      const status = await jarvisAPI.voiceGetStatus();
      if (status.success) {
        setVoiceStatus(status.status);
      }
    } catch (error) {
      console.error("Failed to fetch voice status:", error);
    }
  };

  const fetchVoices = async () => {
    try {
      const result = await jarvisAPI.voiceGetVoices();
      const voices = result.voices || result.metadata?.voices || VOICE_OPTIONS;
      setAvailableVoices(voices);
    } catch (error: any) {
      console.error("Failed to fetch voices:", error);
      setAvailableVoices(VOICE_OPTIONS);
    }
  };

  const fetchProfiles = async () => {
    try {
      const result = await jarvisAPI.voiceListProfiles();
      const fetched = result.profiles || result.metadata?.profiles || [];
      setProfiles(fetched);
      if (fetched.length > 0) {
        setActiveProfile(fetched[0].name);
      }
    } catch (error: any) {
      console.error("Failed to fetch profiles:", error);
    }
  };

  const connectVoiceWebSocket = () => {
    const requestId = ++wsRequestId.current;
    if (wsRef.current) {
      wsRef.current.close();
    }

    void jarvisAPI.connectVoiceWebSocket(
      (data) => {
        console.log("Voice WS message:", data);

        if (data.status === "listening") {
          setIsListening(true);
          addSystemMessage("Listening...");
        } else if (data.status === "recognized") {
          setIsListening(false);
          addMessage({
            type: "user",
            text: data.text,
            confidence: data.confidence,
            engine: data.engine,
          });
        } else if (data.status === "response") {
          addMessage({
            type: "assistant",
            text: data.text,
            confidence: data.confidence,
            engine: data.engine,
          });
        } else if (data.status === "speaking") {
          setIsSpeaking(true);
          addSystemMessage("Speaking response...");
        } else if (data.status === "complete") {
          setIsSpeaking(false);
          setIsListening(false);
          addSystemMessage("Conversation complete");
        } else if (data.status === "error") {
          setIsListening(false);
          setIsSpeaking(false);
          addSystemMessage(`Error: ${data.error}`);
          toast.error(`Voice error: ${data.error}`);
        }
      },
      (error) => {
        console.error("Voice WebSocket error:", error);
        setIsConnected(false);
        toast.error("Voice connection lost");
      }
    ).then((ws) => {
      if (requestId !== wsRequestId.current) {
        ws.close();
        return;
      }
      wsRef.current = ws;
      ws.addEventListener("open", () => {
        if (requestId !== wsRequestId.current) return;
        setIsConnected(true);
        toast.success("Voice connection established");
      });
      ws.addEventListener("close", () => {
        if (requestId !== wsRequestId.current) return;
        setIsConnected(false);
      });
    }).catch((error) => {
      if (requestId !== wsRequestId.current) return;
      console.error("Failed to authenticate voice connection:", error);
      setIsConnected(false);
      toast.error("Voice connection could not be authenticated");
    });
  };

  const disconnectVoiceWebSocket = () => {
    wsRequestId.current++;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setIsListening(false);
    setIsSpeaking(false);
    toast.info("Voice connection closed");
  };

  const addMessage = (msg: Omit<VoiceMessage, "id" | "timestamp">) => {
    const newMessage: VoiceMessage = {
      ...msg,
      id: Date.now().toString(),
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, newMessage]);
  };

  const addSystemMessage = (text: string) => {
    addMessage({
      type: "system",
      text,
    });
  };

  const handleStartListening = () => {
    if (!wsRef.current) {
      connectVoiceWebSocket();
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          action: "listen",
          timeout: 5,
          phrase_time_limit: 10,
        })
      );
    } else {
      toast.error("Voice connection not ready");
    }
  };

  const handleSpeakText = async () => {
    if (!inputText.trim()) {
      toast.error("Please enter text to speak");
      return;
    }

    try {
      setIsSpeaking(true);
      const payload: any = { text: inputText };
      if (selectedVoice) payload.voice = selectedVoice;
      if (activeProfile) payload.profile_name = activeProfile;
      await jarvisAPI.voiceSpeak(inputText, activeProfile);
      addMessage({
        type: "assistant",
        text: inputText,
      });
      setIsSpeaking(false);
      toast.success("Speaking...");
    } catch (error: any) {
      setIsSpeaking(false);
      toast.error(`Failed to speak: ${error.message}`);
    }
  };

  const handleManualListen = async () => {
    try {
      setIsListening(true);
      const result = await jarvisAPI.voiceListen(5, 10);
      setIsListening(false);

      if (result.success) {
        addMessage({
          type: "user",
          text: result.text,
          confidence: result.confidence,
          engine: result.engine,
        });

        // Process through AI
        const aiResponse = await jarvisAPI.starkChat({
          message: result.text,
        });

        if (aiResponse.success) {
          addMessage({
            type: "assistant",
            text: aiResponse.response,
            confidence: aiResponse.confidence,
            engine: aiResponse.engine,
          });

          // Speak response
          await jarvisAPI.voiceSpeak(aiResponse.response, activeProfile);
        }
      } else {
        toast.error(result.error || "Listen failed");
      }
    } catch (error: any) {
      setIsListening(false);
      toast.error(`Listen failed: ${error.message}`);
    }
  };

  const clearConversation = () => {
    setMessages([]);
    toast.info("Conversation cleared");
  };

  const handleCreateProfile = async () => {
    if (!profileForm.name.trim()) {
      toast.error("Profile name is required");
      return;
    }
    try {
      await jarvisAPI.voiceCreateProfile(
        profileForm.name,
        profileForm.rate,
        profileForm.volume
      );
      toast.success(`Profile "${profileForm.name}" created`);
      setProfileForm({ name: "", rate: 150, volume: 0.9 });
      await fetchProfiles();
    } catch (error: any) {
      toast.error(`Failed to create profile: ${error.message}`);
    }
  };

  const handleDeleteProfile = async (name: string) => {
    try {
      // Profiles are stored in a dict; remove by name
      // Use the save endpoint to overwrite or call delete if available
      // For now, we can't delete via API - just inform the user
      toast.info(`Profile "${name}" deletion must be done via backend`);
    } catch (error: any) {
      toast.error(`Failed to delete profile: ${error.message}`);
    }
  };

  const getVoiceLabel = (voiceId: string) => {
    const labels: Record<string, string> = {
      default: "Default",
      nova: "Nova (Premium)",
      alloy: "Alloy",
      echo: "Echo",
      fable: "Fable",
      onyx: "Onyx",
      shimmer: "Shimmer",
    };
    return labels[voiceId] || voiceId;
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
            JARVIS Voice Interface
          </h1>
          <p className="text-muted-foreground mt-1">
            "Jarvis, run diagnostics" - Tony Stark
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="px-3 py-1">
            <div
              className={`h-2 w-2 rounded-full mr-2 ${
                isConnected ? "bg-green-500 animate-pulse" : "bg-gray-500"
              }`}
            ></div>
            {isConnected ? "Connected" : "Disconnected"}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              fetchVoiceStatus();
              fetchVoices();
              fetchProfiles();
              toast.success("Status refreshed");
            }}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Tabs for Voice Chat and Profile Management */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3 mb-4">
          <TabsTrigger value="chat">Voice Chat</TabsTrigger>
          <TabsTrigger value="tts">TTS Controls</TabsTrigger>
          <TabsTrigger value="profiles">Voice Profiles</TabsTrigger>
        </TabsList>

        {/* ── Voice Chat Tab ── */}
        <TabsContent value="chat" className="space-y-4">
          {/* Voice presence: audio-reactive orb + level meter */}
          <Card className="border-cyan-500/20 bg-cyan-500/[0.02]">
            <CardContent className="py-4">
              <VoicePresence
                isSpeaking={isSpeaking}
                isListening={isListening}
                variant="bars"
                enableMic
                showMicToggle={false}
                width={320}
                height={44}
                className="mx-auto max-w-md"
              />
            </CardContent>
          </Card>

          {/* Voice Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="border-blue-500/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Volume2 className="h-4 w-4 text-blue-400" />
                  TTS Engine
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Badge
                  variant="outline"
                  className={
                    voiceStatus?.tts_available
                      ? "border-green-500 text-green-400"
                      : "border-red-500 text-red-400"
                  }
                >
                  {voiceStatus?.tts_available ? "Online" : "Offline"}
                </Badge>
              </CardContent>
            </Card>

            <Card className="border-purple-500/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Mic className="h-4 w-4 text-purple-400" />
                  ASR Engine
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Badge
                  variant="outline"
                  className={
                    voiceStatus?.asr_available
                      ? "border-green-500 text-green-400"
                      : "border-red-500 text-red-400"
                  }
                >
                  {voiceStatus?.asr_available ? "Online" : "Offline"}
                </Badge>
              </CardContent>
            </Card>

            <Card className="border-cyan-500/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="h-4 w-4 text-cyan-400" />
                  Whisper
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Badge
                  variant="outline"
                  className={
                    voiceStatus?.whisper_available
                      ? "border-green-500 text-green-400"
                      : "border-yellow-500 text-yellow-400"
                  }
                >
                  {voiceStatus?.whisper_available ? "Available" : "Fallback"}
                </Badge>
              </CardContent>
            </Card>

            <Card className="border-green-500/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-green-400" />
                  Messages
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-green-400">
                  {messages.length}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  in conversation
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Voice Chat */}
            <Card className="lg:col-span-2 border-blue-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Phone className="h-5 w-5 text-blue-400" />
                  Voice Chat
                  {isListening && (
                    <Badge variant="destructive" className="ml-2 animate-pulse">
                      <Mic className="h-3 w-3 mr-1" />
                      Listening
                    </Badge>
                  )}
                  {isSpeaking && (
                    <Badge variant="secondary" className="ml-2 animate-pulse">
                      <Volume2 className="h-3 w-3 mr-1" />
                      Speaking
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  Talk to JARVIS naturally - voice commands and responses
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Connection Controls */}
                <div className="flex gap-2">
                  {!isConnected ? (
                    <Button onClick={connectVoiceWebSocket} className="flex-1">
                      <Phone className="h-4 w-4 mr-2" />
                      Connect Voice
                    </Button>
                  ) : (
                    <Button
                      onClick={disconnectVoiceWebSocket}
                      variant="destructive"
                      className="flex-1"
                    >
                      <PhoneOff className="h-4 w-4 mr-2" />
                      Disconnect
                    </Button>
                  )}
                  <Button variant="outline" onClick={clearConversation}>
                    Clear
                  </Button>
                </div>

                {/* Voice Controls */}
                <div className="flex gap-2">
                  <Button
                    onClick={handleStartListening}
                    disabled={!isConnected || isListening}
                    variant={isListening ? "destructive" : "default"}
                    className="flex-1"
                  >
                    {isListening ? (
                      <>
                        <MicOff className="h-4 w-4 mr-2" />
                        Listening...
                      </>
                    ) : (
                      <>
                        <Mic className="h-4 w-4 mr-2" />
                        Start Listening
                      </>
                    )}
                  </Button>
                  <Button
                    onClick={handleManualListen}
                    disabled={isListening}
                    variant="outline"
                  >
                    <Mic className="h-4 w-4 mr-2" />
                    Quick Listen
                  </Button>
                </div>

                {/* Text Input for TTS */}
                <div className="flex gap-2">
                  <Input
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Enter text for JARVIS to speak..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        handleSpeakText();
                      }
                    }}
                  />
                  <Button
                    onClick={handleSpeakText}
                    disabled={isSpeaking || !inputText.trim()}
                    variant={isSpeaking ? "secondary" : "default"}
                  >
                    {isSpeaking ? (
                      <>
                        <Square className="h-4 w-4 mr-2" />
                        Speaking
                      </>
                    ) : (
                      <>
                        <Play className="h-4 w-4 mr-2" />
                        Speak
                      </>
                    )}
                  </Button>
                </div>

                {/* Conversation History */}
                <ScrollArea className="h-96 rounded-lg border p-4 bg-muted/30">
                  <div className="space-y-3">
                    {messages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${
                          msg.type === "user" ? "justify-end" : "justify-start"
                        }`}
                      >
                        <div
                          className={`max-w-[80%] rounded-lg p-3 ${
                            msg.type === "user"
                              ? "bg-blue-500/20 border border-blue-500/30"
                              : msg.type === "system"
                              ? "bg-gray-500/20 border border-gray-500/30 text-sm italic"
                              : "bg-green-500/20 border border-green-500/30"
                          }`}
                        >
                          <p className="text-sm">{msg.text}</p>
                          <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                            <span>
                              {msg.timestamp.toLocaleTimeString()}
                            </span>
                            {msg.confidence && (
                              <span>
                                • Confidence: {(msg.confidence * 100).toFixed(0)}%
                              </span>
                            )}
                            {msg.engine && <span>• {msg.engine}</span>}
                          </div>
                        </div>
                      </div>
                    ))}
                    <div ref={messagesEndRef} />
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Voice Settings Sidebar */}
            <div className="space-y-4">
              {/* Active Profile & Voice Selection */}
              <Card className="border-blue-500/20">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Voice Settings
                  </CardTitle>
                  <CardDescription>
                    Configure voice profiles and TTS preferences
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Voice Selection Dropdown */}
                  <div className="space-y-2">
                    <Label htmlFor="voice-select" className="text-sm font-medium">
                      TTS Voice
                    </Label>
                    <Select
                      value={selectedVoice}
                      onValueChange={setSelectedVoice}
                      disabled={!voiceStatus?.tts_available}
                    >
                      <SelectTrigger id="voice-select" className="w-full">
                        <SelectValue placeholder="Select a voice" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableVoices.map((voice) => (
                          <SelectItem key={voice} value={voice}>
                            {getVoiceLabel(voice)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Active voice: {getVoiceLabel(selectedVoice)}
                    </p>
                  </div>

                  {/* Active Profile */}
                  <div className="space-y-2">
                    <Label className="text-sm font-medium">Active Profile</Label>
                    <div className="flex items-center gap-2">
                      <User className="h-4 w-4 text-muted-foreground" />
                      <Badge variant="secondary" className="px-3 py-1">
                        {activeProfile}
                      </Badge>
                    </div>
                    {profiles.length > 0 && (
                      <p className="text-xs text-muted-foreground">
                        {profiles.length} profile{profiles.length !== 1 ? "s" : ""} available
                      </p>
                    )}
                  </div>

                  {/* Quick Actions */}
                  <div className="space-y-2 pt-2 border-t">
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={async () => {
                        await fetchProfiles();
                        toast.info(`Found ${profiles.length} profile${profiles.length !== 1 ? "s" : ""}`);
                      }}
                    >
                      <User className="h-4 w-4 mr-2" />
                      Refresh Profiles
                    </Button>
                    <Button
                      variant="outline"
                      className="w-full"
                      onClick={async () => {
                        await fetchVoices();
                        toast.info(`Found ${availableVoices.length} voices`);
                      }}
                    >
                      Refresh Voices
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Voice Engine Info */}
              <Card className="border-gray-500/20">
                <CardContent className="pt-4">
                  <div className="rounded-lg border p-3 bg-muted/30 space-y-2">
                    <h4 className="font-medium text-sm">Voice Engine Info</h4>
                    <div className="space-y-1 text-xs text-muted-foreground">
                      <p>• TTS: pyttsx3 (offline)</p>
                      <p>• ASR: SpeechRecognition + Whisper</p>
                      <p>• Languages: English (more with Whisper)</p>
                      <p>• Profiles: Custom voice settings</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

        {/* ── TTS Controls Tab ── */}
        <TabsContent value="tts" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* TTS Configuration */}
            <Card className="border-purple-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Volume2 className="h-5 w-5 text-purple-400" />
                  Text-to-Speech
                </CardTitle>
                <CardDescription>
                  Configure voice and speech parameters, then preview
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Voice Selection */}
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Voice Model</Label>
                  <Select value={selectedVoice} onValueChange={setSelectedVoice}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select a voice" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableVoices.map((voice) => (
                        <SelectItem key={voice} value={voice}>
                          {getVoiceLabel(voice)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Active Profile for TTS */}
                <div className="space-y-2">
                  <Label className="text-sm font-medium">Voice Profile</Label>
                  <Select
                    value={activeProfile || "jarvis_default"}
                    onValueChange={setActiveProfile}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select a profile" />
                    </SelectTrigger>
                    <SelectContent>
                      {profiles.map((p) => (
                        <SelectItem key={p.name} value={p.name}>
                          {p.name} (rate: {p.rate}, vol: {p.volume})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Text Input */}
                <div className="space-y-2">
                  <Label htmlFor="tts-input" className="text-sm font-medium">
                    Text to Speak
                  </Label>
                  <Input
                    id="tts-input"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Enter text for JARVIS to speak..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        handleSpeakText();
                      }
                    }}
                  />
                </div>

                {/* Speak Button */}
                <Button
                  onClick={handleSpeakText}
                  disabled={isSpeaking || !inputText.trim() || !voiceStatus?.tts_available}
                  variant={isSpeaking ? "secondary" : "default"}
                  className="w-full"
                >
                  {isSpeaking ? (
                    <>
                      <Square className="h-4 w-4 mr-2" />
                      Speaking...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-2" />
                      Speak with {getVoiceLabel(selectedVoice)}
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* TTS Status */}
            <Card className="border-green-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="h-5 w-5 text-green-400" />
                  TTS Status
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      TTS Engine
                    </span>
                    <Badge
                      variant={voiceStatus?.tts_available ? "default" : "destructive"}
                    >
                      {voiceStatus?.tts_available ? "Online" : "Offline"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      ASR Engine
                    </span>
                    <Badge
                      variant={voiceStatus?.asr_available ? "default" : "secondary"}
                    >
                      {voiceStatus?.asr_available ? "Online" : "Offline"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      Whisper ASR
                    </span>
                    <Badge
                      variant={voiceStatus?.whisper_available ? "default" : "outline"}
                    >
                      {voiceStatus?.whisper_available ? "Available" : "Fallback"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      Current Voice
                    </span>
                    <span className="text-sm font-medium">
                      {getVoiceLabel(selectedVoice)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">
                      Active Profile
                    </span>
                    <span className="text-sm font-medium">
                      {activeProfile}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Voice Profiles Tab ── */}
        <TabsContent value="profiles" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Profile List */}
            <Card className="border-cyan-500/20">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <User className="h-5 w-5 text-cyan-400" />
                    Voice Profiles
                  </span>
                  <Badge variant="outline">{profiles.length} active</Badge>
                </CardTitle>
                <CardDescription>
                  Manage custom voice profiles with personalized rate and volume
                </CardDescription>
              </CardHeader>
              <CardContent>
                {profiles.length === 0 ? (
                  <div className="text-center py-8">
                    <User className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
                    <p className="text-sm text-muted-foreground">
                      No profiles created yet. Create one below.
                    </p>
                  </div>
                ) : (
                  <ScrollArea className="h-80">
                    <div className="space-y-2">
                      {profiles.map((profile) => (
                        <div
                          key={profile.name}
                          className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                            activeProfile === profile.name
                              ? "border-cyan-500/30 bg-cyan-500/10"
                              : "border-border hover:bg-muted/20"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <User className="h-4 w-4 text-cyan-400" />
                            <div>
                              <p className="font-medium text-sm">
                                {profile.name}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                Rate: {profile.rate} • Volume: {profile.volume}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setActiveProfile(profile.name)}
                              className={
                                activeProfile === profile.name
                                  ? "text-cyan-400"
                                  : "text-muted-foreground"
                              }
                            >
                              {activeProfile === profile.name ? "Active" : "Select"}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              onClick={() => handleDeleteProfile(profile.name)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>

            {/* Create Profile Form */}
            <Card className="border-purple-500/20">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Plus className="h-5 w-5 text-purple-400" />
                  Create New Profile
                </CardTitle>
                <CardDescription>
                  Define a custom voice profile with specific rate and volume
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="profile-name" className="text-sm font-medium">
                    Profile Name
                  </Label>
                  <Input
                    id="profile-name"
                    value={profileForm.name}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, name: e.target.value })
                    }
                    placeholder="e.g. whisper_slow, presentation_fast..."
                  />
                </div>

                <div className="space-y-2">
                  <Label className="text-sm font-medium">
                    Speech Rate: {profileForm.rate}
                  </Label>
                  <Slider
                    value={[profileForm.rate]}
                    onValueChange={(vals) =>
                      setProfileForm({ ...profileForm, rate: vals[0] })
                    }
                    min={80}
                    max={250}
                    step={10}
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Slow (80)</span>
                    <span>Normal (150)</span>
                    <span>Fast (250)</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-sm font-medium">
                    Volume: {(profileForm.volume * 100).toFixed(0)}%
                  </Label>
                  <Slider
                    value={[profileForm.volume * 100]}
                    onValueChange={(vals) =>
                      setProfileForm({
                        ...profileForm,
                        volume: vals[0] / 100,
                      })
                    }
                    min={0}
                    max={100}
                    step={5}
                  />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Mute (0)</span>
                    <span>Default (90)</span>
                    <span>Loud (100)</span>
                  </div>
                </div>

                <Button
                  onClick={handleCreateProfile}
                  className="w-full gap-2"
                  disabled={!profileForm.name.trim()}
                >
                  <Save className="h-4 w-4" />
                  Create Profile
                </Button>
              </CardContent>
            </Card>
          </div>

          {/* Voice Engine Info (bottom of profiles tab) */}
          <Card className="border-gray-500/20">
            <CardContent className="pt-4">
              <div className="rounded-lg border p-3 bg-muted/30 space-y-2">
                <h4 className="font-medium text-sm flex items-center gap-2">
                  <Activity className="h-4 w-4" />
                  Voice Engine Info
                </h4>
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>• TTS: pyttsx3 (offline)</p>
                  <p>• ASR: SpeechRecognition + Whisper</p>
                  <p>• Languages: English (more with Whisper)</p>
                  <p>• Available voices: {availableVoices.length}</p>
                  <p>• Created profiles: {profiles.length}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
