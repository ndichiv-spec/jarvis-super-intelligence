"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Image, Loader2, Wand2, Upload, Sparkles, Download } from "lucide-react";
import { jarvisAPI, type ProviderFeatureStatus } from "@/lib/api";

interface GeneratedImage {
  url?: string;
  base64?: string;
  prompt: string;
  model: string;
  width: number;
  height: number;
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
  const [isLoadingProviders, setIsLoadingProviders] = useState(true);
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [providerStatus, setProviderStatus] = useState<Record<string, ProviderFeatureStatus>>({});

  useEffect(() => {
    void loadProviderStatus();
  }, []);

  const loadProviderStatus = async () => {
    setIsLoadingProviders(true);
    try {
      const response = await jarvisAPI.getProviderSettings();
      setProviderStatus(response.providers);

      const firstConfigured = PROVIDERS.find((item) => response.providers[item.value]?.configured);
      if (firstConfigured) {
        setProvider(firstConfigured.value);
      }
    } catch (error: any) {
      toast.error(`Failed to load provider status: ${error.message}`);
    } finally {
      setIsLoadingProviders(false);
    }
  };

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

    try {
      const data = await jarvisAPI.generateImage({
          prompt,
          provider,
          size,
          quality,
          style,
          negative_prompt: negativePrompt || null,
          num_images: numImages,
      });

      if (data.success) {
        setImages(data.images);
        toast.success(`Generated ${data.count} image(s)`);
      } else {
        toast.error(data.detail || "Generation failed");
      }
    } catch (error: any) {
      toast.error(`Generation error: ${error.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const downloadImage = (image: GeneratedImage) => {
    if (image.base64) {
      const link = document.createElement("a");
      link.href = `data:image/png;base64,${image.base64}`;
      link.download = `jarvis-image-${Date.now()}.png`;
      link.click();
      return;
    }

    if (image.url) {
      window.open(image.url, "_blank", "noopener,noreferrer");
    }
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
              <label className="text-sm font-medium mb-2 block">Provider</label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger>
                  <SelectValue />
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
                  {item.label}
                </Badge>
              ))}
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block">Size</label>
              <Select value={size} onValueChange={setSize}>
                <SelectTrigger>
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
              <label className="text-sm font-medium mb-2 block">Style</label>
              <Select value={style} onValueChange={setStyle}>
                <SelectTrigger>
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

            <Button
              onClick={generateImages}
              disabled={isGenerating || isLoadingProviders || !prompt.trim()}
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
              <Image className="w-5 h-5" />
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

            <Textarea
              placeholder="Negative prompt: blur, low quality, distortion..."
              value={negativePrompt}
              onChange={(event) => setNegativePrompt(event.target.value)}
              className="min-h-[80px]"
            />

            {images.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold mb-4">Generated Images</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {images.map((image, index) => (
                    <div key={index} className="relative group">
                      <img
                        src={image.base64 ? `data:image/png;base64,${image.base64}` : image.url}
                        alt={`Generated ${index + 1}`}
                        className="w-full rounded-lg border"
                      />
                      <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-2">
                        <Button size="sm" variant="secondary" onClick={() => downloadImage(image)}>
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
