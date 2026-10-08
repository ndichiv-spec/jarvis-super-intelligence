"use client";

import { FormEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Activity, Loader2, Mic, MicOff, MessageSquare, Newspaper, Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { jarvisAPI } from "@/lib/api";

interface VoiceMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: Date;
  tools?: string[];
}

interface VoiceServiceStatus {
  status?: string;
  tts_available?: boolean;
  asr_available?: boolean;
  audio_streaming_available?: boolean;
}

interface RecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface RecognitionResult extends ArrayLike<RecognitionAlternative> {
  isFinal: boolean;
}

interface RecognitionEvent extends Event {
  results: ArrayLike<RecognitionResult>;
}

interface RecognitionErrorEvent extends Event {
  error: string;
}

interface BrowserRecognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}

type RecognitionConstructor = new () => BrowserRecognition;
type SpeechWindow = Window & {
  SpeechRecognition?: RecognitionConstructor;
  webkitSpeechRecognition?: RecognitionConstructor;
};

const SOCIETY_BRIEF_PROMPT = [
  "Prepare a concise, balanced briefing on important current events and issues affecting society.",
  "Use live news or research tools if they are available. Cite sources and publication dates when available.",
  "If you cannot retrieve current sources, clearly say so and distinguish general background from verified recent events.",
  "Do not invent headlines, statistics, quotations, or sources. Organize the response into major themes and explain why each matters.",
].join(" ");

