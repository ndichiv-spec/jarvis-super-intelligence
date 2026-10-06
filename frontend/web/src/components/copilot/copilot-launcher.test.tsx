import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { usePathname } from 'next/navigation';

import { CopilotLauncher } from './copilot-launcher';
import { useAuthStore } from '@/stores/authStore';

const chatLifecycle = vi.hoisted(() => ({
  initChat: vi.fn(),
  disposeChat: vi.fn(),
  browserContextError: null as string | null,
}));

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(),
}));

vi.mock('@/features/chat/store', () => ({
  useChatStore: Object.assign(
    (selector: (state: typeof chatLifecycle) => unknown) => selector(chatLifecycle),
    { getState: () => chatLifecycle },
  ),
}));

vi.mock('@/components/chat/chat-window', () => ({
  ChatWindow: () => <textarea aria-label="Message JARVIS" />,
}));

describe('CopilotLauncher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatLifecycle.browserContextError = null;
    vi.mocked(usePathname).mockReturnValue('/dashboard');
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
      window.setTimeout(() => callback(performance.now()), 0),
    );
    vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('stays hidden when logged out or on a public route', async () => {
    const { rerender } = render(<CopilotLauncher />);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'JARVIS Copilot' })).not.toBeInTheDocument());

    act(() => useAuthStore.setState({ token: 'test-token', isAuthenticated: true }));
    vi.mocked(usePathname).mockReturnValue('/login');
    rerender(<CopilotLauncher />);

    expect(screen.queryByRole('button', { name: 'JARVIS Copilot' })).not.toBeInTheDocument();
  });

  it('toggles with Ctrl+J, focuses chat, and restores focus on Escape', async () => {
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true });
    const { unmount } = render(<CopilotLauncher />);

    const launcher = await screen.findByRole('button', { name: 'JARVIS Copilot' });
    await waitFor(() => expect(chatLifecycle.initChat).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(window, { key: 'j', ctrlKey: true });

    const composer = await screen.findByRole('textbox', { name: 'Message JARVIS' });
    await waitFor(() => expect(composer).toHaveFocus());

    fireEvent.keyDown(composer, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('region', { name: 'JARVIS Copilot' })).not.toBeInTheDocument());
    await waitFor(() => expect(launcher).toHaveFocus());
    unmount();
    expect(chatLifecycle.disposeChat).toHaveBeenCalledTimes(1);
  });

  it('reports browser context failures and allows retrying initialization', async () => {
    chatLifecycle.browserContextError = 'Browser integration could not load';
    useAuthStore.setState({ token: 'test-token', isAuthenticated: true });
    render(<CopilotLauncher />);
    fireEvent.click(await screen.findByRole('button', { name: 'JARVIS Copilot' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Browser context is unavailable: Browser integration could not load',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(chatLifecycle.initChat).toHaveBeenCalled();
  });
});
