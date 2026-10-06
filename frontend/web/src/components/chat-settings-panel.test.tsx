import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ChatSettingsPanel from '@/components/chat-settings-panel';
import type { ChatSettings } from '@/features/chat/types';

// Mock the chat store
vi.mock('@/features/chat/store', () => ({
  useChatStore: (selector: (state: {
    chatSettings: ChatSettings;
    updateChatSettings: (settings: Partial<ChatSettings>) => void;
  }) => unknown) => selector({
    chatSettings: {
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
      system_prompt: '',
      web_search: false,
      code_interpreter: false,
    },
    updateChatSettings: vi.fn(),
  }),
}));

describe('ChatSettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the settings toggle button', () => {
    render(<ChatSettingsPanel />);
    expect(screen.getByRole('button', { name: 'Chat Settings' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands to show settings controls when clicked', async () => {
    render(<ChatSettingsPanel />);
    const toggle = screen.getByRole('button', { name: 'Chat Settings' });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText('Temperature')).toBeInTheDocument();
      expect(screen.getByText('Top-P')).toBeInTheDocument();
      expect(screen.getByText('Max Tokens')).toBeInTheDocument();
    });
  });

  it('shows Web Search and Code Interpreter toggles', async () => {
    render(<ChatSettingsPanel />);
    const toggle = screen.getByRole('button', { name: 'Chat Settings' });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText('Web Search')).toBeInTheDocument();
      expect(screen.getByText('Code Interpreter')).toBeInTheDocument();
    });
  });

  it('collapses settings when toggle is clicked again', async () => {
    render(<ChatSettingsPanel />);
    const toggle = screen.getByRole('button', { name: 'Chat Settings' });
    fireEvent.click(toggle);

    await waitFor(() => {
      expect(screen.getByText('Temperature')).toBeInTheDocument();
    });

    fireEvent.click(toggle);

    await waitFor(() => {
      expect(screen.queryByText('Temperature')).not.toBeInTheDocument();
    });
  });
});
