"use client";

import { useState, useEffect, useCallback } from "react";
import { format, formatDistanceToNow } from "date-fns";
import { toast } from "sonner";
import {
  Folder,
  File,
  FileText,
  Image,
  Code,
  Package,
  Lock,
  Trash2,
  Search,
} from "lucide-react";
import { jarvisAPI } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface FileEntry {
  name: string;
  path: string;
  size: number;
  type: string;
  modified_at: string;
  is_directory: boolean;
}

const FOLDER_ICON = Folder;
const FILE_TEXT_ICON = FileText;
const IMAGE_ICON = Image;
const CODE_ICON = Code;
const PACKAGE_ICON = Package;
const LOCK_ICON = Lock;
const DEFAULT_FILE_ICON = File;

function getFileIcon(name: string, isDir: boolean): React.ElementType {
  if (isDir) return FOLDER_ICON;
  const ext = name.split(".").pop()?.toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"].includes(ext || ""))
    return IMAGE_ICON;
  if (
    ["ts", "tsx", "js", "jsx", "py", "java", "c", "cpp", "h", "go", "rs", "rb"].includes(
      ext || ""
    )
  )
    return CODE_ICON;
  if (["json", "yaml", "yml", "toml", "ini", "cfg", "env"].includes(ext || ""))
    return PACKAGE_ICON;
  if (["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md"].includes(ext || ""))
    return FILE_TEXT_ICON;
  if (["env", "key", "pem", "cert"].includes(ext || "")) return LOCK_ICON;
  return DEFAULT_FILE_ICON;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

function BreadcrumbNav({
  currentPath,
  onNavigate,
}: {
  currentPath: string;
  onNavigate: (path: string) => void;
}) {
  // Build breadcrumb segments from the path
  const segments: { label: string; path: string }[] = [];
  const parts = currentPath.split("/").filter(Boolean);
  let cumulative = "";

  // Always show root
  segments.push({ label: "Home", path: "" });

  for (const part of parts) {
    cumulative = cumulative ? `${cumulative}/${part}` : part;
    segments.push({ label: part, path: cumulative });
  }

  return (
    <nav className="flex items-center gap-1 text-sm">
      {segments.map((seg, idx) => (
        <>
          {idx > 0 && (
            <span className="text-muted-foreground/40">›</span>
          )}
          <button
            className={`px-2 py-1 rounded hover:bg-muted/20 transition-colors ${
              idx === segments.length - 1
                ? "text-foreground font-medium"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => onNavigate(seg.path)}
            disabled={idx === segments.length - 1}
          >
            {seg.label}
          </button>
        </>
      ))}
    </nav>
  );
}

export default function FileBrowserPage() {
  const [currentPath, setCurrentPath] = useState<string>(".");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState<FileEntry | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [reading, setReading] = useState(false);
  const [filteredFiles, setFilteredFiles] = useState<FileEntry[]>([]);

  const fetchData = useCallback(async (path: string = ".") => {
    setLoading(true);
    try {
      const result = await jarvisAPI.listFiles(path);
      const entries = result.entries || result.files || [];
      setFiles(entries);
      setFilteredFiles(entries);
      setCurrentPath(result.path || path);
    } catch (error: any) {
      toast.error(`Failed to load files: ${error.message || error}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(currentPath);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPath]);

  const handleNavigate = (entry: FileEntry) => {
    if (entry.is_directory) {
      fetchData(entry.path);
      setSelectedFile(null);
      setFileContent("");
    } else {
      handleReadFile(entry);
    }
  };

  const handleReadFile = async (entry: FileEntry) => {
    setReading(true);
    setSelectedFile(entry);
    try {
      const result = await jarvisAPI.readFile(entry.path);
      setFileContent(result.content || "(empty file)");
    } catch (error: any) {
      toast.error(`Failed to read file: ${error.message || error}`);
      setFileContent("(error reading file)");
    } finally {
      setReading(false);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    if (!query.trim()) {
      setFilteredFiles(files);
    } else {
      const filtered = files.filter((f) =>
        f.name.toLowerCase().includes(query.toLowerCase())
      );
      setFilteredFiles(filtered);
    }
  };

  const handleBreadcrumbNavigate = (path: string) => {
    if (path === "") {
      fetchData(".");
    } else {
      fetchData(path);
    }
    setSelectedFile(null);
    setFileContent("");
  };

  const sortedFiles = [...filteredFiles].sort((a, b) => {
    if (a.is_directory && !b.is_directory) return -1;
    if (!a.is_directory && b.is_directory) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="h-full overflow-auto p-4 md:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">File Browser</h1>
          <p className="text-sm text-muted-foreground mt-1">
            System file explorer with real-time navigation
          </p>
        </div>

        {/* Breadcrumb */}
        <Card className="mb-4 bg-card/30 border-border">
          <CardContent className="pt-4">
            <BreadcrumbNav
              currentPath={currentPath}
              onNavigate={handleBreadcrumbNavigate}
            />
          </CardContent>
        </Card>

        {/* Search */}
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Filter files..."
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              className="pl-10"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* File listing */}
          <div className="lg:col-span-2">
            <Card className="bg-card/50 border-border h-[calc(100vh-320px)]">
              <CardHeader>
                <CardTitle className="text-lg">
                  {currentPath || "Root Directory"}
                </CardTitle>
                <CardDescription>
                  {files.length} items • Double-click a directory to navigate
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                {loading ? (
                  <div className="p-6 text-center">
                    <div className="text-muted-foreground">Loading files...</div>
                  </div>
                ) : sortedFiles.length === 0 ? (
                  <div className="p-6 text-center">
                    <Folder className="h-12 w-12 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">
                      {searchQuery ? "No matching files" : "Directory is empty"}
                    </p>
                  </div>
                ) : (
                  <ScrollArea className="h-[calc(100vh-380px)]">
                    <div className="divide-y divide-border">
                      {sortedFiles.map((entry) => {
                        const Icon = getFileIcon(entry.name, entry.is_directory);
                        return (
                          <div
                            key={entry.path}
                            className="flex items-center gap-3 p-3 hover:bg-muted/20 cursor-pointer transition-colors group"
                            onDoubleClick={() => handleNavigate(entry)}
                            onClick={() => {
                              if (!entry.is_directory) {
                                handleReadFile(entry);
                              }
                            }}
                          >
                            <Icon
                              className={`h-5 w-5 ${
                                entry.is_directory
                                  ? "text-blue-400"
                                  : "text-muted-foreground"
                              }`}
                            />
                            <div className="flex-1 min-w-0">
                              <div
                                className={`text-sm font-medium truncate ${
                                  entry.is_directory
                                    ? "text-foreground"
                                    : "text-foreground"
                                }`}
                              >
                                {entry.name}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {entry.is_directory
                                  ? "Directory"
                                  : formatFileSize(entry.size)}
                                {" • "}
                                {formatDistanceToNow(
                                  new Date(entry.modified_at),
                                  { addSuffix: true }
                                )}
                              </div>
                            </div>
                            {!entry.is_directory && (
                              <Badge
                                variant="outline"
                                className="text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                              >
                                {(entry.name.split(".").pop() || "").toUpperCase()}
                              </Badge>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </ScrollArea>
                )}
              </CardContent>
            </Card>
          </div>

          {/* File preview / details */}
          <div className="lg:col-span-1">
            <Card className="bg-card/50 border-border h-[calc(100vh-320px)]">
              <CardHeader>
                <CardTitle className="text-lg">File Preview</CardTitle>
                <CardDescription>
                  {selectedFile
                    ? selectedFile.name
                    : "Click a file to preview"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {reading ? (
                  <div className="text-center py-8">
                    <div className="text-muted-foreground">
                      Reading file...
                    </div>
                  </div>
                ) : selectedFile ? (
                  <ScrollArea className="h-[calc(100vh-420px)]">
                    <pre className="text-xs bg-muted/20 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap break-all">
                      <code>{fileContent}</code>
                    </pre>
                  </ScrollArea>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <FileText className="h-12 w-12 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm">
                      No file selected. Click a file to view its contents.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        {/* File preview dialog for larger view */}
        <Dialog
          open={!!selectedFile}
          onOpenChange={(open) => !open && setSelectedFile(null)}
        >
          <DialogContent className="max-w-4xl max-h-[80vh]">
            <DialogHeader>
              <DialogTitle>
                {selectedFile?.name}
                {selectedFile && (
                  <Badge variant="outline" className="ml-2 text-xs">
                    {(selectedFile.name.split(".").pop() || "unknown").toUpperCase()}
                  </Badge>
                )}
              </DialogTitle>
              <DialogDescription>
                Path: {selectedFile?.path} • Size:{" "}
                {selectedFile ? formatFileSize(selectedFile.size) : "—"} •
                Modified:{" "}
                {selectedFile &&
                  format(new Date(selectedFile.modified_at), "PPpp")}
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="max-h-[calc(80vh-120px)]">
              <pre className="text-xs bg-muted/20 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap break-all">
                <code>{fileContent}</code>
              </pre>
            </ScrollArea>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
