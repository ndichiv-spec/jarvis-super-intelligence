"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  Check,
  Power,
  Settings,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useChatStore } from "@/features/chat/store";
import type { ModelCatalog, ProviderInfo } from "@/features/chat/types";

export interface ModelSelectorProps {
  /** Show the refresh button. */
  showRefresh?: boolean;
  /** Show the settings (provider settings) button. */
  showSettings?: boolean;
  /** Compact mode for toolbar integration. */
  compact?: boolean;
  /** Callback fired when the model changes. */
  onModelChange?: (model: string) => void;
}

/**
 * ModelSelector
 *
 * A standalone, reusable dropdown for selecting an AI provider + model
 * combination. Reads its data from the Zustand chat store's model catalog,
 * which is populated from `GET /api/v1/ai/models`.
 *
 * When `compact` is true the selector renders as a small badge-style button
 * suitable for a toolbar; otherwise it renders the full select with labels.
 */
export default function ModelSelector({
  showRefresh = true,
  showSettings = false,
  compact = false,
  onModelChange,
}: ModelSelectorProps) {
  const {
    activeModel,
    modelCatalog,
    availableProviders,
    setActiveModel,
    loadModelCatalog,
  } = useChatStore((state) => ({
    activeModel: state.activeModel,
    modelCatalog: state.modelCatalog,
    availableProviders: state.availableProviders,
    setActiveModel: state.setActiveModel,
    loadModelCatalog: state.loadModelCatalog,
  }));

  const [isRefreshing, setIsRefreshing] = React.useState(false);
  const [isOpen, setIsOpen] = React.useState(false);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      await loadModelCatalog();
    } finally {
      setIsRefreshing(false);
    }
  };

  // Build the display label for the currently selected model.
  const selectedProvider = modelCatalog?.providers.find(
    (p) => `${p.provider}:${p.model}` === activeModel || p.provider === activeModel
  );
  const selectedLabel =
    selectedProvider?.display_name ||
    selectedProvider?.provider ||
    activeModel ||
    "Select model";

  React.useEffect(() => {
    if (!modelCatalog) {
      void handleRefresh();
    }
  }, []);

  // --- Compact button variant (toolbar) ---
  if (compact) {
    return (
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1 text-xs border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
          onClick={() => setIsOpen(true)}
        >
          <span className="max-w-[120px] truncate">{selectedLabel}</span>
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
        {showRefresh && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            onClick={handleRefresh}
            disabled={isRefreshing}
            title="Refresh models"
          >
            <RefreshCw
              className={`h-3 w-3 ${isRefreshing ? "animate-spin" : ""}`}
            />
          </Button>
        )}

        {/* Compact modal-style selector */}
        {isOpen && (
          <CompactModelSheet
            open={isOpen}
            onOpenChange={setIsOpen}
            modelCatalog={modelCatalog}
            activeModel={activeModel}
            onModelSelect={(model) => {
              setActiveModel(model);
              onModelChange?.(model);
              setIsOpen(false);
            }}
            onRefresh={handleRefresh}
            isRefreshing={isRefreshing}
          />
        )}
      </div>
    );
  }

  // --- Full-width select variant ---
  return (
    <div className="flex items-center gap-2">
      <Select
        value={activeModel}
        onValueChange={(model) => {
          setActiveModel(model);
          onModelChange?.(model);
        }}
        disabled={isRefreshing}
      >
        <SelectTrigger className="w-64 bg-white/[0.05] border-white/10 text-sm">
          <div className="flex items-center gap-2 truncate">
            <span className="truncate">{selectedLabel}</span>
            {selectedProvider && (
              <Badge
                variant={selectedProvider.authorized ? "default" : "outline"}
                className="ml-auto text-xs"
              >
                {selectedProvider.authorized ? "ready" : "auth needed"}
              </Badge>
            )}
          </div>
        </SelectTrigger>
        <SelectContent className="bg-gray-900 border-white/10 text-gray-200">
          <SelectItem value="auto" className="focus:bg-white/[0.05]">
            <span className="flex items-center justify-between w-full">
              <span>Auto Select (JARVIS routing)</span>
              <Badge
                variant="outline"
                className="ml-2 text-xs bg-cyan-500/10 text-cyan-300"
              >
                recommended
              </Badge>
            </span>
          </SelectItem>
          {renderProviderGroups(modelCatalog, activeModel, (model) => {
            setActiveModel(model);
            onModelChange?.(model);
          }, isRefreshing)}
        </SelectContent>
      </Select>

      {showRefresh && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 hover:bg-white/[0.05]"
          onClick={handleRefresh}
          disabled={isRefreshing}
          title="Refresh models"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`}
          />
        </Button>
      )}

      {showSettings && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 hover:bg-white/[0.05]"
          onClick={() => {
            // Navigate to system provider settings
            window.location.href = "/dashboard/system?tab=provider-settings";
          }}
          title="Provider settings"
        >
          <Settings className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

// --- Helper: render provider groups inside the Select ---
function renderProviderGroups(
  modelCatalog: ModelCatalog | null,
  activeModel: string,
  onSelect: (model: string) => void,
  disabled: boolean
): React.ReactNode {
  if (!modelCatalog) {
    return (
      <SelectItem value="loading" disabled>
        <span className="text-xs text-gray-500 flex items-center gap-2">
          <RefreshCw className="h-3 w-3 animate-spin" />
          Loading models…
        </span>
      </SelectItem>
    );
  }

  // Group providers: available first, then unavailable
  const available = modelCatalog.providers.filter((p) => p.available);
  const unavailable = modelCatalog.providers.filter((p) => !p.available);

  const renderProvider = (p: ProviderInfo) => {
    const baseKey = p.provider;
    const modelOptions = p.models.length > 0 ? p.models : [p.model];

    if (modelOptions.length <= 1) {
      const value = `${p.provider}:${modelOptions[0]}`;
      return (
        <SelectItem
          key={value}
          value={value}
          disabled={!p.available || disabled}
          className="focus:bg-white/[0.05]"
        >
          <div className="flex flex-col w-full">
            <span className="flex items-center">
              {p.display_name || p.provider} — {modelOptions[0]}
              {!p.available && (
                <Badge
                  variant="outline"
                  className="ml-2 text-xs text-red-400"
                >
                  unavailable
                </Badge>
              )}
            </span>
            {p.authorized && (
              <span className="text-xs text-gray-500">
                {p.latency_ms ? `${p.latency_ms}ms latency` : "authorized"}
              </span>
            )}
          </div>
        </SelectItem>
      );
    }

    // Multiple models for this provider — render a sub-group
    return modelOptions.map((m) => {
      const value = `${p.provider}:${m}`;
      return (
        <SelectItem
          key={value}
          value={value}
          disabled={!p.available || disabled}
          className="focus:bg-white/[0.05]"
        >
          <div className="flex flex-col w-full">
            <span className="flex items-center">
              {p.display_name || p.provider} — {m}
              {!p.available && (
                <Badge
                  variant="outline"
                  className="ml-2 text-xs text-red-400"
                >
                  unavailable
                </Badge>
              )}
            </span>
            {p.authorized && (
              <span className="text-xs text-gray-500">
                {p.latency_ms ? `${p.latency_ms}ms latency` : "authorized"}
              </span>
            )}
          </div>
        </SelectItem>
      );
    });
  };

  return (
    <>
      {available.length > 0 && (
        <div className="py-1">
          <div className="px-2 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Available
          </div>
          {available.map(renderProvider)}
        </div>
      )}
      {unavailable.length > 0 && (
        <div className="py-1">
          <div className="px-2 py-1.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Configured (unavailable)
          </div>
          {unavailable.map(renderProvider)}
        </div>
      )}
    </>
  );
}

/**
 * Compact modal-style model selector for toolbar integration.
 * Uses a dialog-like overlay with a searchable model list.
 */
function CompactModelSheet({
  open,
  onOpenChange,
  modelCatalog,
  activeModel,
  onModelSelect,
  onRefresh,
  isRefreshing,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelCatalog: ModelCatalog | null;
  activeModel: string;
  onModelSelect: (model: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}) {
  const providers = modelCatalog?.providers ?? [];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => onOpenChange(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ type: "spring", duration: 0.2 }}
            className="w-full max-w-md rounded-xl border border-white/10 bg-[hsl(222,47%,10%)] p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">
                Select Model
              </h3>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={onRefresh}
                disabled={isRefreshing}
              >
                <RefreshCw
                  className={`h-3 w-3 ${isRefreshing ? "animate-spin" : ""}`}
                />
              </Button>
            </div>

            <div className="space-y-1 max-h-80 overflow-y-auto">
              <button
                className={`
                  flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm
                  ${
                    activeModel === "auto"
                      ? "bg-cyan-500/10 text-cyan-300"
                      : "hover:bg-white/[0.04] text-gray-300"
                  }
                `}
                onClick={() => {
                  onModelSelect("auto");
                  onOpenChange(false);
                }}
              >
                <Check
                  className={`h-4 w-4 ${
                    activeModel === "auto" ? "text-cyan-400" : "opacity-0"
                  }`}
                />
                Auto Select (JARVIS routing)
              </button>

              {providers.map((p) => {
                const modelOptions = p.models.length > 0 ? p.models : [p.model];
                return modelOptions.map((m) => {
                  const value = `${p.provider}:${m}`;
                  return (
                    <button
                      key={value}
                      className={`
                        flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm
                        ${
                          activeModel === value
                            ? "bg-cyan-500/10 text-cyan-300"
                            : "hover:bg-white/[0.04] text-gray-300"
                        }
                        ${!p.available ? "opacity-50" : ""}
                      `}
                      onClick={() => {
                        if (!p.available) return;
                        onModelSelect(value);
                        onOpenChange(false);
                      }}
                      disabled={!p.available}
                    >
                      <div className="flex items-center gap-2">
                        <Check
                          className={`h-4 w-4 ${
                            activeModel === value
                              ? "text-cyan-400"
                              : "opacity-0 group-hover:opacity-30"
                          }`}
                        />
                        <span>
                          {p.display_name || p.provider} — {m}
                        </span>
                      </div>
                      {p.authorized ? (
                        <CheckCircle2 className="h-3 w-3 text-green-400" />
                      ) : (
                        <AlertCircle className="h-3 w-3 text-amber-400" />
                      )}
                    </button>
                  );
                });
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
