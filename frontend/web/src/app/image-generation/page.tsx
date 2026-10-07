"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Image as ImageIcon, Loader2, Wand2, Upload, Sparkles, Download } from "lucide-react";
import { jarvisAPI, type ImageProviderStatus } from "@/lib/api";
import { getApiUrl } from "@/lib/runtime-url";
import { useChatStore } from "@/features/chat/store";
import chatApi from "@/features/chat/api";

interface GeneratedImage {
  artifact_id: string;
  url: string;
  prompt: string;
  model: string;
  width: number;
  height: number;
  mime_type: string;
}

type ProviderOption = {
  value: string;
  label: string;
};

const PROVIDERS: ProviderOption[] = [
  { value: "openai", label: "OpenAI DALL-E 3" },
  { value: "stability", label: "Stable Diffusion" },
  { value: "replicate", label: "Replicate" },
];

const SIZES = [
  { value: "1024x1024", label: "Square (1024x1024)" },
  { value: "1792x1024", label: "Landscape (1792x1024)" },
  { value: "1024x1792", label: "Portrait (1024x1792)" },
  { value: "512x512", label: "Small (512x512)" },
];

const STYLES = [
  { value: "natural", label: "Natural" },
  { value: "vivid", label: "Vivid" },
];

const OPENAI_SIZES = new Set(["1024x1024", "1792x1024", "1024x1792"]);
const NO_CHAT_SESSION = "__no_chat_session__";

