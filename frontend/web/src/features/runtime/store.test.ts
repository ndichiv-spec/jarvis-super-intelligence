import { beforeEach, describe, expect, it } from 'vitest';
import { useJarvisRuntime } from './store';

describe('JARVIS runtime state', () => {
  beforeEach(() => {
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

  it('records real environment transitions and retains current session context', () => {
    useJarvisRuntime.getState().setSessionId('session-7');
    useJarvisRuntime.getState().transitionEnvironment('world');
    useJarvisRuntime.getState().transitionEnvironment('conversation');

    expect(useJarvisRuntime.getState()).toMatchObject({
      currentEnvironment: 'conversation',
      previousEnvironment: 'world',
      currentSessionId: 'session-7',
      environmentHistory: [
        { from: 'conversation', to: 'world' },
        { from: 'world', to: 'conversation' },
      ],
    });
  });

  it('normalizes actual runtime events into a human-readable activity without exposing payload JSON', () => {
    useJarvisRuntime.getState().ingestWebSocketEvent({
      id: 'event-1',
      type: 'system_alert',
      timestamp: '2026-10-08T08:00:00.000Z',
      data: { message: 'Provider connection lost', status: 'warning' },
    });

    expect(useJarvisRuntime.getState().activities[0]).toMatchObject({
      id: 'event-1',
      summary: 'Provider connection lost',
      detail: 'warning',
      source: 'websocket',
    });
    expect(useJarvisRuntime.getState().activities[0].summary).not.toContain('{');
  });

  it('keeps selection, active task, and explicit permission state in the shared runtime', () => {
    useJarvisRuntime.getState().setSelectedObject({
      environment: 'world',
      kind: 'place',
      label: 'Central Park',
    });
    useJarvisRuntime.getState().setCurrentTask({
      id: 'task-1',
      title: 'Route planning',
      status: 'running',
      updatedAt: '2026-10-08T08:00:00.000Z',
    });
    useJarvisRuntime.getState().setPermissionState('geolocation', 'granted');

    expect(useJarvisRuntime.getState()).toMatchObject({
      selectedObject: { environment: 'world', label: 'Central Park' },
      currentTask: { id: 'task-1', status: 'running' },
      permissions: { geolocation: 'granted' },
    });
  });

  it('drives voice presence from actual voice runtime event names', () => {
    useJarvisRuntime.getState().ingestChatActivity({
      event_id: 'voice-1',
      event_type: 'voice.state.listening',
      timestamp: '2026-10-08T08:00:00.000Z',
      message: 'Voice session started',
      status: 'started',
    });
    expect(useJarvisRuntime.getState().voiceState).toBe('listening');

    useJarvisRuntime.getState().ingestChatActivity({
      event_id: 'voice-2',
      event_type: 'voice.speaking.started',
      timestamp: '2026-10-08T08:00:01.000Z',
      message: 'JARVIS is speaking',
      status: 'started',
    });
    expect(useJarvisRuntime.getState().voiceState).toBe('speaking');
  });

  it('adapts only backend-reported capability and provider data for the runtime graph', () => {
    useJarvisRuntime.getState().syncCapabilityRegistry([{
      capability: 'web.search',
      category: 'web',
      tool: 'search_web',
      permissions: ['network.search'],
      provider: 'search-provider',
      provider_service: 'web-search',
      model: null,
      availability: 'available',
      health: 'ok',
      ai_backed: false,
    }], '2026-10-08T08:00:00.000Z');
    useJarvisRuntime.getState().syncIntegrations([{
      provider: 'search-provider',
      display_name: 'Search provider',
      connected: true,
      status: 'ready',
      capabilities: ['web_search'],
      configured: true,
    }]);

    expect(useJarvisRuntime.getState()).toMatchObject({
      capabilityRegistryReported: true,
      capabilityRegistryUpdatedAt: '2026-10-08T08:00:00.000Z',
      capabilities: [{
        id: 'web.search',
        tool: 'search_web',
        availability: 'available',
        permissions: ['network.search'],
      }],
      integrations: [{
        id: 'search-provider',
        connected: true,
        configured: true,
        capabilities: ['web_search'],
      }],
    });
  });

  it('accepts only supported presentation envelopes and binds actual presentation voice state', () => {
    const envelope = {
      protocol: 'jarvis.presentation' as const,
      version: '1.0',
      issuedAt: '2026-10-08T08:00:00.000Z',
      source: { runtime: 'jarvis-core', requestId: 'request-1' },
      security: { authorizationContext: 'authctx-opaque', capabilities: [] },
      intent: {
        id: 'presentation-1',
        sessionId: 'session-1',
        sequence: 1,
        environment: { id: 'conversation', type: 'conversation' as const },
        mode: 'focused' as const,
        voice: { enabled: true, state: 'speaking' as const },
      },
    };
    expect(useJarvisRuntime.getState().applyPresentation(envelope)).toBe(true);
    expect(useJarvisRuntime.getState()).toMatchObject({
      currentPresentation: { intent: { id: 'presentation-1' } },
      voiceState: 'speaking',
    });
    expect(useJarvisRuntime.getState().applyPresentation({
      ...envelope,
      version: '2.0',
    })).toBe(false);
  });

  it('lets the semantic presentation intent, not the current route, select the active environment', () => {
    const envelope = {
      protocol: 'jarvis.presentation' as const,
      version: '1.0',
      issuedAt: '2026-10-08T08:00:00.000Z',
      source: { runtime: 'jarvis-core', requestId: 'request-2' },
      security: { authorizationContext: 'authctx-opaque', capabilities: ['location'] },
      intent: {
        id: 'presentation-2',
        sessionId: 'session-1',
        sequence: 2,
        environment: { id: 'geospatial', type: 'geospatial' as const },
        mode: 'focused' as const,
      },
    };

    expect(useJarvisRuntime.getState().applyPresentation(envelope)).toBe(true);
    expect(useJarvisRuntime.getState()).toMatchObject({
      currentEnvironment: 'world',
      previousEnvironment: 'conversation',
      currentPresentation: { intent: { environment: { type: 'geospatial' } } },
      environmentHistory: [{
        from: 'conversation',
        to: 'world',
      }],
    });
  });
});
