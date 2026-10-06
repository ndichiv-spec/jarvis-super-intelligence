import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Code, Download, Play, FileText } from 'lucide-react';

export function CascadeCodeViewer() {
  const [currentCode, setCurrentCode] = useState(`// JARVIS AI System - Core Module
class JarvisCore {
  constructor() {
    this.neuralNetwork = new NeuralNetwork();
    this.dataProcessor = new DataProcessor();
    this.aiEngine = new AIEngine();
  }
  
  async initialize() {
    await this.neuralNetwork.load();
    await this.dataProcessor.configure();
    await this.aiEngine.start();
    
    console.log('JARVIS Core Initialized');
  }
  
  async processInput(input) {
    const processed = await this.dataProcessor.analyze(input);
    const prediction = await this.neuralNetwork.predict(processed);
    return await this.aiEngine.execute(prediction);
  }
}

// Initialize JARVIS
const jarvis = new JarvisCore();
jarvis.initialize();`);

  const [language, setLanguage] = useState('javascript');

  return (
    <div className="h-full flex flex-col bg-gray-800 rounded-xl">
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Code className="w-6 h-6 text-green-400" />
            <h2 className="text-xl font-semibold text-white">Cascade CodeViewer</h2>
          </div>
          <div className="flex space-x-2">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-gray-700 text-white px-3 py-1 rounded text-sm"
            >
              <option value="javascript">JavaScript</option>
              <option value="python">Python</option>
              <option value="typescript">TypeScript</option>
              <option value="json">JSON</option>
            </select>
          </div>
        </div>
      </div>
      
      <div className="flex-1 overflow-hidden">
        <div className="h-full flex flex-col">
          <div className="p-4 border-b border-gray-700">
            <div className="flex items-center space-x-2 text-sm text-gray-400">
              <FileText className="w-4 h-4" />
              <span>jarvis-core.js</span>
              <span>•</span>
              <span>{currentCode.split('\n').length} lines</span>
            </div>
          </div>
          
          <div className="flex-1 p-4 overflow-auto">
            <pre className="text-sm text-gray-300 font-mono">
              <code>{currentCode}</code>
            </pre>
          </div>
          
          <div className="p-4 border-t border-gray-700">
            <div className="flex space-x-2">
              <button className="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded text-sm flex items-center space-x-1 transition-colors">
                <Play className="w-3 h-3" />
                <span>Run</span>
              </button>
              <button className="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded text-sm flex items-center space-x-1 transition-colors">
                <Download className="w-3 h-3" />
                <span>Export</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
