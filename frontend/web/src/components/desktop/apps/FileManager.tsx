'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { jarvisAPI } from '@/lib/api';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FolderOpen,
  File,
  ChevronRight,
  ChevronDown,
  Upload,
  Download,
  Trash2,
  RefreshCw,
  Search,
  ArrowUp,
  FileText,
  Image as ImageIcon,
  Code,
  MoreVertical,
} from 'lucide-react';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  modified?: string;
  children?: FileNode[];
  expanded?: boolean;
}

export default function FileManager() {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentPath, setCurrentPath] = useState('.');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  const loadFiles = useCallback(async (path: string = '.') => {
    setIsLoading(true);
    try {
      const response = await jarvisAPI.listFiles(path);
      // Transform API response to FileNode format
      const items: FileNode[] = (response.files || response.entries || []).map((item: any) => ({
        name: item.name || item.filename || 'unknown',
        path: item.path || `${path}/${item.name}`,
        type: item.type === 'directory' || item.is_dir ? 'directory' : 'file',
        size: item.size,
        modified: item.modified || item.updated_at,
        expanded: false,
      }));

      // Sort: directories first, then files
      items.sort((a, b) => {
        if (a.type === 'directory' && b.type === 'file') return -1;
        if (a.type === 'file' && b.type === 'directory') return 1;
        return a.name.localeCompare(b.name);
      });

      setFiles(items);
      setCurrentPath(path);
    } catch (error) {
      // Mock data if API fails
      const mockFiles: FileNode[] = [
        { name: 'Documents', path: './Documents', type: 'directory', children: [], expanded: false },
        { name: 'Projects', path: './Projects', type: 'directory', children: [], expanded: false },
        { name: 'Images', path: './Images', type: 'directory', children: [], expanded: false },
        { name: 'config.json', path: './config.json', type: 'file', size: 2048, modified: '2024-01-15' },
        { name: 'README.md', path: './README.md', type: 'file', size: 4096, modified: '2024-01-14' },
        { name: 'package.json', path: './package.json', type: 'file', size: 1024, modified: '2024-01-13' },
        { name: '.env.example', path: './.env.example', type: 'file', size: 512, modified: '2024-01-12' },
      ];
      setFiles(mockFiles);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const toggleDirectory = async (file: FileNode) => {
    if (file.type !== 'directory') return;

    if (file.expanded) {
      setFiles((prev) =>
        prev.map((f) => (f.path === file.path ? { ...f, expanded: false } : f))
      );
    } else {
      try {
        const response = await jarvisAPI.listFiles(file.path);
        const children: FileNode[] = (response.files || response.entries || []).map((item: any) => ({
          name: item.name || item.filename || 'unknown',
          path: item.path || `${file.path}/${item.name}`,
          type: item.type === 'directory' || item.is_dir ? 'directory' : 'file',
          size: item.size,
          modified: item.modified || item.updated_at,
          expanded: false,
        }));

        setFiles((prev) =>
          prev.map((f) => (f.path === file.path ? { ...f, expanded: true, children } : f))
        );
      } catch {
        setFiles((prev) =>
          prev.map((f) =>
            f.path === file.path
              ? {
                  ...f,
                  expanded: true,
                  children: [
                    { name: 'subfolder', path: `${file.path}/subfolder`, type: 'directory' },
                    { name: 'file.txt', path: `${file.path}/file.txt`, type: 'file', size: 1024 },
                  ],
                }
              : f
          )
        );
      }
    }
  };

  const getFileIcon = (file: FileNode) => {
    if (file.type === 'directory') return FolderOpen;

    const ext = file.name.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
      case 'svg':
        return ImageIcon;
      case 'ts':
      case 'tsx':
      case 'js':
      case 'jsx':
      case 'py':
      case 'json':
      case 'yaml':
      case 'yml':
        return Code;
      default:
        return FileText;
    }
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const filteredFiles = searchQuery
    ? files.filter((f) => f.name.toLowerCase().includes(searchQuery.toLowerCase()))
    : files;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/50 bg-card/30">
        <button
          onClick={() => loadFiles()}
          disabled={isLoading}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>

        <div className="h-6 w-px bg-border/50" />

        {/* Path breadcrumbs */}
        <div className="flex items-center gap-1 flex-1 min-w-0">
          <button
            onClick={() => loadFiles('.')}
            className="flex items-center gap-1 text-xs text-foreground/60 hover:text-foreground px-2 py-1 rounded-lg hover:bg-white/5 transition-colors"
          >
            <FolderOpen className="w-3.5 h-3.5" />
            Home
          </button>
          {currentPath !== '.' && (
            <>
              <ChevronRight className="w-3 h-3 text-foreground/30" />
              <span className="text-xs text-foreground/40 truncate">{currentPath}</span>
            </>
          )}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-foreground/30" />
          <input
            type="text"
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 pl-8 pr-3 w-40 bg-white/5 border border-border/50 rounded-lg text-xs text-foreground placeholder:text-foreground/30 focus:outline-none focus:border-primary/50 transition-all"
          />
        </div>

        <div className="h-6 w-px bg-border/50" />

        {/* View mode toggle */}
        <button
          onClick={() => setViewMode(viewMode === 'grid' ? 'list' : 'grid')}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors text-xs"
        >
          {viewMode === 'grid' ? 'L' : 'G'}
        </button>

        <button
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-white/5 text-foreground/50 hover:text-foreground transition-colors"
          title="Upload"
        >
          <Upload className="w-4 h-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 custom-scrollbar">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <RefreshCw className="w-6 h-6 text-primary/50 animate-spin" />
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-4 gap-2">
            {filteredFiles.map((file) => {
              const Icon = getFileIcon(file);
              return (
                <motion.button
                  key={file.path}
                  className={`flex flex-col items-center gap-2 p-4 rounded-xl border transition-all ${
                    selectedFile === file.path
                      ? 'bg-primary/10 border-primary/30'
                      : 'bg-white/[0.02] border-border/30 hover:bg-white/5 hover:border-border/50'
                  }`}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setSelectedFile(file.path)}
                  onDoubleClick={() => file.type === 'directory' && toggleDirectory(file)}
                >
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/10 to-accent/10 border border-primary/10 flex items-center justify-center">
                    <Icon
                      className={`w-6 h-6 ${
                        file.type === 'directory' ? 'text-amber-400' : 'text-foreground/60'
                      }`}
                    />
                  </div>
                  <span className="text-xs text-foreground/70 text-center truncate w-full">
                    {file.name}
                  </span>
                  {file.type === 'file' && (
                    <span className="text-[10px] text-foreground/40">{formatSize(file.size)}</span>
                  )}
                </motion.button>
              );
            })}
          </div>
        ) : (
          <div className="space-y-0.5">
            {/* List header */}
            <div className="flex items-center gap-2 px-3 py-1.5 text-[10px] text-foreground/40 uppercase tracking-wider">
              <span className="flex-1">Name</span>
              <span className="w-20 text-right">Size</span>
              <span className="w-28 text-right">Modified</span>
              <span className="w-8" />
            </div>

            {filteredFiles.map((file) => {
              const Icon = getFileIcon(file);
              return (
                <motion.div
                  key={file.path}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all ${
                    selectedFile === file.path
                      ? 'bg-primary/10'
                      : 'hover:bg-white/5'
                  }`}
                  whileHover={{ x: 2 }}
                  onClick={() => setSelectedFile(file.path)}
                  onDoubleClick={() => file.type === 'directory' && toggleDirectory(file)}
                >
                  <Icon
                    className={`w-4 h-4 shrink-0 ${
                      file.type === 'directory' ? 'text-amber-400' : 'text-foreground/50'
                    }`}
                  />
                  <span className="text-sm text-foreground/80 flex-1 truncate">{file.name}</span>
                  <span className="w-20 text-right text-xs text-foreground/40 font-mono">
                    {file.type === 'directory' ? '-' : formatSize(file.size)}
                  </span>
                  <span className="w-28 text-right text-xs text-foreground/40">
                    {file.modified || '-'}
                  </span>
                  <button className="w-8 flex items-center justify-center text-foreground/30 hover:text-foreground/60">
                    <MoreVertical className="w-3.5 h-3.5" />
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

        {filteredFiles.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-foreground/40">
            <FolderOpen className="w-12 h-12 mb-3" />
            <span className="text-sm">No files found</span>
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-t border-border/50 bg-card/30 text-[10px] text-foreground/40">
        <span>{filteredFiles.length} items</span>
        <span>{formatSize(filteredFiles.reduce((acc, f) => acc + (f.size || 0), 0))}</span>
      </div>
    </div>
  );
}
