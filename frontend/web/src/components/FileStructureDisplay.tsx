'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Folder, File, ChevronRight, ChevronDown, Sparkles, CheckCircle, XCircle } from 'lucide-react';
import env from '@/config/env';

interface FileNode {
  name: string;
  type: 'directory' | 'file';
  path: string;
  children?: FileNode[];
  description?: string;
  status?: 'active' | 'available' | 'experimental';
}

interface FileStructureDisplayProps {
  className?: string;
}

export default function FileStructureDisplay({ className }: FileStructureDisplayProps) {
  const [fileStructure, setFileStructure] = useState<FileNode[]>([]);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<FileNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchFileStructure();
  }, []);

  const fetchFileStructure = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${env.API_URL}/api/v1/system/file-structure`, {
        credentials: 'include',
      });
      if (!response.ok) {
        throw new Error(`File structure request failed (HTTP ${response.status})`);
      }
      const data = await response.json();
      if (!data.success || !Array.isArray(data.structure)) {
        throw new Error(
          typeof data.detail === 'string' ? data.detail : 'The backend returned an invalid file structure.',
        );
      }
      setFileStructure(data.structure);
      setError(null);
    } catch (error) {
      setFileStructure([]);
      setError(error instanceof Error ? error.message : 'Unable to load the file structure.');
    } finally {
      setLoading(false);
    }
  };

  const toggleNode = (path: string) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
    }
    setExpandedNodes(newExpanded);
  };

  const renderNode = (node: FileNode, level: number = 0) => {
    const isExpanded = expandedNodes.has(node.path);
    const Icon = node.type === 'directory' ? Folder : File;
    const StatusIcon = node.status === 'active' ? CheckCircle : node.status === 'available' ? CheckCircle : XCircle;

    return (
      <div key={node.path} style={{ marginLeft: `${level * 20}px` }}>
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-gray-800 cursor-pointer transition-colors"
          onClick={() => {
            if (node.type === 'directory') {
              toggleNode(node.path);
            } else {
              setSelectedNode(node);
            }
          }}
        >
          {node.type === 'directory' && (
            <span className="text-gray-400">
              {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </span>
          )}
          <Icon className={`w-5 h-5 ${node.type === 'directory' ? 'text-blue-400' : 'text-gray-400'}`} />
          <span className="flex-1 text-sm">{node.name}</span>
          {node.status && (
            <StatusIcon className={`w-4 h-4 ${node.status === 'active' ? 'text-green-400' : node.status === 'available' ? 'text-yellow-400' : 'text-red-400'}`} />
          )}
        </motion.div>
        
        {node.type === 'directory' && isExpanded && node.children && (
          <div className="mt-1">
            {node.children.map(child => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  const countNodes = (nodes: FileNode[], type: FileNode['type']): number =>
    nodes.reduce((count, node) => count + (node.type === type ? 1 : 0) + countNodes(node.children ?? [], type), 0);
  const countActiveChildren = (nodes: FileNode[]): number =>
    nodes.reduce((count, node) => count + (node.status === 'active' ? 1 : 0) + countActiveChildren(node.children ?? []), 0);
  const activeCount = fileStructure.reduce(
    (count, node) => count + (node.status === 'active' ? 1 : 0) + countActiveChildren(node.children ?? []),
    0,
  );
  const directoryCount = Math.max(0, countNodes(fileStructure, 'directory') - fileStructure.length);
  const fileCount = countNodes(fileStructure, 'file');

  return (
    <div className={`min-h-screen bg-gray-900 text-white p-6 ${className}`}>
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 flex items-center">
            <Sparkles className="mr-3 w-10 h-10 text-blue-400" />
            JARVIS File Structure
          </h1>
          <p className="text-gray-400 text-lg">
            System capabilities organized by actual file/code structure
          </p>
        </div>

        {/* Stats */}
        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-gradient-to-br from-blue-600 to-blue-800 p-6 rounded-xl">
              <div className="text-3xl font-bold">{fileStructure.length}</div>
              <div className="text-blue-200">Main Directories</div>
            </div>
            <div className="bg-gradient-to-br from-green-600 to-green-800 p-6 rounded-xl">
              <div className="text-3xl font-bold">{activeCount}</div>
              <div className="text-green-200">Active Systems</div>
            </div>
            <div className="bg-gradient-to-br from-purple-600 to-purple-800 p-6 rounded-xl">
              <div className="text-3xl font-bold">{directoryCount}</div>
              <div className="text-purple-200">Sub-directories</div>
            </div>
            <div className="bg-gradient-to-br from-yellow-600 to-yellow-800 p-6 rounded-xl">
              <div className="text-3xl font-bold">{fileCount}</div>
              <div className="text-yellow-200">Files</div>
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-400 mx-auto mb-4"></div>
            <p className="text-gray-400">Loading file structure...</p>
          </div>
        )}

        {/* File Structure Tree */}
        {!loading && error && (
          <div role="alert" className="rounded-xl border border-red-500/30 bg-red-950/30 p-6 text-red-200">
            <p>{error}</p>
            <button
              onClick={() => void fetchFileStructure()}
              className="mt-4 rounded-lg border border-red-300/30 px-4 py-2 hover:bg-red-900/40"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && (
          <div className="bg-gray-800 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Core Directory Structure</h2>
              <button
                onClick={() => {
                  const allPaths = new Set<string>();
                  const collectPaths = (nodes: FileNode[]) => {
                    nodes.forEach(node => {
                      if (node.type === 'directory') {
                        allPaths.add(node.path);
                        if (node.children) {
                          collectPaths(node.children);
                        }
                      }
                    });
                  };
                  collectPaths(fileStructure);
                  setExpandedNodes(allPaths);
                }}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                Expand All
              </button>
            </div>
            <div className="space-y-1">
              {fileStructure.map(node => renderNode(node))}
            </div>
          </div>
        )}

        {/* Detail Modal */}
        <AnimatePresence>
          {selectedNode && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
              onClick={() => setSelectedNode(null)}
            >
              <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                className="bg-gray-800 p-8 rounded-xl max-w-2xl w-full"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center mr-4">
                      <File className="w-8 h-8 text-white" />
                    </div>
                    <div>
                      <h2 className="text-2xl font-bold">{selectedNode.name}</h2>
                      <p className="text-gray-400">{selectedNode.path}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedNode(null)}
                    className="text-gray-400 hover:text-white"
                  >
                    <XCircle className="w-6 h-6" />
                  </button>
                </div>
                <p className="text-gray-300 mb-6">{selectedNode.description || 'No description available'}</p>
                {selectedNode.status && (
                  <div className="flex items-center justify-between">
                    <span className={`px-3 py-1 rounded ${
                      selectedNode.status === 'active' ? 'bg-green-600' :
                      selectedNode.status === 'available' ? 'bg-yellow-600' :
                      'bg-red-600'
                    }`}>
                      Status: {selectedNode.status}
                    </span>
                    <button
                      onClick={() => setSelectedNode(null)}
                      className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg"
                    >
                      Close
                    </button>
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
