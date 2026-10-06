'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Folder, FolderOpen, File, Server, Database, Brain, Cpu, Shield, 
  Zap, Globe, Code, Settings, Users, Activity, Layers, Network,
  Search, Bell, Home, MessageSquare, Bot, Puzzle, Wrench,
  ChevronRight, ChevronDown, Sparkles, CheckCircle, XCircle
} from 'lucide-react';
import env from '@/config/env';

interface FileNode {
  name: string;
  type: 'directory' | 'file';
  path: string;
  children?: FileNode[];
  description?: string;
  status?: 'active' | 'available' | 'experimental';
  icon?: any;
}

interface FileStructureDisplayProps {
  className?: string;
}

const ICON_MAP: Record<string, any> = {
  'api': Server,
  'auth': Shield,
  'automation': Zap,
  'cognitive': Brain,
  'database': Database,
  'integrations': Puzzle,
  'memory': Brain,
  'orchestrator': Activity,
  'performance': Activity,
  'realtime': Zap,
  'security': Shield,
  'workflow': Layers,
  'agents': Bot,
  'browser': Globe,
  'voice': MessageSquare,
  'gateway': Server,
  'intelligence': Brain,
  'runtime': Cpu,
  'services': Settings,
  'entities': Database,
  'eventbus': Network,
  'client_gateway': Users,
  'client_integration': Users,
};

const DESCRIPTIONS: Record<string, string> = {
  'api': 'REST API endpoints and HTTP services',
  'auth': 'Authentication and authorization systems',
  'automation': 'Automation engines and task execution',
  'cognitive': 'Cognitive processing and reasoning',
  'database': 'Database models and persistence',
  'integrations': 'External service integrations',
  'memory': 'Memory systems and knowledge storage',
  'orchestrator': 'System orchestration and coordination',
  'performance': 'Performance monitoring and optimization',
  'realtime': 'Real-time communication and streaming',
  'security': 'Security and encryption systems',
  'workflow': 'Workflow automation and execution',
  'agents': 'AI agent systems and collaboration',
  'browser': 'Web browsing and page analysis',
  'voice': 'Voice processing and speech recognition',
  'gateway': 'API gateway and routing',
  'intelligence': 'AI and machine learning systems',
  'runtime': 'Runtime execution environments',
  'services': 'Core services and utilities',
  'entities': 'Data entities and models',
  'eventbus': 'Event bus and messaging',
  'client_gateway': 'Client gateway integration',
  'client_integration': 'Client integration systems',
};

