import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AdvancedAgentOrchestration from "@/components/advanced-agent-orchestration";
import { API_ENDPOINTS } from "@/config/api";
import { apiClient } from "@/lib/api-client";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const graphStatus = {
  graph: {
    total_agents: 1,
    by_status: { running: 1, paused: 0 },
    by_role: { researcher: 1 },
    pending_messages: { researcher: 0 },
    redis_connected: true,
  },
};

describe("AdvancedAgentOrchestration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.get).mockImplementation(async (endpoint) => {
      if (endpoint === API_ENDPOINTS.agents.graph.status) return graphStatus;
      if (endpoint === API_ENDPOINTS.agents.graph.agents) {
        return {
          agents: [{
            agent_id: "researcher-123",
            name: "Researcher",
            role: "researcher",
            status: "running",
            capabilities: ["research_cortex"],
            created_at: 1,
          }],
        };
      }
      if (endpoint === API_ENDPOINTS.agents.graph.roles) {
        return {
          roles: {
            researcher: {
              description: "Research and gather knowledge",
              capabilities: ["research_cortex"],
              default_model: "test-model",
            },
          },
        };
      }
      if (endpoint === API_ENDPOINTS.agents.graph.inboxMessages) return { messages: [] };
      return { messages: [] };
    });
  });

  it("loads real graph state and exposes lifecycle controls", async () => {
    render(<AdvancedAgentOrchestration />);

    expect(await screen.findByText("Connected to the JARVIS agent graph")).toBeInTheDocument();
    expect(await screen.findByText(/researcher-123/)).toBeInTheDocument();
    expect(screen.getByText("Agents in graph")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause Researcher" })).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith(API_ENDPOINTS.agents.graph.status);
  });

  it("submits a task by spawning the selected specialist with its request", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ agent_id: "researcher-456" });
    render(<AdvancedAgentOrchestration />);

    const taskField = await screen.findByRole("textbox", { name: "Task description" });
    fireEvent.change(taskField, { target: { value: "Summarize current space weather" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit task" }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        API_ENDPOINTS.agents.graph.spawn,
        {
          name: "Researcher task",
          role: "researcher",
          request: {
            task: "Summarize current space weather",
            query: "Summarize current space weather",
          },
        },
      );
    });
    expect(await screen.findByText(/Task submitted to researcher agent researcher-456/)).toBeInTheDocument();
  });
});
