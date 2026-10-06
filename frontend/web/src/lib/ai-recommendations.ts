import { useMemo } from 'react';
import { detectAIMood, ThemeMood } from '@/lib/neural-theme-engine';

interface FeatureRecommendation {
  name: string;
  href: string;
  reason: string;
  confidence: number;
  icon: string;
}

export function useAIRecommendations(userQuery?: string, recentFeatures?: string[]) {
  const recommendations = useMemo(() => {
    if (!userQuery) return [];

    // Detect mood from query
    const mood = detectAIMood(userQuery);
    
    // Base recommendations on mood and context
    const moodBasedRecs: Record<ThemeMood, FeatureRecommendation[]> = {
      analytical: [
        { name: 'Advanced Reasoning', href: '/dashboard/advanced', reason: 'Perfect for logical analysis tasks', confidence: 0.95, icon: '🧠' },
        { name: 'Knowledge Studio', href: '/dashboard/knowledge', reason: 'Access structured data & facts', confidence: 0.9, icon: '📊' },
        { name: 'Code Execution', href: '/dashboard', reason: 'Run code snippets & calculations', confidence: 0.85, icon: '💻' },
      ],
      creative: [
        { name: 'Image Generation', href: '/image-generation', reason: 'Create visual content with AI', confidence: 0.95, icon: '🎨' },
        { name: 'Creative AI', href: '/dashboard', reason: 'Generate stories, ideas & content', confidence: 0.9, icon: '✨' },
        { name: 'OMEGA Engine', href: '/omega', reason: 'Multi-model creative orchestration', confidence: 0.85, icon: '🚀' },
      ],
      empathetic: [
        { name: 'Neural Chat', href: '/dashboard', reason: 'Engage in meaningful conversation', confidence: 0.95, icon: '💬' },
        { name: 'Voice Interface', href: '/voice', reason: 'Natural voice interaction', confidence: 0.85, icon: '🎙️' },
        { name: 'SUPREME UI', href: '/supreme', reason: 'Enhanced conversational experience', confidence: 0.8, icon: '⭐' },
      ],
      focused: [
        { name: 'Workflows', href: '/workflows', reason: 'Automate repetitive tasks', confidence: 0.95, icon: '⚡' },
        { name: 'Agent Orchestration', href: '/dashboard/agents', reason: 'Delegate complex multi-step tasks', confidence: 0.9, icon: '🤖' },
        { name: 'Command Center', href: '/dashboard/monitoring', reason: 'Monitor all systems at once', confidence: 0.85, icon: '📊' },
      ],
      playful: [
        { name: 'Virtual Desktop', href: '/desktop', reason: 'Explore the full desktop environment', confidence: 0.9, icon: '🖥️' },
        { name: 'Plugin Marketplace', href: '/plugins', reason: 'Discover fun extensions', confidence: 0.85, icon: '🔌' },
        { name: 'Video Analysis', href: '/video-analysis', reason: 'Analyze and process videos', confidence: 0.8, icon: '🎬' },
      ],
      serious: [
        { name: 'System Control', href: '/dashboard/system', reason: 'Critical system management', confidence: 0.95, icon: '⚙️' },
        { name: 'Admin Console', href: '/dashboard/admin', reason: 'Security & access control', confidence: 0.9, icon: '🛡️' },
        { name: 'Self-Healing', href: '/dashboard/monitoring', reason: 'Automatic error recovery', confidence: 0.85, icon: '🔄' },
      ],
      neutral: [
        { name: 'OMEGA Engine', href: '/omega', reason: 'Master AI orchestrator', confidence: 0.85, icon: '🚀' },
        { name: 'Knowledge Studio', href: '/dashboard/knowledge', reason: 'Centralized knowledge base', confidence: 0.8, icon: '📚' },
        { name: 'Workflows', href: '/workflows', reason: 'Visual automation builder', confidence: 0.75, icon: '⚡' },
      ],
    };

    let recs = moodBasedRecs[mood] || moodBasedRecs.neutral;

    // Boost confidence for recently used features
    if (recentFeatures && recentFeatures.length > 0) {
      recs = recs.map(rec => ({
        ...rec,
        confidence: recentFeatures.includes(rec.name) 
          ? Math.min(rec.confidence + 0.1, 1.0) 
          : rec.confidence,
      }));
      
      // Sort by confidence
      recs.sort((a, b) => b.confidence - a.confidence);
    }

    return recs.slice(0, 3); // Return top 3 recommendations
  }, [userQuery, recentFeatures]);

  return recommendations;
}

// Keyboard shortcuts configuration
export const KEYBOARD_SHORTCUTS = {
  'Cmd+K': { action: 'Open command palette', description: 'Quick navigation' },
  'Cmd+B': { action: 'Toggle sidebar', description: 'Show/hide navigation' },
  'Cmd+T': { action: 'Open theme selector', description: 'Change neural theme' },
  'Cmd+H': { action: 'View health status', description: 'System monitoring' },
  'Escape': { action: 'Close dialogs', description: 'Exit modals' },
  '/': { action: 'Focus search', description: 'Search features' },
  '?': { action: 'Show shortcuts', description: 'Keyboard help' },
};

// Hook for keyboard shortcuts
export function useKeyboardShortcuts(actions: Record<string, () => void>) {
  if (typeof window === 'undefined') return;

  const handleKeyDown = (e: KeyboardEvent) => {
    // Command palette
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      actions.commandPalette?.();
    }
    
    // Toggle sidebar
    if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
      e.preventDefault();
      actions.toggleSidebar?.();
    }
    
    // Theme selector
    if ((e.metaKey || e.ctrlKey) && e.key === 't') {
      e.preventDefault();
      actions.openThemeSelector?.();
    }
    
    // Health status
    if ((e.metaKey || e.ctrlKey) && e.key === 'h') {
      e.preventDefault();
      actions.viewHealth?.();
    }
    
    // Focus search
    if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
      e.preventDefault();
      actions.focusSearch?.();
    }
    
    // Show shortcuts help
    if (e.key === '?' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
      e.preventDefault();
      actions.showShortcuts?.();
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }
}