export default function FileStructureDisplay({ className }: FileStructureDisplayProps) {
  const [fileStructure, setFileStructure] = useState<FileNode[]>([]);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<FileNode | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchFileStructure();
  }, []);

  const fetchFileStructure = async () => {
    try {
      const response = await fetch(`${env.API_URL}/api/v1/system/file-structure`);
      const data = await response.json();
      if (data.success && data.structure) {
        setFileStructure(data.structure);
      } else {
        // Fallback to static structure if API not available
        setFileStructure(getStaticFileStructure());
      }
    } catch (error) {
      // Fallback to static structure
      setFileStructure(getStaticFileStructure());
    } finally {
      setLoading(false);
    }
  };

  const getStaticFileStructure = (): FileNode[] => {
    return [
      {
        name: 'api',
        type: 'directory',
        path: 'core/api',
        description: DESCRIPTIONS['api'],
        icon: ICON_MAP['api'],
        status: 'active',
        children: [
          { name: 'main.py', type: 'file', path: 'core/api/main.py', description: 'Main FastAPI application' },
          { name: 'routers', type: 'directory', path: 'core/api/routers', description: 'API route handlers' },
          { name: 'middleware', type: 'directory', path: 'core/api/middleware', description: 'Middleware components' },
        ]
      },
      {
        name: 'integrations',
        type: 'directory',
        path: 'core/integrations',
        description: DESCRIPTIONS['integrations'],
        icon: ICON_MAP['integrations'],
        status: 'active',
        children: [
          { name: 'slack_integration.py', type: 'file', path: 'core/integrations/slack_integration.py', description: 'Slack integration' },
          { name: 'discord_integration.py', type: 'file', path: 'core/integrations/discord_integration.py', description: 'Discord integration' },
          { name: 'integration_manager.py', type: 'file', path: 'core/integrations/integration_manager.py', description: 'Integration manager' },
        ]
      },
      {
        name: 'workflow',
        type: 'directory',
        path: 'core/workflow',
        description: DESCRIPTIONS['workflow'],
        icon: ICON_MAP['workflow'],
        status: 'active',
        children: [
          { name: 'workflow_builder.py', type: 'file', path: 'core/workflow/workflow_builder.py', description: 'Workflow builder' },
        ]
      },
      {
        name: 'security',
        type: 'directory',
        path: 'core/security',
        description: DESCRIPTIONS['security'],
        icon: ICON_MAP['security'],
        status: 'active',
        children: [
          { name: 'api_key_manager.py', type: 'file', path: 'core/security/api_key_manager.py', description: 'API key management' },
          { name: 'audit_logger.py', type: 'file', path: 'core/security/audit_logger.py', description: 'Audit logging system' },
          { name: 'auth_service.py', type: 'file', path: 'core/security/auth_service.py', description: 'Authentication service' },
        ]
      },
      {
        name: 'automation',
        type: 'directory',
        path: 'core/automation',
        description: DESCRIPTIONS['automation'],
        icon: ICON_MAP['automation'],
        status: 'active',
        children: [
          { name: 'automation_engine.py', type: 'file', path: 'core/automation/automation_engine.py', description: 'Automation engine' },
        ]
      },
      {
        name: 'cognitive',
        type: 'directory',
        path: 'core/cognitive',
        description: DESCRIPTIONS['cognitive'],
        icon: ICON_MAP['cognitive'],
        status: 'active',
      },
      {
        name: 'memory',
        type: 'directory',
        path: 'core/memory',
        description: DESCRIPTIONS['memory'],
        icon: ICON_MAP['memory'],
        status: 'active',
      },
      {
        name: 'orchestrator',
        type: 'directory',
        path: 'core/orchestrator',
        description: DESCRIPTIONS['orchestrator'],
        icon: ICON_MAP['orchestrator'],
        status: 'active',
      },
      {
        name: 'realtime',
        type: 'directory',
        path: 'core/realtime',
        description: DESCRIPTIONS['realtime'],
        icon: ICON_MAP['realtime'],
        status: 'active',
      },
      {
        name: 'agents',
        type: 'directory',
        path: 'core/agents',
        description: DESCRIPTIONS['agents'],
        icon: ICON_MAP['agents'],
        status: 'active',
      },
      {
        name: 'intelligence',
        type: 'directory',
        path: 'core/intelligence',
        description: DESCRIPTIONS['intelligence'],
        icon: ICON_MAP['intelligence'],
        status: 'active',
      },
      {
        name: 'runtime',
        type: 'directory',
        path: 'core/runtime',
        description: DESCRIPTIONS['runtime'],
        icon: ICON_MAP['runtime'],
        status: 'active',
      },
      {
        name: 'services',
        type: 'directory',
        path: 'core/services',
        description: DESCRIPTIONS['services'],
        icon: ICON_MAP['services'],
        status: 'active',
      },
      {
        name: 'gateway',
        type: 'directory',
        path: 'core/gateway',
        description: DESCRIPTIONS['gateway'],
        icon: ICON_MAP['gateway'],
        status: 'active',
      },
      {
        name: 'eventbus',
        type: 'directory',
        path: 'core/eventbus',
        description: DESCRIPTIONS['eventbus'],
        icon: ICON_MAP['eventbus'],
        status: 'active',
      },
      {
        name: 'client_gateway',
        type: 'directory',
        path: 'core/client_gateway',
        description: DESCRIPTIONS['client_gateway'],
        icon: ICON_MAP['client_gateway'],
        status: 'active',
      },
      {
        name: 'auth',
        type: 'directory',
        path: 'core/auth',
        description: DESCRIPTIONS['auth'],
        icon: ICON_MAP['auth'],
        status: 'active',
      },
    ];
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
    const Icon = node.icon || (node.type === 'directory' ? Folder : File);
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

  const activeCount = fileStructure.filter(n => n.status === 'active').length;
  const directoryCount = fileStructure.filter(n => n.type === 'directory').length;
  const fileCount = fileStructure.reduce((acc, node) => {
    if (node.children) {
      return acc + node.children.filter(c => c.type === 'file').length;
    }
    return acc;
  }, 0);

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
            <div className="text-yellow-200">Key Files</div>
          </div>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-400 mx-auto mb-4"></div>
            <p className="text-gray-400">Loading file structure...</p>
          </div>
        )}

        {/* File Structure Tree */}
        {!loading && (
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
