"use client";

import React, { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  FileCode, Folder, FolderOpen, Terminal, Code2, Eye,
  RefreshCw, Edit3, ChevronRight, ChevronDown, BookOpen, Brain,
  Zap, CheckCircle, FileText, X
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { jarvisAPI } from "@/lib/api";

interface FileNode {
  path: string;
  name: string;
  is_directory: boolean;
  size: number;
  extension: string;
  modified: string;
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/$/, '');
}

function parentPath(path: string): string {
  const normalized = normalizePath(path);
  return normalized.slice(0, normalized.lastIndexOf('/')) || '.';
}

export default function SelfReliantIDE() {
  const [activeTab, setActiveTab] = useState("editor");
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(["."]));
  const [showFileTree, setShowFileTree] = useState(true);
  const [fileError, setFileError] = useState<string | null>(null);
  const [rootPath, setRootPath] = useState('.');

  useEffect(() => {
    loadFileTree();
  }, []);

  async function loadFileTree(path = '.') {
    try {
      setIsLoading(true);
      const response = await jarvisAPI.listFiles(path);
      if (path === '.') setRootPath(response.path);
      const entries: FileNode[] = (response.entries || []).map((entry: {
        path: string;
        name: string;
        is_dir: boolean;
        size: number | null;
      }) => ({
        path: entry.path,
        name: entry.name,
        is_directory: entry.is_dir,
        size: entry.size ?? 0,
        extension: entry.is_dir ? '' : entry.name.includes('.') ? `.${entry.name.split('.').pop()}` : '',
        modified: '',
      }));
      setFileTree((current) => {
        const remaining = current.filter((file) => {
          return parentPath(file.path) !== normalizePath(response.path);
        });
        return [...remaining, ...entries];
      });
      setFileError(null);
    } catch (error) {
      setFileError(error instanceof Error ? error.message : 'Workspace file listing is unavailable.');
    } finally {
      setIsLoading(false);
    }
  }

  const openFile = async (filePath: string) => {
    try {
      setIsLoading(true);
      setSelectedFile(filePath);

      const response = await jarvisAPI.readFile(filePath);
      if (typeof response.content !== 'string') throw new Error('The file service returned no content.');
      setFileContent(response.content);
      setFileError(null);
      toast.success(`Read ${filePath}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'File contents are unavailable.';
      setFileError(message);
      toast.error(`Failed to open file: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleFolder = async (path: string) => {
    const newExpanded = new Set(expandedFolders);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      await loadFileTree(path);
      newExpanded.add(path);
    }
    setExpandedFolders(newExpanded);
  };

  const getFileIcon = (file: FileNode) => {
    if (file.is_directory) {
      return expandedFolders.has(file.path) ? FolderOpen : Folder;
    }
    if (file.extension === '.py') return FileCode;
    if (file.extension === '.js' || file.extension === '.jsx') return FileCode;
    if (file.extension === '.ts' || file.extension === '.tsx') return FileCode;
    if (file.extension === '.md') return BookOpen;
    return FileText;
  };

  const renderFileTree = () => {
    return (
      <div className="space-y-1">
        {fileError && <p role="alert" className="p-2 text-xs text-amber-200">{fileError}</p>}
        {isLoading && fileTree.length === 0 && <p className="p-2 text-xs text-muted-foreground">Loading workspace entries…</p>}
        {fileTree.filter((file) => parentPath(file.path) === normalizePath(rootPath)).map((file, i) => {
          const Icon = getFileIcon(file);
          const isExpanded = expandedFolders.has(file.path);

          return (
            <motion.div
              key={file.path}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.02 }}
            >
              <button
                onClick={() => file.is_directory ? toggleFolder(file.path) : openFile(file.path)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm hover:bg-white/5 ${
                  selectedFile === file.path ? 'bg-blue-500/10 text-blue-400' : 'text-muted-foreground/70'
                }`}
              >
                {file.is_directory && (
                  isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />
                )}
                {!file.is_directory && <span className="w-3" />}
                <Icon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate">{file.name}</span>
              </button>

              {file.is_directory && isExpanded && (
                <div className="ml-4 border-l border-white/5 pl-2 mt-1">
                  {fileTree
                    .filter((child) => parentPath(child.path) === normalizePath(file.path))
                    .map((child) => {
                      const ChildIcon = getFileIcon(child);
                      return (
                        <button
                          key={child.path}
                          onClick={() => child.is_directory ? toggleFolder(child.path) : openFile(child.path)}
                          className={`w-full flex items-center gap-2 px-2 py-1 rounded text-xs hover:bg-white/5 ${
                            selectedFile === child.path ? 'bg-blue-500/10 text-blue-400' : 'text-muted-foreground/60'
                          }`}
                        >
                          {child.is_directory && (
                            expandedFolders.has(child.path) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />
                          )}
                          {!child.is_directory && <span className="w-3" />}
                          <ChildIcon className="h-3 w-3" />
                          <span className="truncate">{child.name}</span>
                        </button>
                      );
                    })}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between p-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6 text-purple-400" />
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-purple-400 via-pink-400 to-orange-400 bg-clip-text text-transparent">
              Workspace File Inspector
            </h1>
            <p className="text-xs text-muted-foreground/60">
              Read-only workspace access. File writes, shell execution, and self-modification are unavailable.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void loadFileTree()} disabled={isLoading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh files
          </Button>
          <Button variant="outline" size="sm" disabled title="Code analysis is not connected to a backend service.">
            <Brain className="mr-2 h-4 w-4" />
            Analysis unavailable
          </Button>
          <Button size="sm" disabled title="Automated code modification is not available.">
            <Zap className="mr-2 h-4 w-4" />
            Auto-improve unavailable
          </Button>
        </div>
      </motion.div>

      <div className="flex flex-1 overflow-hidden">
        {/* File Tree Sidebar */}
        {showFileTree && (
          <div className="w-64 border-r border-white/5 bg-white/[0.02]">
            <div className="p-3 border-b border-white/5 flex items-center justify-between">
              <span className="text-sm font-semibold">Explorer</span>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowFileTree(false)}>
                <X className="h-3 w-3" />
              </Button>
            </div>
            <ScrollArea className="h-[calc(100vh-8rem)]">
              <div className="p-2">
                {renderFileTree()}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          {/* Toolbar */}
          <div className="flex items-center gap-2 p-2 border-b border-white/5 bg-white/[0.02]">
            {!showFileTree && (
              <Button variant="ghost" size="sm" onClick={() => setShowFileTree(true)}>
                <Folder className="h-4 w-4" />
              </Button>
            )}
            {selectedFile && (
              <>
                <span className="text-sm text-muted-foreground/60">{selectedFile}</span>
                <Separator orientation="vertical" className="h-4" />
                <Badge variant="outline">Read only</Badge>
              </>
            )}
          </div>

          {/* Editor Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
            <TabsList className="bg-white/[0.02] border-b border-white/5 rounded-none">
              <TabsTrigger value="editor" className="text-sm">
                <Edit3 className="mr-2 h-4 w-4" />
                Editor
              </TabsTrigger>
              <TabsTrigger value="analysis" className="text-sm">
                <Code2 className="mr-2 h-4 w-4" />
                Analysis
              </TabsTrigger>
              <TabsTrigger value="terminal" className="text-sm">
                <Terminal className="mr-2 h-4 w-4" />
                Terminal
              </TabsTrigger>
              <TabsTrigger value="self-read" className="text-sm">
                <Eye className="mr-2 h-4 w-4" />
                Self-Read
              </TabsTrigger>
            </TabsList>

            {/* Editor Tab */}
            <TabsContent value="editor" className="flex-1 overflow-hidden">
              {selectedFile ? (
                <div className="h-full flex flex-col">
                  <Textarea
                    value={fileContent}
                    readOnly
                    className="flex-1 font-mono text-sm bg-transparent border-none resize-none focus-visible:ring-0"
                    placeholder="File content will appear here..."
                  />
                </div>
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground/40">
                  <div className="text-center">
                    <FileCode className="h-16 w-16 mx-auto mb-4 opacity-50" />
                    <h3 className="text-lg font-semibold mb-2">No File Open</h3>
                    <p className="text-sm">Select a file from the explorer to start editing</p>
                  </div>
                </div>
              )}
            </TabsContent>

            {/* Analysis Tab */}
            <TabsContent value="analysis" className="flex-1 p-4 overflow-auto">
              <div role="status" className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-muted-foreground">
                Code analysis is unavailable because this deployment does not expose a connected analysis endpoint.
              </div>
            </TabsContent>

            {/* Terminal Tab */}
            <TabsContent value="terminal" className="flex-1 flex flex-col">
              <div role="status" className="m-4 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-muted-foreground">
                Terminal execution is unavailable. No shell command is submitted or simulated.
              </div>
            </TabsContent>

            {/* Self-Read Tab */}
            <TabsContent value="self-read" className="flex-1 p-4 overflow-auto">
              <div className="space-y-4">
                <Card className="bg-white/[0.02] border-white/5">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Eye className="h-5 w-5 text-cyan-400" />
                      JARVIS Self-Reading Mode
                    </CardTitle>
                    <CardDescription>
                      This view reads files only; analysis and modification are not wired to a service.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div className="p-3 rounded bg-cyan-500/10 border border-cyan-500/20">
                        <p className="text-sm font-semibold text-cyan-400 mb-2">What JARVIS Can Do:</p>
                        <ul className="space-y-1 text-sm text-muted-foreground/70">
                          <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" /> List workspace files through the authenticated backend</li>
                          <li className="flex items-center gap-2"><CheckCircle className="h-3 w-3 text-emerald-400" /> Read selected files through the confined file API</li>
                          <li className="flex items-center gap-2"><X className="h-3 w-3 text-amber-400" /> File writes and terminal execution are unavailable</li>
                          <li className="flex items-center gap-2"><X className="h-3 w-3 text-amber-400" /> Indexing and code analysis are unavailable</li>
                        </ul>
                      </div>

                      <Button className="w-full" disabled>
                        <Brain className="mr-2 h-4 w-4" />
                        Self-analysis unavailable
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
