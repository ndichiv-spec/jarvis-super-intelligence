"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, Download, ExternalLink, Image as ImageIcon, Loader2, Sparkles, Wand2 } from "lucide-react";
import { jarvisAPI, type ProviderFeatureStatus } from "@/lib/api";

interface GeneratedImage {
  url?: string;
  base64?: string;
  prompt: string;
  model: string;
  width: number;
  height: number;
}

interface ImageGenerationResponse {
  success?: boolean;
  images?: GeneratedImage[];
  count?: number;
  detail?: string;
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
  { value: "digital-art", label: "Digital Art" },
  { value: "anime", label: "Anime" },
  { value: "photographic", label: "Photographic" },
  { value: "3d-render", label: "3D Render" },
];

export default function ImageGenerationPage() {
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [provider, setProvider] = useState("openai");
  const [size, setSize] = useState("1024x1024");
  const [quality, setQuality] = useState("standard");
  const [style, setStyle] = useState("natural");
  const numImages = 1;
  const [isGenerating, setIsGenerating] = useState(false);
  const [isAssisting, setIsAssisting] = useState(false);
  const [isLoadingProviders, setIsLoadingProviders] = useState(true);
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [providerStatus, setProviderStatus] = useState<Record<string, ProviderFeatureStatus>>({});
  const [providerError, setProviderError] = useState("");
  const [generationError, setGenerationError] = useState("");

  useEffect(() => {
    let active = true;
    void jarvisAPI.getProviderSettings()
      .then((response) => {
        if (!active) return;
        setProviderStatus(response.providers);
        const firstConfigured = PROVIDERS.find((item) => response.providers[item.value]?.configured);
        if (firstConfigured) setProvider(firstConfigured.value);
      })
      .catch((error: unknown) => {
        if (active) {
          const message = `Failed to load provider status: ${error instanceof Error ? error.message : "Unknown error"}`;
          setProviderError(message);
          toast.error(message);
        }
      })
      .finally(() => {
        if (active) setIsLoadingProviders(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const generateImages = async () => {
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
    setGenerationError("");

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1/image/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt,
          provider,
          size,
          quality,
          style,
          negative_prompt: negativePrompt || null,
          num_images: numImages,
        }),
      });

      const data = await response.json() as ImageGenerationResponse;
      if (!response.ok) {
        throw new Error(data.detail || `Image generation failed (HTTP ${response.status})`);
      }

      const generatedImages = Array.isArray(data.images)
        ? data.images.filter((image) => image && (image.base64 || image.url))
        : [];
      if (data.success && generatedImages.length > 0) {
        setImages(generatedImages);
        toast.success(`Generated ${data.count ?? generatedImages.length} image(s)`);
      } else {
        const message = data.detail || "The provider returned no generated images.";
        setGenerationError(message);
        toast.error(message);
      }
    } catch (error) {
      const message = `Generation error: ${error instanceof Error ? error.message : "Unknown error"}`;
      setGenerationError(message);
      toast.error(message);
    } finally {
      setIsGenerating(false);
    }
  };

  const refinePromptWithJarvis = async () => {
    if (!prompt.trim()) {
      toast.error("Describe the image you want JARVIS to refine");
      return;
    }
    setIsAssisting(true);
    try {
      const response = await jarvisAPI.starkChat({
        message: `Turn this image idea into a vivid, specific image-generation prompt. Preserve the user's intent, avoid adding text or logos unless requested, and return only the improved prompt:\n\n${prompt.trim()}`,
        context: { surface: "image-generation", task: "refine-image-prompt" },
      });
      if (!response.success || !response.response?.trim()) {
        throw new Error(response.response || "JARVIS did not return an improved prompt");
      }
      setPrompt(response.response.trim());
      toast.success("Prompt refined by JARVIS");
    } catch (error) {
      toast.error(`Prompt assistance failed: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsAssisting(false);
    }
  };

  const downloadImage = (image: GeneratedImage) => {
    if (image.base64) {
      const link = document.createElement("a");
      link.href = `data:image/png;base64,${image.base64}`;
      link.download = `jarvis-image-${crypto.randomUUID()}.png`;
      link.click();
      return;
    }

    if (image.url) {
      window.open(image.url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-4rem)] w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-cyan-200/15 bg-cyan-200/[0.05] text-cyan-100">
            <Wand2 aria-hidden="true" className="h-5 w-5" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-200/70">JARVIS · Creative workspace</p>
            <h1 className="mt-1 text-2xl font-semibold text-white md:text-3xl">Image generation</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">Build a prompt, choose a configured provider and output settings, then download the returned image.</p>
          </div>
        </div>
        <div className="inline-flex items-center gap-2 rounded-md border border-white/[0.08] bg-white/[0.025] px-3 py-2 text-xs text-slate-300" role="status" aria-live="polite">
          {isLoadingProviders
            ? <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin text-cyan-200 motion-reduce:animate-none" />
            : providerError
              ? <AlertCircle aria-hidden="true" className="h-3.5 w-3.5 text-amber-200" />
              : <CheckCircle2 aria-hidden="true" className="h-3.5 w-3.5 text-emerald-200" />}
          {isLoadingProviders
            ? "Checking provider settings"
            : providerError
              ? "Provider status unavailable"
              : `${PROVIDERS.filter((item) => providerStatus[item.value]?.configured).length} configured provider${PROVIDERS.filter((item) => providerStatus[item.value]?.configured).length === 1 ? "" : "s"}`}
        </div>
      </header>

      <div className="grid min-w-0 flex-1 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <Card className="order-2 border-white/10 bg-[#0b111b] lg:order-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <Sparkles className="h-5 w-5 text-cyan-200" />
              Output settings
            </CardTitle>
            <CardDescription>Only providers reported as configured can be selected.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {providerError && (
              <div role="alert" className="rounded-md border border-amber-200/15 bg-amber-200/[0.05] p-3 text-xs leading-relaxed text-amber-100">
                {providerError}
              </div>
            )}
            {!isLoadingProviders && !providerError && !PROVIDERS.some((item) => providerStatus[item.value]?.configured) && (
              <div role="status" className="rounded-md border border-dashed border-white/10 p-3 text-xs leading-relaxed text-slate-300">
                No image provider is currently reported as configured. Add provider settings before generating.
              </div>
            )}
            <div>
              <label htmlFor="image-provider" className="mb-2 block text-sm font-medium text-slate-200">Provider</label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger id="image-provider" className="border-white/10 bg-black/20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((item) => (
                    <SelectItem
                      key={item.value}
                      value={item.value}
                      disabled={isLoadingProviders || !providerStatus[item.value]?.configured}
                    >
                      {item.label} · {providerStatus[item.value]?.configured ? "Configured" : "Not configured"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <ul aria-label="Provider availability" className="space-y-2">
              {PROVIDERS.map((item) => (
                <li key={item.value} className="flex items-center justify-between gap-3 rounded-md border border-white/[0.07] px-3 py-2 text-xs">
                  <span className="text-slate-300">{item.label}</span>
                  <Badge variant="outline" className={providerStatus[item.value]?.configured ? "border-emerald-300/20 text-emerald-200" : "border-white/10 text-slate-400"}>
                    {isLoadingProviders ? "Checking" : providerStatus[item.value]?.configured ? "Configured" : providerError ? "Unverified" : "Not configured"}
                  </Badge>
                </li>
              ))}
            </ul>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-200">Output size</label>
              <Select value={size} onValueChange={setSize}>
                <SelectTrigger className="border-white/10 bg-black/20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SIZES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-200">Style</label>
              <Select value={style} onValueChange={setStyle}>
                <SelectTrigger className="border-white/10 bg-black/20">
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
                aria-pressed={quality === "standard"}
                onClick={() => setQuality("standard")}
              >
                Standard
              </Button>
              <Button
                variant={quality === "hd" ? "default" : "outline"}
                size="sm"
                aria-pressed={quality === "hd"}
                onClick={() => setQuality("hd")}
              >
                HD
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="order-1 min-w-0 border-white/10 bg-[#0b111b] lg:order-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-white">
              <ImageIcon className="h-5 w-5 text-cyan-200" />
              Prompt &amp; output
            </CardTitle>
            <CardDescription>JARVIS can refine the prompt; image generation uses the configured provider.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              aria-label="Image prompt"
              placeholder="Describe the subject, setting, composition, lighting, and visual style…"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              className="min-h-[160px] border-white/10 bg-black/20 text-base leading-relaxed"
            />
            <Button
              variant="outline"
              onClick={refinePromptWithJarvis}
              disabled={isAssisting || isGenerating || !prompt.trim()}
            >
              {isAssisting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-2 h-4 w-4" />
              )}
              {isAssisting ? "JARVIS is refining..." : "Refine with JARVIS"}
            </Button>

            <Textarea
              aria-label="Negative prompt"
              placeholder="Optional: elements or qualities to avoid"
              value={negativePrompt}
              onChange={(event) => setNegativePrompt(event.target.value)}
              className="min-h-[84px] border-white/10 bg-black/20"
            />

            <Button
              onClick={generateImages}
              disabled={isGenerating || isLoadingProviders || !!providerError || !providerStatus[provider]?.configured || !prompt.trim()}
              className="w-full sm:w-auto"
              size="lg"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Wand2 className="mr-2 h-5 w-5" />
                  Generate image
                </>
              )}
            </Button>

            {generationError && (
              <div role="alert" className="flex items-start gap-2 rounded-md border border-rose-300/15 bg-rose-300/[0.05] p-3 text-sm text-rose-100">
                <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                <p>{generationError}</p>
              </div>
            )}

            {isGenerating && (
              <div role="status" aria-live="polite" className="flex items-center gap-3 rounded-md border border-cyan-200/10 bg-cyan-200/[0.035] p-4 text-sm text-slate-300">
                <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin text-cyan-200 motion-reduce:animate-none" />
                Waiting for the configured image provider…
              </div>
            )}

            {images.length > 0 && (
              <section aria-labelledby="generated-output-heading" className="border-t border-white/[0.07] pt-5">
                <h3 id="generated-output-heading" className="mb-4 text-sm font-semibold text-slate-100">Generated output</h3>
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  {images.map((image, index) => (
                    <article key={`${image.model}-${index}`} className="overflow-hidden rounded-lg border border-white/[0.08] bg-black/20">
                      <img
                        src={image.base64 ? `data:image/png;base64,${image.base64}` : image.url}
                        alt={image.prompt || `Generated image ${index + 1}`}
                        loading="lazy"
                        decoding="async"
                        className="max-h-[560px] w-full bg-black/30 object-contain"
                      />
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.07] p-3">
                        <div className="flex min-w-0 items-center gap-2">
                          <Badge variant="outline" className="max-w-[12rem] truncate">{image.model}</Badge>
                          <span className="text-xs text-slate-400">{image.width} × {image.height}</span>
                        </div>
                        <Button size="sm" variant="outline" onClick={() => downloadImage(image)}>
                          {image.base64
                            ? <><Download aria-hidden="true" className="mr-2 h-4 w-4" /> Download</>
                            : <><ExternalLink aria-hidden="true" className="mr-2 h-4 w-4" /> Open image</>}
                        </Button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )}

            {!images.length && !isGenerating && !generationError && (
              <div className="flex min-h-52 flex-col items-center justify-center rounded-lg border border-dashed border-white/[0.09] px-5 py-10 text-center">
                <ImageIcon aria-hidden="true" className="mb-3 h-8 w-8 text-slate-500" />
                <p className="text-sm font-medium text-slate-200">Your output will appear here</p>
                <p className="mt-1 max-w-sm text-xs leading-relaxed text-slate-400">
                  {isLoadingProviders
                    ? "Checking provider settings before enabling generation."
                    : providerError
                      ? "Provider readiness could not be verified."
                      : "Enter a prompt and select a configured provider to generate one image."}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
