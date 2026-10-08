"use client";

import React, { useState, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Mic, MicOff, Volume2, VolumeX, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";

export default function JarvisVoiceInterface() {
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [response, setResponse] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  
  const recognitionRef = useRef<any>(null);
  const synthesisRef = useRef<SpeechSynthesis | null>(null);

  useEffect(() => {
    // Check for browser support
    if (typeof window !== 'undefined') {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      
      if (SpeechRecognition) {
        recognitionRef.current = new SpeechRecognition();
        recognitionRef.current.continuous = true;
        recognitionRef.current.interimResults = true;
        recognitionRef.current.lang = 'en-US';

        recognitionRef.current.onresult = (event: any) => {
          let interimTranscript = '';
          let finalTranscript = '';

          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              finalTranscript += transcript;
            } else {
              interimTranscript += transcript;
            }
          }

          setTranscript(finalTranscript || interimTranscript);
        };

        recognitionRef.current.onerror = (event: any) => {
          console.error('Speech recognition error:', event.error);
          setIsListening(false);
        };

        recognitionRef.current.onend = () => {
          if (isListening) {
            recognitionRef.current.start();
          }
        };
      }

      synthesisRef.current = window.speechSynthesis;
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      if (synthesisRef.current) {
        synthesisRef.current.cancel();
      }
    };
  }, [isListening]);

  const startListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  };

  const speak = (text: string) => {
    if (!voiceEnabled || !synthesisRef.current) return;

    synthesisRef.current.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    synthesisRef.current.speak(utterance);
  };

  const processVoiceCommand = async () => {
    if (!transcript.trim()) return;

    setIsProcessing(true);
    
    // Simulate AI processing
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const aiResponse = `JARVIS: I heard "${transcript}". Processing your request with advanced AI capabilities...`;
    setResponse(aiResponse);
    
    if (voiceEnabled) {
      speak(aiResponse);
    }
    
    setIsProcessing(false);
    setTranscript("");
  };

  const clearConversation = () => {
    setTranscript("");
    setResponse("");
  };

  return (
    <div className="space-y-6">
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="w-5 h-5 text-purple-400" />
            JARVIS Voice Interface
          </CardTitle>
          <CardDescription>
            Voice-activated AI assistant with speech recognition and synthesis
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Voice Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                onClick={isListening ? stopListening : startListening}
                variant={isListening ? "destructive" : "default"}
                size="lg"
                className="relative"
              >
                {isListening ? (
                  <>
                    <MicOff className="w-5 h-5 mr-2" />
                    Stop Listening
                  </>
                ) : (
                  <>
                    <Mic className="w-5 h-5 mr-2" />
                    Start Listening
                  </>
                )}
                {isListening && (
                  <motion.div
                    className="absolute inset-0 bg-red-500 rounded-md"
                    animate={{ opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 1, repeat: Infinity }}
                  />
                )}
              </Button>

              <Button
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                variant="outline"
                size="lg"
              >
                {voiceEnabled ? (
                  <>
                    <Volume2 className="w-5 h-5 mr-2" />
                    Voice On
                  </>
                ) : (
                  <>
                    <VolumeX className="w-5 h-5 mr-2" />
                    Voice Off
                  </>
                )}
              </Button>
            </div>

            <div className="flex items-center gap-2">
              {isListening && (
                <Badge className="bg-red-500 animate-pulse">
                  Listening...
                </Badge>
              )}
              {isSpeaking && (
                <Badge className="bg-green-500 animate-pulse">
                  Speaking...
                </Badge>
              )}
              {isProcessing && (
                <Badge className="bg-blue-500">
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                  Processing...
                </Badge>
              )}
            </div>
          </div>

          {/* Transcript Display */}
          <div className="space-y-4">
            <div>
              <label className="text-sm text-gray-400 mb-2 block">Your Voice Input</label>
              <Textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="Speak or type your message to JARVIS..."
                className="min-h-[100px] bg-white/[0.02] border-white/10 text-white"
                disabled={isListening}
              />
            </div>

            <div className="flex gap-2">
              <Button
                onClick={processVoiceCommand}
                disabled={!transcript.trim() || isProcessing}
                className="flex-1"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    Send to JARVIS
                  </>
                )}
              </Button>
              
              <Button
                onClick={clearConversation}
                variant="outline"
              >
                Clear
              </Button>
            </div>
          </div>

          {/* JARVIS Response */}
          {response && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="p-4 bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg border border-purple-500/20"
            >
              <div className="flex items-start gap-3">
                <div className="p-2 bg-purple-500 rounded-full">
                  <Mic className="w-4 h-4 text-white" />
                </div>
                <div className="flex-1">
                  <p className="text-white">{response}</p>
                </div>
              </div>
            </motion.div>
          )}
        </CardContent>
      </Card>

      {/* Voice Commands Reference */}
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="text-lg">Voice Commands</CardTitle>
          <CardDescription>
            Available voice commands for JARVIS
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              "What's the system status?",
              "Show me the advanced agents",
              "Display quantum states",
              "Open the 3D visualization",
              "Check neural network activity",
              "What are the current tasks?",
              "Optimize the system",
              "Show me the full potential"
            ].map((command, idx) => (
              <div
                key={idx}
                className="p-3 bg-white/[0.02] rounded border border-white/5 hover:border-purple-500/30 transition-colors cursor-pointer"
                onClick={() => setTranscript(command)}
              >
                <p className="text-sm text-white">{command}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Voice Settings */}
      <Card className="bg-white/[0.02] border-white/5">
        <CardHeader>
          <CardTitle className="text-lg">Voice Settings</CardTitle>
          <CardDescription>
            Configure voice recognition and synthesis
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white font-medium">Voice Output</p>
              <p className="text-sm text-gray-400">Enable JARVIS voice responses</p>
            </div>
            <Button
              onClick={() => setVoiceEnabled(!voiceEnabled)}
              variant={voiceEnabled ? "default" : "outline"}
              size="sm"
            >
              {voiceEnabled ? "Enabled" : "Disabled"}
            </Button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-white font-medium">Continuous Listening</p>
              <p className="text-sm text-gray-400">Keep microphone active</p>
            </div>
            <Button
              onClick={isListening ? stopListening : startListening}
              variant={isListening ? "destructive" : "outline"}
              size="sm"
            >
              {isListening ? "Stop" : "Start"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
