import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockControlNavigation } = vi.hoisted(() => ({
  mockControlNavigation: vi.fn(),
}));

vi.mock('./api', () => ({
  default: {
    controlNavigation: (...args: unknown[]) => mockControlNavigation(...args),
  },
}));

import { useBrowserStore } from './store';

const session = {
  id: 'session-1',
  name: 'Research',
  privacy_mode: 'standard' as const,
  tabs: ['tab-1'],
  active_tab_id: 'tab-1',
  created_at: '',
  updated_at: '',
};

const tab = {
  id: 'tab-1',
  session_id: 'session-1',
  url: 'https://example.com/second',
  title: 'Example',
  favicon: '',
  is_loading: false,
  is_pinned: false,
  group: 'default',
  created_at: '',
  updated_at: '',
};

describe('browser session navigation controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useBrowserStore.setState({
      sessions: [session],
      tabs: { 'tab-1': tab },
      activeSessionId: session.id,
      activeTabId: tab.id,
      privacyMode: 'standard',
      isLoading: false,
      error: null,
      aiContext: { metadata: {}, text: 'old page' } as never,
    });
  });

  it('dispatches Back to the active session and synchronizes tab URL and page context', async () => {
    mockControlNavigation.mockResolvedValue({
      navigated: true,
      url: 'https://example.com/first',
      action: 'back',
      privacy_mode: 'standard',
    });

    const moved = await useBrowserStore.getState().goBack();

    expect(moved).toBe(true);
    expect(mockControlNavigation).toHaveBeenCalledWith('session-1', 'tab-1', 'back');
    expect(useBrowserStore.getState().tabs['tab-1'].url).toBe('https://example.com/first');
    expect(useBrowserStore.getState().activeTabId).toBe('tab-1');
    expect(useBrowserStore.getState().aiContext).toBeNull();
  });

  it('increments the active tab revision only after a successful Reload', async () => {
    mockControlNavigation.mockResolvedValue({
      navigated: true,
      url: tab.url,
      action: 'reload',
      privacy_mode: 'standard',
    });

    await useBrowserStore.getState().reload();

    expect(mockControlNavigation).toHaveBeenCalledWith('session-1', 'tab-1', 'reload');
    expect(useBrowserStore.getState().tabs['tab-1'].navigation_revision).toBe(1);
  });

  it('dispatches Forward against the active tab and synchronizes its URL', async () => {
    mockControlNavigation.mockResolvedValue({
      navigated: true,
      url: 'https://example.com/second',
      action: 'forward',
      privacy_mode: 'standard',
    });

    const moved = await useBrowserStore.getState().goForward();

    expect(moved).toBe(true);
    expect(mockControlNavigation).toHaveBeenCalledWith('session-1', 'tab-1', 'forward');
    expect(useBrowserStore.getState().tabs['tab-1'].url).toBe('https://example.com/second');
  });

  it('does not persist a private session tab URL to browser local storage', () => {
    const privateSession = { ...session, privacy_mode: 'private' as const };
    const secretTab = {
      ...tab,
      url: 'https://example.com/private-only',
      private_ephemeral_url: true,
    };
    useBrowserStore.setState({
      sessions: [privateSession],
      tabs: { 'tab-1': secretTab },
      activeSessionId: privateSession.id,
      activeTabId: secretTab.id,
      privacyMode: 'private',
      history: [{
        id: 'prior-visit',
        url: 'https://example.com/previously-saved',
        title: 'Earlier page',
        domain: 'example.com',
        visited_at: '',
        epoch: 0,
        user_id: 'user-1',
      }],
    });

    const persisted = JSON.parse(localStorage.getItem('jarvis-browser-store') || '{}').state;
    expect(JSON.stringify(persisted)).not.toContain('private-only');
    expect(persisted.sessions).toEqual([]);
    expect(persisted.history[0].url).toBe('https://example.com/previously-saved');

    useBrowserStore.setState({
      sessions: [{ ...privateSession, privacy_mode: 'standard' }],
      privacyMode: 'standard',
    });
    const afterModeSwitch = JSON.parse(localStorage.getItem('jarvis-browser-store') || '{}').state;
    expect(JSON.stringify(afterModeSwitch)).not.toContain('private-only');
    expect(afterModeSwitch.tabs).toEqual({});
    expect(afterModeSwitch.sessions[0].tabs).toEqual([]);
  });
});
