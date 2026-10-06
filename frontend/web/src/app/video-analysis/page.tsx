"use client";

import { useState, useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Video, Upload, Play, Pause, Film, Frame, Search, Activity, Timer, FileVideo } from "lucide-react";
import { getApiUrl } from "@/lib/runtime-url";

interface VideoAnalysisResult {
  success: boolean;
  duration?: number;
  frame_count?: number;
  fps?: number;
  resolution?: string;
  description?: string;
  keyframes?: any[];
  transcript?: string;
  summary?: string;
  scenes?: Array<{ start: number; end: number; description: string }>;
  error?: string;
}

export default function VideoAnalysisPage() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<VideoAnalysisResult | null>(null);
  const [analysisMode, setAnalysisMode] = useState<"upload" | "url">("upload");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files[0]) {
      setVideoFile(files[0]);
      setResult(null);
    }
  };

  const analyzeVideo = async () => {
    const videoSource = analysisMode === "upload" ? videoFile : videoUrl;
    
    if (!videoSource) {
      toast.error("Please provide a video file or URL");
      return;
    }

    setIsAnalyzing(true);

    try {
      let endpoint = "";
      let body: any = {};

      if (analysisMode === "upload" && videoFile) {
        const formData = new FormData();
        formData.append("file", videoFile);
        
        const response = await fetch(
          getApiUrl('/api/v1/video/analyze'),
          { method: "POST", body: formData }
        );
        const data = await response.json();
        setResult(data);
      } else {
        endpoint = getApiUrl('/api/v1/video/analyze');
        body = { video_url: videoUrl };
        
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await response.json();
        setResult(data);
      }

      toast.success("Video analysis complete");
    } catch (error: any) {
      toast.error(`Analysis failed: ${error.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const extractFrames = async () => {
    if (!videoUrl && !videoFile) {
      toast.error("Please provide a video");
      return;
    }

    setIsAnalyzing(true);

    try {
      const formData = new FormData();
      if (videoFile) {
        formData.append("file", videoFile);
      }
      formData.append("num_frames", "10");

      const response = await fetch(
        getApiUrl('/api/v1/video/extract-frames'),
        { method: "POST", body: formData }
      );
      const data = await response.json();
      setResult(data);
      toast.success(`Extracted ${data.frame_count} frames`);
    } catch (error: any) {
      toast.error(`Extraction failed: ${error.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const getVideoInfo = async () => {
    if (!videoUrl && !videoFile) {
      toast.error("Please provide a video");
      return;
    }

    setIsAnalyzing(true);

    try {
      const formData = new FormData();
      if (videoFile) {
        formData.append("file", videoFile);
      }

      const response = await fetch(
        getApiUrl('/api/v1/video/info'),
        { method: "POST", body: formData }
      );
      const data = await response.json();
      setResult(data);
      toast.success("Got video info");
    } catch (error: any) {
      toast.error(`Failed: ${error.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-3 rounded-xl bg-gradient-to-br from-orange-500 to-red-500">
          <Video className="w-8 h-8 text-white" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">Video Analysis</h1>
          <p className="text-muted-foreground">Analyze video content with AI vision</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="w-5 h-5" />
              Input Video
            </CardTitle>
            <CardDescription>Upload or provide video URL</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Tabs value={analysisMode} onValueChange={(v) => setAnalysisMode(v as "upload" | "url")}>
              <TabsList className="w-full">
                <TabsTrigger value="upload" className="flex-1">Upload</TabsTrigger>
                <TabsTrigger value="url" className="flex-1">URL</TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="space-y-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="video/*"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <Button
                  variant="outline"
                  className="w-full h-32 flex flex-col gap-2"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <FileVideo className="w-8 h-8" />
                  {videoFile ? videoFile.name : "Click to upload video"}
                </Button>
              </TabsContent>

              <TabsContent value="url" className="space-y-4">
                <Input
                  placeholder="https://example.com/video.mp4"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                />
              </TabsContent>
            </Tabs>

            <div className="flex gap-2">
              <Button onClick={analyzeVideo} disabled={isAnalyzing} className="flex-1">
                <Video className="w-4 h-4 mr-2" />
                Analyze
              </Button>
              <Button onClick={extractFrames} disabled={isAnalyzing} variant="outline">
                <Frame className="w-4 h-4 mr-2" />
                Frames
              </Button>
              <Button onClick={getVideoInfo} disabled={isAnalyzing} variant="outline">
                <Activity className="w-4 h-4 mr-2" />
                Info
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Film className="w-5 h-5" />
              Analysis Results
            </CardTitle>
          </CardHeader>
          <CardContent>
            {result ? (
              <div className="space-y-4">
                {result.duration && (
                  <div className="flex items-center gap-2">
                    <Timer className="w-4 h-4" />
                    <Badge variant="outline">Duration: {result.duration}s</Badge>
                  </div>
                )}
                {result.fps && (
                  <Badge variant="outline">FPS: {result.fps}</Badge>
                )}
                {result.resolution && (
                  <Badge variant="outline">{result.resolution}</Badge>
                )}
                {result.frame_count && (
                  <Badge variant="outline">{result.frame_count} frames</Badge>
                )}
                
                {result.description && (
                  <div className="mt-4">
                    <h4 className="font-semibold mb-2">Description</h4>
                    <p className="text-sm text-muted-foreground">{result.description}</p>
                  </div>
                )}

                {result.scenes && result.scenes.length > 0 && (
                  <div className="mt-4">
                    <h4 className="font-semibold mb-2">Scenes</h4>
                    <div className="space-y-2">
                      {result.scenes.map((scene, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-sm">
                          <Badge variant="secondary">
                            {scene.start.toFixed(1)}s - {scene.end.toFixed(1)}s
                          </Badge>
                          <span>{scene.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {result.summary && (
                  <div className="mt-4">
                    <h4 className="font-semibold mb-2">Summary</h4>
                    <p className="text-sm">{result.summary}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Film className="w-12 h-12 text-muted-foreground mb-4" />
                <p className="text-muted-foreground">Upload a video and select an action</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
