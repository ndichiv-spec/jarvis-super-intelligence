import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

const { chatState, platformState, systemState, routerState } = vi.hoisted(() => ({
  chatState: {
    messages: [],
    sessions: [
      {
        session_id: 'session-1',
        preview: 'Review the incident report',
        started: '2026-09-30T12:00:00.000Z',
      },
    ],
    currentSessionId: 'session-1',
    loadSession: vi.fn(),
    deleteSession: vi.fn(),
    newSession: vi.fn(),
  },
  platformState: {
    backend: { connected: false, status: 'idle' },
    providerSummary: { total: 0, connected: 0, disconnected: 0 },
    refreshBackend: vi.fn(),
    refreshProviders: vi.fn(),
  },
  systemState: {
    status: null,
    capabilities: null,
    loadStatus: vi.fn(),
    loadCapabilities: vi.fn(),
  },
  routerState: { push: vi.fn() },
}));

vi.mock('@/features/chat/store', () => ({
  useChatStore: (selector: (state: typeof chatState) => unknown) => selector(chatState),
}));

vi.mock('@/stores/platform-store', () => ({
  usePlatformStore: (selector: (state: typeof platformState) => unknown) => selector(platformState),
}));

vi.mock('@/features/system/store', () => ({
  useSystemStore: (selector: (state: typeof systemState) => unknown) => selector(systemState),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => routerState,
}));

vi.mock('./chat-window', () => ({
  ChatWindow: ({ showSidebar }: { showSidebar: boolean }) => (
    <div role="region" aria-label="Conversation pane" data-sidebar={String(showSidebar)} />
  ),
}));

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
}));

import { ChatWorkspace } from './chat-workspace';
import { useJarvisRuntime } from '@/features/runtime/store';

describe('ChatWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    platformState.backend = { connected: false, status: 'idle' };
    platformState.providerSummary = { total: 0, connected: 0, disconnected: 0 };
    platformState.refreshBackend = vi.fn();
    platformState.refreshProviders = vi.fn();
    systemState.status = null;
    systemState.capabilities = null;
    systemState.loadStatus = vi.fn();
    systemState.loadCapabilities = vi.fn();
    useJarvisRuntime.setState({
      currentEnvironment: 'conversation',
      previousEnvironment: null,
      environmentHistory: [],
      currentSessionId: null,
      currentTask: null,
      selectedObject: null,
      permissions: {},
      voiceState: 'idle',
      activities: [],
      capabilities: [],
      integrations: [],
      capabilityRegistryReported: false,
      capabilityRegistryUpdatedAt: null,
      rendererNegotiation: null,
      rendererNegotiationError: null,
      currentPresentation: null,
      presentationEvents: [],
    });
  });

  it('opens the existing chat with one searchable, persisted conversation rail', () => {
    render(<ChatWorkspace />);

    expect(screen.getByRole('region', { name: 'Conversation pane' })).toHaveAttribute('data-sidebar', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'Open conversation navigation' }));
    expect(screen.getByRole('complementary', { name: 'Conversation navigation' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Agents & tasks/ })).toHaveAttribute('href', '/dashboard/agents');
    expect(screen.getByRole('searchbox', { name: 'Search conversations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Review the incident report,/ })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Backend status: Checking' })).toBeInTheDocument();
    expect(screen.getAllByText('Not reported')).toHaveLength(2);
    expect(screen.queryByText('System overview')).not.toBeInTheDocument();
  });

  it('filters the real session list and selects a matching conversation', () => {
    render(<ChatWorkspace />);

    fireEvent.click(screen.getByRole('button', { name: 'Open conversation navigation' }));
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search conversations' }), {
      target: { value: 'incident' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Review the incident report,/ }));

    expect(chatState.loadSession).toHaveBeenCalledWith('session-1');
  });

  it('shows only backend-reported capability readiness and supports the mobile drawer', () => {
    useJarvisRuntime.setState({
      capabilities: [
        {
          id: 'web.search',
          category: 'web',
          tool: 'search_web',
          permissions: ['network.search'],
          provider: 'search-provider',
          providerService: 'web',
          model: null,
          availability: 'available',
          health: 'ok',
          aiBacked: false,
        },
        {
          id: 'device.control',
          category: 'device',
          tool: 'control_device',
          permissions: [],
          provider: null,
          providerService: '',
          model: null,
          availability: 'unavailable',
          health: 'offline',
          aiBacked: false,
        },
      ],
      capabilityRegistryReported: true,
    });
    const { container } = render(<ChatWorkspace />);

    expect(screen.getByText('1 of 2 ready')).toBeInTheDocument();
    const openButton = screen.getByRole('button', { name: 'Open conversation navigation' });
    expect(openButton).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(openButton);
    expect(openButton).toHaveAttribute('aria-expanded', 'true');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByRole('button', { name: 'Open conversation navigation' })).toHaveAttribute('aria-expanded', 'false');
    expect(container.querySelector('#conversation-navigation')).toBeInTheDocument();
  });

  it('shows capability details from the shared runtime rather than exposing raw backend payloads', () => {
    useJarvisRuntime.setState({
      capabilities: [{
        id: 'web.search',
        category: 'web',
        tool: 'search_web',
        permissions: ['network.search'],
        provider: 'search-provider',
        providerService: 'web',
        model: null,
        availability: 'available',
        health: 'ok',
        aiBacked: false,
      }],
      integrations: [{
        id: 'search-provider',
        name: 'Search provider',
        connected: true,
        configured: true,
        status: 'ready',
        capabilities: ['web_search'],
      }],
      capabilityRegistryReported: true,
      rendererNegotiation: {
        clientId: 'jarvis-web',
        renderers: [{
          type: 'map.renderer',
          version: '1.0',
          supportedClients: ['web'],
          supportedPrimitives: ['map', 'marker'],
          capabilities: ['geospatial'],
          constraints: {},
        }],
        fallbacks: [],
      },
    });
    render(<ChatWorkspace />);

    fireEvent.click(screen.getByRole('button', { name: 'Show available capabilities' }));

    expect(screen.getByRole('region', { name: 'Backend-reported capability graph' })).toBeInTheDocument();
    expect(screen.getByText('web.search')).toBeInTheDocument();
    expect(screen.getByText(/Permissions: network\.search/)).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('map.renderer')).toBeInTheDocument();
    expect(screen.queryByText('{"capability"')).not.toBeInTheDocument();
  });

  it('transitions through the real environment registry and keeps unconnected device control unavailable', () => {
    render(<ChatWorkspace />);
    fireEvent.click(screen.getByRole('button', { name: 'Open environments' }));

    expect(screen.getByRole('heading', { name: 'JARVIS environments' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Devices.*authorized connectors/ })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /World.*Maps, authorized location/ }));

    expect(routerState.push).toHaveBeenCalledWith('/dashboard/geography');
    expect(useJarvisRuntime.getState().currentEnvironment).toBe('world');
  });
});