export default function VoiceControlPanel() {
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [input, setInput] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speakResponses, setSpeakResponses] = useState(true);
  const [voiceStatus, setVoiceStatus] = useState<VoiceServiceStatus | null>(null);
  const recognitionRef = useRef<BrowserRecognition | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const browserRecognitionSupported = useSyncExternalStore(
    () => () => {},
    () => {
      const speechWindow = window as SpeechWindow;
      return Boolean(speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition);
    },
    () => false,
  );
  const browserSpeechOutputSupported = useSyncExternalStore(
    () => () => {},
    () => typeof window.speechSynthesis !== "undefined",
    () => false,
  );

  useEffect(() => {
    void jarvisAPI.voiceGetStatus()
      .then((status: VoiceServiceStatus) => setVoiceStatus(status))
      .catch(() => setVoiceStatus({ status: "unavailable" }));

    return () => {
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const speak = (text: string) => {
    if (!window.speechSynthesis) {
      toast.error("Speech output is not supported by this browser");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => {
      setIsSpeaking(false);
      toast.error("Browser speech could not play this response");
    };
    window.speechSynthesis.speak(utterance);
  };

  const submitMessage = async (text: string) => {
    const message = text.trim();
    if (!message || isSending) return;
    setInput("");
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: message, createdAt: new Date() },
    ]);
    setIsSending(true);
    try {
      const result = await jarvisAPI.starkChat({
        message,
        context: {
          conversation_history: messages.slice(-12).map(({ role, text }) => ({ role, content: text })),
        },
      });
      if (!result.success || !result.response?.trim()) {
        throw new Error(result.response || "JARVIS returned no response");
      }
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: result.response,
          createdAt: new Date(),
          tools: result.tools_used,
        },
      ]);
      if (speakResponses) speak(result.response);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "JARVIS could not process that request");
    } finally {
      setIsSending(false);
    }
  };

  const startListening = () => {
    const speechWindow = window as SpeechWindow;
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      toast.error("Speech recognition is not supported here. You can still type to JARVIS.");
      return;
    }
    if (isListening || isSending) return;

    const recognition = new Recognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript;
      if (transcript) void submitMessage(transcript);
    };
    recognition.onerror = (event) => {
      setIsListening(false);
      if (event.error !== "aborted") toast.error(`Microphone error: ${event.error}`);
    };
    recognition.onend = () => setIsListening(false);
    recognitionRef.current = recognition;
    try {
      recognition.start();
      setIsListening(true);
    } catch (error) {
      setIsListening(false);
      toast.error(error instanceof Error ? error.message : "Could not start speech recognition");
    }
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitMessage(input);
  };

  const serverTtsAvailable = voiceStatus?.tts_available === true;
  const serverServiceLabel = voiceStatus === null
    ? "Checking"
    : voiceStatus.status === "unavailable"
      ? "Unavailable"
      : voiceStatus.status || "Reported";
  const serverFeatureLabel = (available: boolean | undefined) => {
    if (voiceStatus === null) return "Checking";
    if (voiceStatus.status === "unavailable") return "Unavailable";
    return available === true ? "Available" : available === false ? "Unavailable" : "Not reported";
  };

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200/70">JARVIS · Multimodal interface</p>
          <h1 className="mt-1 text-2xl font-semibold text-white md:text-3xl">Talk with JARVIS</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-400">
            Speak or type to the assistant, hear replies, and request an evidence-aware briefing on current affairs.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className={browserRecognitionSupported ? "border-emerald-300/30 text-emerald-200" : "border-amber-300/30 text-amber-100"}>
            <Mic className="mr-1.5 h-3.5 w-3.5" /> {browserRecognitionSupported ? "Browser speech input supported" : "Text input available"}
          </Badge>
          <Badge variant="outline" className={browserSpeechOutputSupported ? "border-emerald-300/30 text-emerald-200" : "border-amber-300/30 text-amber-100"}>
            <Volume2 className="mr-1.5 h-3.5 w-3.5" /> Browser playback {browserSpeechOutputSupported ? "supported" : "unavailable"}
          </Badge>
          <Badge variant="outline" className={serverTtsAvailable ? "border-emerald-300/30 text-emerald-200" : "border-slate-300/20 text-slate-300"}>
            <Activity className="mr-1.5 h-3.5 w-3.5" /> Server TTS {serverFeatureLabel(voiceStatus?.tts_available)}
          </Badge>
        </div>
      </header>

      <div className="grid flex-1 gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <Card className="flex min-h-[560px] flex-col border-white/10 bg-[#0b111b]">
          <CardHeader className="border-b border-white/[0.07]">
            <CardTitle className="flex items-center justify-between gap-3 text-lg text-white">
              <span className="flex items-center gap-2"><MessageSquare className="h-5 w-5 text-cyan-300" /> Conversation</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSpeakResponses((enabled) => !enabled)}
                aria-pressed={speakResponses}
                title={speakResponses ? "Turn response audio off" : "Turn response audio on"}
              >
                {speakResponses ? <Volume2 className="mr-2 h-4 w-4" /> : <VolumeX className="mr-2 h-4 w-4" />}
                {speakResponses ? "Audio on" : "Audio off"}
              </Button>
            </CardTitle>
            <CardDescription>JARVIS responses are powered by the configured assistant; browser speech handles microphone and playback.</CardDescription>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col gap-4 p-4">
            <ScrollArea className="min-h-[320px] flex-1 rounded-lg border border-white/[0.07] bg-black/20 p-4">
              <div className="space-y-4">
                {messages.length === 0 && (
                  <div className="flex h-full min-h-[260px] flex-col items-center justify-center text-center">
                    <div className="rounded-full border border-cyan-200/15 bg-cyan-200/[0.05] p-4 text-cyan-200"><MessageSquare className="h-6 w-6" /></div>
                    <p className="mt-4 text-sm font-medium text-slate-200">Ready when you are</p>
                    <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-400">Ask a question, dictate a request, or ask JARVIS for a society briefing.</p>
                  </div>
                )}
                {messages.map((message) => (
                  <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                    <article className={`max-w-[88%] rounded-xl border p-3 ${message.role === "user" ? "border-cyan-300/15 bg-cyan-300/[0.07]" : "border-white/[0.08] bg-white/[0.035]"}`}>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{message.text}</p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                        <span>{message.createdAt.toLocaleTimeString()}</span>
                        {message.tools?.map((tool) => <Badge variant="outline" key={tool} className="px-1.5 py-0 text-[10px]">{tool}</Badge>)}
                        {message.role === "assistant" && (
                          <button type="button" onClick={() => speak(message.text)} className="inline-flex items-center gap-1 text-cyan-200 hover:text-cyan-100">
                            <Volume2 className="h-3 w-3" /> Play
                          </button>
                        )}
                      </div>
                    </article>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Message JARVIS..."
                aria-label="Message JARVIS"
                disabled={isSending}
              />
              <Button type="submit" disabled={isSending || !input.trim()} aria-label="Send message">
                {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <MessageSquare className="h-4 w-4" />}
              </Button>
            </form>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant={isListening ? "destructive" : "outline"} onClick={isListening ? stopListening : startListening} disabled={isSending || (!browserRecognitionSupported && !isListening)}>
                {isListening ? <MicOff className="mr-2 h-4 w-4" /> : <Mic className="mr-2 h-4 w-4" />}
                {isListening ? "Stop listening" : "Speak to JARVIS"}
              </Button>
              <Button type="button" variant="outline" onClick={() => void submitMessage(SOCIETY_BRIEF_PROMPT)} disabled={isSending}>
                <Newspaper className="mr-2 h-4 w-4" /> Society briefing
              </Button>
              {isSpeaking && (
                <Button type="button" variant="ghost" onClick={() => window.speechSynthesis.cancel()}>
                  <VolumeX className="mr-2 h-4 w-4" /> Stop audio
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <aside className="flex flex-col gap-5">
          <Card className="border-white/10 bg-[#0b111b]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base text-white"><Activity className="h-4 w-4 text-cyan-300" /> Voice providers</CardTitle>
              <CardDescription>Browser speech and server speech are separate capabilities.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-white/[0.07] p-3">
                <div><p className="text-sm font-medium text-slate-200">Browser microphone input</p><p className="mt-1 text-xs text-slate-400">Uses browser speech recognition</p></div>
                <Badge variant="outline" className={browserRecognitionSupported ? "text-emerald-200" : "text-amber-100"}>{browserRecognitionSupported ? "Supported" : "Unavailable"}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-white/[0.07] p-3">
                <div><p className="text-sm font-medium text-slate-200">Browser audio playback</p><p className="mt-1 text-xs text-slate-400">Uses browser speech synthesis</p></div>
                <Badge variant="outline" className={browserSpeechOutputSupported ? "text-emerald-200" : "text-amber-100"}>{browserSpeechOutputSupported ? "Supported" : "Unavailable"}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-white/[0.07] p-3">
                <div><p className="text-sm font-medium text-slate-200">JARVIS server ASR</p><p className="mt-1 text-xs text-slate-400">Speech recognition service</p></div>
                <Badge variant="outline">{serverFeatureLabel(voiceStatus?.asr_available)}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-white/[0.07] p-3">
                <div><p className="text-sm font-medium text-slate-200">JARVIS server TTS</p><p className="mt-1 text-xs text-slate-400">Speech output service</p></div>
                <Badge variant="outline">{serverFeatureLabel(voiceStatus?.tts_available)}</Badge>
              </div>
              <p className="text-xs leading-relaxed text-slate-500">
                Browser microphone access may require HTTPS and permission; support does not mean permission has been granted. Server status: {serverServiceLabel}. Text conversation remains available independently.
              </p>
            </CardContent>
          </Card>

          <Card className="flex-1 border-white/10 bg-[#0b111b]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base text-white"><Newspaper className="h-4 w-4 text-cyan-300" /> Society &amp; current affairs</CardTitle>
              <CardDescription>Ask for a balanced summary, with current sources when JARVIS has access to them.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs leading-relaxed text-slate-400">
              <p>JARVIS is instructed to distinguish verified recent reporting from general background and to identify when live research is unavailable.</p>
              <Button type="button" className="w-full" onClick={() => void submitMessage(SOCIETY_BRIEF_PROMPT)} disabled={isSending}>
                {isSending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Newspaper className="mr-2 h-4 w-4" />}
                Generate society briefing
              </Button>
            </CardContent>
          </Card>
        </aside>
      </div>
    </main>
  );
}
