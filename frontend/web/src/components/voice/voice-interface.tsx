'use client';

import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Square, Volume2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useVoiceStore } from '@/features/voice/store';

export function VoiceInterface() {
  const {
    status,
    isSpeaking,
    isListening,
    transcript,
    speak,
    listen,
    loadStatus,
    clearTranscript,
  } = useVoiceStore();

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, [loadStatus]);

  return (
    <Card className="border-white/10 bg-white/[0.03]">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Volume2 className="h-5 w-5 text-cyan-400" />
          Voice Interface
          <Badge className="ml-2 bg-amber-500/10 text-amber-400 border-amber-500/20 text-[10px]">
            BETA
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-muted-foreground/60">
            <span className={`inline-flex h-2 w-2 rounded-full ${status?.mic_available ? 'bg-emerald-500' : 'bg-red-500'}`} />
            Mic
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground/60">
            <span className={`inline-flex h-2 w-2 rounded-full ${status?.speaker_available ? 'bg-emerald-500' : 'bg-red-500'}`} />
            Speaker
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="border-white/10 hover:bg-white/5"
            onClick={() => listen()}
            disabled={isListening}
          >
            {isListening ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Mic className="mr-2 h-4 w-4" />
            )}
            {isListening ? 'Listening...' : 'Listen'}
          </Button>

          {transcript && (
            <Button
              variant="outline"
              size="sm"
              className="border-white/10 hover:bg-white/5"
              onClick={() => speak(transcript)}
              disabled={isSpeaking}
            >
              {isSpeaking ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Volume2 className="mr-2 h-4 w-4" />
              )}
              Speak
            </Button>
          )}
        </div>

        {/* Transcript */}
        <AnimatePresence>
          {transcript && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="rounded-xl border border-white/10 bg-white/[0.02] p-3"
            >
              <div className="flex items-start justify-between">
                <p className="text-sm text-foreground/80">{transcript}</p>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground/40 hover:text-foreground"
                  onClick={clearTranscript}
                >
                  <Square className="h-3 w-3" />
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Available Voices */}
        {status?.available_voices && status.available_voices.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium text-muted-foreground/60">Available Voices</h4>
            <div className="flex flex-wrap gap-1">
              {status.available_voices.map((voice) => (
                <Badge key={voice} variant="secondary" className="text-[10px] bg-white/[0.03] border-white/5">
                  {voice}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
