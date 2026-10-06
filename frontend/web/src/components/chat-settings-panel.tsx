"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  ChevronUp,
  ThermometerSun,
  Layers,
  Hash,
  Globe,
  Code,
  Save,
} from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore } from "@/features/chat/store";
import type { ChatSettings } from "@/features/chat/types";

/**
 * ChatSettingsPanel
 *
 * A collapsible panel that lets users tune per-chat generation parameters
 * (temperature, top-p, max tokens, system prompt, web search, code interpreter).
 * Settings are persisted in the Zustand chat store and sent with every
 * streaming request to `/api/chat/stream`.
 */
export default function ChatSettingsPanel() {
  const { chatSettings, updateChatSettings } = useChatStore((state) => ({
    chatSettings: state.chatSettings,
    updateChatSettings: state.updateChatSettings,
  }));

  const [expanded, setExpanded] = React.useState(false);

  const handleSliderChange = (field: keyof ChatSettings, value: number[]) => {
    updateChatSettings({ [field]: value[0] });
  };

  const handleToggle = (field: keyof ChatSettings) => {
    updateChatSettings({ [field]: !chatSettings[field] });
  };

  return (
    <div className="border-t border-white/5">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-left hover:bg-white/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
      >
        <span className="text-xs font-medium text-gray-400 flex items-center gap-1">
          <Save className="h-3 w-3" />
          Chat Settings
        </span>
        <span aria-hidden="true" className="text-gray-400">
          {expanded ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="px-4 pb-3 space-y-3 overflow-hidden"
          >
            {/* Temperature */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <ThermometerSun className="h-3 w-3" />
                  Temperature
                </div>
                <span className="text-xs text-cyan-400">
                  {chatSettings.temperature.toFixed(1)}
                </span>
              </div>
              <Slider
                aria-label="Temperature"
                value={[chatSettings.temperature]}
                onValueChange={(v) => handleSliderChange("temperature", v)}
                min={0}
                max={2}
                step={0.1}
              />
            </div>

            {/* Top-P */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <Layers className="h-3 w-3" />
                  Top-P
                </div>
                <span className="text-xs text-cyan-400">
                  {chatSettings.top_p.toFixed(2)}
                </span>
              </div>
              <Slider
                aria-label="Top-P"
                value={[chatSettings.top_p]}
                onValueChange={(v) => handleSliderChange("top_p", v)}
                min={0.1}
                max={1}
                step={0.05}
              />
            </div>

            {/* Max tokens */}
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <Hash className="h-3 w-3" />
                  Max Tokens
                </div>
                <span className="text-xs text-cyan-400">
                  {chatSettings.max_tokens.toLocaleString()}
                </span>
              </div>
              <Slider
                aria-label="Max Tokens"
                value={[chatSettings.max_tokens]}
                onValueChange={(v) => handleSliderChange("max_tokens", v)}
                min={256}
                max={32768}
                step={256}
              />
            </div>

            {/* System prompt */}
            <div className="space-y-1">
              <label htmlFor="chat-system-prompt" className="text-xs text-gray-400 flex items-center gap-1">
                <Code className="h-3 w-3" />
                System Prompt
              </label>
              <Textarea
                id="chat-system-prompt"
                value={chatSettings.system_prompt || ""}
                onChange={(e) =>
                  updateChatSettings({ system_prompt: e.target.value || undefined })
                }
                placeholder="e.g. You are a helpful assistant..."
                className="text-xs bg-white/[0.05] border-white/10 text-white placeholder:text-gray-500 resize-none"
                rows={2}
              />
            </div>

            {/* Toggles */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <Globe className="h-3 w-3" />
                  Web Search
                </div>
                <Switch
                  aria-label="Web Search"
                  checked={chatSettings.web_search || false}
                  onCheckedChange={() => handleToggle("web_search")}
                />
              </div>
              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-400 flex items-center gap-1">
                  <Code className="h-3 w-3" />
                  Code Interpreter
                </div>
                <Switch
                  aria-label="Code Interpreter"
                  checked={chatSettings.code_interpreter || false}
                  onCheckedChange={() => handleToggle("code_interpreter")}
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