export default function ImageGenerationPage() {
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const sessions = useChatStore((state) => state.sessions);
  const loadSession = useChatStore((state) => state.loadSession);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [provider, setProvider] = useState("");
  const [size, setSize] = useState("1024x1024");
  const [quality, setQuality] = useState("standard");
  const [style, setStyle] = useState("natural");
  const numImages = 1;
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(true);
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [imageObjectUrls, setImageObjectUrls] = useState<Record<string, string>>({});
  const [imageLoadErrors, setImageLoadErrors] = useState<Record<string, string>>({});
  const [providerStatus, setProviderStatus] = useState<Record<string, ImageProviderStatus>>({});
  const [providerStatusError, setProviderStatusError] = useState<string | null>(null);
  const [sessionStatusError, setSessionStatusError] = useState<string | null>(null);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [attachSessionId, setAttachSessionId] = useState<string>(
    () => useChatStore.getState().currentSessionId || NO_CHAT_SESSION,
  );
  const supportedSizes = provider === "openai"
    ? SIZES.filter((item) => OPENAI_SIZES.has(item.value))
    : SIZES.filter((item) => {
        const [width, height] = item.value.split("x").map(Number);
        return width <= 1536 && height <= 1536;
      });

  const changeProvider = (nextProvider: string) => {
    setProvider(nextProvider);
    setQuality("standard");
    setStyle("natural");
    setNegativePrompt("");
    const nextSizes = nextProvider === "openai"
      ? OPENAI_SIZES
      : new Set(SIZES.filter((item) => {
          const [width, height] = item.value.split("x").map(Number);
          return width <= 1536 && height <= 1536;
        }).map((item) => item.value));
    if (!nextSizes.has(size)) setSize("1024x1024");
  };

  useEffect(() => {
    let mounted = true;
    void chatApi.getSessions()
      .then((result) => {
        if (!mounted) return;
        useChatStore.setState({ sessions: result.sessions });
        setSessionStatusError(null);
      })
      .catch((error: unknown) => {
        if (mounted) {
          setSessionStatusError(
            error instanceof Error ? error.message : "Failed to load conversations",
          );
        }
      })
      .finally(() => {
        if (mounted) setIsLoadingSessions(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    void jarvisAPI.getImageProviderStatus()
      .then((response) => {
        if (!mounted) return;
        setProviderStatus(response.providers);
        setProviderStatusError(null);
        const firstConfigured = PROVIDERS.find((item) => response.providers[item.value]?.configured);
        if (firstConfigured) setProvider(firstConfigured.value);
      })
      .catch((error: unknown) => {
        if (mounted) {
          const message = `Failed to load provider status: ${
            error instanceof Error ? error.message : "Unknown error"
          }`;
          setProviderStatusError(message);
          toast.error(message);
        }
      })
      .finally(() => {
        if (mounted) setIsLoadingProviders(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (images.length === 0) return;

    const controller = new AbortController();
    let disposed = false;
    const objectUrls: string[] = [];

    void Promise.all(images.map(async (image) => {
      try {
        const response = await fetch(image.url, {
          credentials: "include",
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Image artifact request failed with HTTP ${response.status}`);
        }
        const blob = await response.blob();
        if (!blob.type.startsWith("image/")) {
          throw new Error("Image artifact response was not an image");
        }
        const objectUrl = URL.createObjectURL(blob);
        objectUrls.push(objectUrl);
        if (disposed) URL.revokeObjectURL(objectUrl);
        return { type: "loaded" as const, artifactId: image.artifact_id, objectUrl };
      } catch (error) {
        if (controller.signal.aborted) return null;
        return {
          type: "failed" as const,
          artifactId: image.artifact_id,
          error: error instanceof Error ? error.message : "Failed to load generated image",
        };
      }
    }))
      .then((results) => {
        if (disposed) return;
        const loaded: Record<string, string> = {};
        const failed: Record<string, string> = {};
        results.forEach((result) => {
          if (!result) return;
          if (result.type === "loaded") loaded[result.artifactId] = result.objectUrl;
          else failed[result.artifactId] = result.error;
        });
        setImageObjectUrls(loaded);
        setImageLoadErrors(failed);
        Object.values(failed).forEach((error) => toast.error(error));
      });

    return () => {
      disposed = true;
      controller.abort();
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [images]);

  const generateImages = async () => {
    if (providerStatusError) {
      toast.error(providerStatusError);
      return;
    }
    if (!prompt.trim()) {
      toast.error("Please enter a prompt");
      return;
    }

    if (!providerStatus[provider]?.configured) {
      toast.error("Selected provider is not configured. Add its settings first.");
      return;
    }

    setIsGenerating(true);
    setImages([]);
    setImageObjectUrls({});
    setImageLoadErrors({});

    try {
      const data = await jarvisAPI.generateImage({
          prompt,
          session_id: attachSessionId === NO_CHAT_SESSION ? undefined : attachSessionId,
          provider,
          size,
          quality: provider === "openai" ? quality : "standard",
          style: provider === "openai" ? style : null,
          negative_prompt: provider === "replicate" ? negativePrompt || null : null,
          num_images: numImages,
      });

      if (data.success) {
        setImages(data.images.map((image) => ({
          ...image,
          url: getApiUrl(image.url),
        })));
        if (data.conversation_messages && attachSessionId === currentSessionId) {
          const messages = data.conversation_messages;
          useChatStore.setState((state) => state.currentSessionId === currentSessionId
            && !messages.some((message) => state.messages.some((item) => item.id === message.id))
            ? {
                messages: [
                  ...state.messages,
                  ...messages.map((message) => ({
                    id: message.id,
                    role: message.role,
                    content: message.content,
                    timestamp: message.timestamp,
                    provider: message.provider,
                    metadata: message.metadata,
                    status: "COMPLETED" as const,
                  })),
                ],
              }
            : state);
        }
        toast.success(`Generated ${data.count} image(s)`);
      } else {
        toast.error(data.detail || "Generation failed");
      }
    } catch (error) {
      toast.error(
        `Generation error: ${
          error instanceof Error ? error.message : "Unknown error"
        }`,
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadImage = (image: GeneratedImage) => {
    const objectUrl = imageObjectUrls[image.artifact_id];
    if (!objectUrl) return;
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `jarvis-image-${image.artifact_id}`;
    link.click();
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-3 rounded-xl bg-gradient-to-br from-amber-500 to-rose-500">
          <Wand2 className="w-8 h-8 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">Image Generation</h1>
          <p className="text-muted-foreground">Create images with the providers configured in JARVIS settings</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              Settings
            </CardTitle>
            <CardDescription>Configure your generation provider and output</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label htmlFor="image-chat-session" className="text-sm font-medium mb-2 block">
                Attach to conversation
              </label>
              <Select
                value={attachSessionId}
                onValueChange={(sessionId) => {
                  if (sessionId === NO_CHAT_SESSION) {
                    setAttachSessionId(NO_CHAT_SESSION);
                    return;
                  }
                  setAttachSessionId(sessionId);
                  void loadSession(sessionId);
                }}
              >
                <SelectTrigger id="image-chat-session">
                  <SelectValue placeholder="Choose a conversation" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_CHAT_SESSION}>Do not attach to chat</SelectItem>
                  {sessions.map((session) => (
                    <SelectItem key={session.session_id} value={session.session_id}>
                      {session.preview || "New conversation"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-muted-foreground">
                Generated artifacts appear in this conversation&apos;s history.
              </p>
              {sessionStatusError && (
                <p role="alert" className="mt-1 text-xs text-destructive">
                  Conversations unavailable: {sessionStatusError}
                </p>
              )}
              {isLoadingSessions && (
                <p role="status" className="mt-1 text-xs text-muted-foreground">
                  Loading conversations…
                </p>
              )}
            </div>

            <div>
              <label htmlFor="image-provider" className="text-sm font-medium mb-2 block">Provider</label>
              <Select value={provider} onValueChange={changeProvider}>
                <SelectTrigger id="image-provider">
                  <SelectValue placeholder="Select configured provider" />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((item) => (
                    <SelectItem
                      key={item.value}
                      value={item.value}
                      disabled={!providerStatus[item.value]?.configured}
                    >
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-wrap gap-2">
              {PROVIDERS.map((item) => (
                <Badge
                  key={item.value}
                  variant={providerStatus[item.value]?.configured ? "default" : "outline"}
                >
                  {item.label} · {providerStatus[item.value]?.status ?? "UNKNOWN"}
                </Badge>
              ))}
            </div>
            {providerStatusError ? (
              <p role="alert" className="text-sm text-destructive">{providerStatusError}</p>
            ) : !isLoadingProviders && !PROVIDERS.some((item) => providerStatus[item.value]?.configured) ? (
              <p className="text-sm text-muted-foreground">
                No image provider is configured on the backend.
              </p>
            ) : null}

            <div>
              <label htmlFor="image-size" className="text-sm font-medium mb-2 block">Size</label>
              <Select value={size} onValueChange={setSize}>
                <SelectTrigger id="image-size">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {supportedSizes.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {provider === "openai" && (
              <>
                <div>
                  <label htmlFor="image-style" className="text-sm font-medium mb-2 block">Style</label>
                  <Select value={style} onValueChange={setStyle}>
                    <SelectTrigger id="image-style">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STYLES.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant={quality === "standard" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setQuality("standard")}
                  >
                    Standard
                  </Button>
                  <Button
                    variant={quality === "hd" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setQuality("hd")}
                  >
                    HD
                  </Button>
                </div>
              </>
            )}

            <Button
              onClick={generateImages}
              disabled={
                isGenerating ||
                isLoadingProviders ||
                Boolean(providerStatusError) ||
                !providerStatus[provider]?.configured ||
                !prompt.trim()
              }
              className="w-full"
              size="lg"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Wand2 className="w-5 h-5 mr-2" />
                  Generate
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ImageIcon className="w-5 h-5" aria-hidden="true" />
              Prompt & Results
            </CardTitle>
            <CardDescription>Describe what you want to create</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="A futuristic city with flying cars and neon lights at sunset, cinematic view..."
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="min-h-[120px] text-lg"
            />

            {provider === "replicate" && (
              <Textarea
                placeholder="Negative prompt: blur, low quality, distortion..."
                value={negativePrompt}
                onChange={(event) => setNegativePrompt(event.target.value)}
                className="min-h-[80px]"
              />
            )}

            {images.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold mb-4">Generated Images</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {images.map((image, index) => (
                    <div key={image.artifact_id} className="relative group">
                      {imageObjectUrls[image.artifact_id] ? (
                        <img
                          src={imageObjectUrls[image.artifact_id]}
                          alt={`Generated ${index + 1}`}
                          className="w-full rounded-lg border"
                        />
                      ) : imageLoadErrors[image.artifact_id] ? (
                        <div className="flex aspect-square items-center justify-center rounded-lg border text-sm text-destructive" role="alert">
                          {imageLoadErrors[image.artifact_id]}
                        </div>
                      ) : (
                        <div
                          className="flex aspect-square items-center justify-center rounded-lg border"
                          role="status"
                        >
                          <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
                          <span className="sr-only">Loading generated image</span>
                        </div>
                      )}
                      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={!imageObjectUrls[image.artifact_id]}
                          onClick={() => downloadImage(image)}
                        >
                          <Download className="w-4 h-4 mr-1" />
                          Download
                        </Button>
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        <Badge variant="outline">{image.model}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {image.width}x{image.height}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!images.length && !isGenerating && (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Upload className="w-12 h-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  {isLoadingProviders
                    ? "Loading provider settings..."
                    : "Enter a prompt and click Generate to create images"}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
