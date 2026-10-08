> For the complete documentation index, see [llms.txt](https://agpt.co/docs/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://agpt.co/docs/platform/what-is-autogpt-platform.md).

# What is the AutoGPT Platform?

The AutoGPT Platform is a groundbreaking system that revolutionizes AI utilization for businesses and individuals. It enables the creation, deployment, and management of continuous agents that work tirelessly on your behalf, bringing unprecedented efficiency and innovation to your workflows.

## Key Features

* **Seamless Integration and Low-Code Workflows**: Rapidly create complex workflows without extensive coding knowledge.
* **Autonomous Operation and Continuous Agents**: Deploy cloud-based assistants that run indefinitely, activating on relevant triggers.
* **Intelligent Automation and Maximum Efficiency**: Streamline workflows by automating repetitive processes.
* **Reliable Performance and Predictable Execution**: Enjoy consistent and dependable long-running processes.

## Platform Architecture

The AutoGPT Platform consists of two main components:

### 1. AutoGPT Server

The powerhouse of our platform, containing:

* **Source Code**: Core logic driving agents and automation processes.
* **Infrastructure**: Robust systems ensuring reliable and scalable performance.
* **Marketplace**: A comprehensive marketplace for pre-built agents.

### 2. AutoGPT Frontend

The user interface where you interact with the platform:

* **Agent Builder**: Design and configure your own AI agents.
* **Workflow Management**: Build, modify, and optimize automation workflows.
* **Deployment Controls**: Manage the lifecycle of your agents.
* **Ready-to-Use Agents**: Select from pre-configured agents.
* **Agent Interaction**: Run and interact with agents through a user-friendly interface.
* **Monitoring and Analytics**: Track agent performance and gain insights.

## Platform Components

### Agents and Workflows

In the platform, you can create highly customized workflows to build agents. An agent is essentially an automated workflow that you design to perform specific tasks or processes. Create customized workflows to build agents for various tasks, including:

* Data processing and analysis
* Task scheduling and management
* Communication and notification systems
* Integration between different software tools
* AI-powered decision making and content generation

### Blocks as Integrations

Blocks represent actions and are the building blocks of your workflows, including:

* Connections to external services
* Data processing tools
* AI models for various tasks
* Custom scripts or functions
* Conditional logic and decision-making components

You can learn more under: [Build your own Blocks](/docs/platform/building-blocks/new_blocks.md)

## Available Language Models

The full model list — models, capabilities, context windows, and pricing — lives in the model catalog checked into the platform itself (`autogpt_platform/backend/backend/data/llm_registry/catalog.py`), so every install ships with the exact list its code supports. The platform comes pre-integrated with cutting-edge LLM providers:

* OpenAI - <https://openai.com/>
* Anthropic - <https://www.anthropic.com/>
* Groq - <https://groq.com/>
* Llama - <https://llamaindex.ai/>
* AI/ML API - <https://aimlapi.com/>
  * AI/ML API provides 300+ AI models including Deepseek, Gemini, ChatGPT. The models run at enterprise-grade rate limits and uptimes.

## License Overview

We've adopted a dual-license approach to balance open collaboration with sustainable development:

* **MIT License**: The majority of the AutoGPT repository remains under this license.
* **Polyform Shield License**: Applies to the new `autogpt_platform` folder.

This strategy allows us to share previously closed-source components, fostering a vibrant ecosystem of developers and users.

## Ready to Get Started?

* **Cloud:** Read the [Getting Started (Cloud)](/docs/platform/using-the-platform/getting-started-cloud.md) guide to start using the hosted platform immediately.
* **Self-Host:** Read the [Self-Hosting Guide](/docs/platform/self-hosting/getting-started.md) to run the platform on your own infrastructure.


---

# Agent Instructions
This documentation is published with GitBook. GitBook is the documentation platform designed so that both humans and AI agents can read, navigate, and reason over technical content effectively. Learn more at gitbook.com.

## Querying This Documentation
If you need additional information that is not directly available in this page, you can query the documentation dynamically by asking a question.

Perform an HTTP GET request on the current page URL with the `ask` query parameter, and the optional `goal` query parameter:

```
GET https://agpt.co/docs/platform/what-is-autogpt-platform.md?ask=<question>&goal=<endgoal>
```

`ask` is the immediate question: it should be specific, self-contained, and written in natural language.
`goal` is optional and describes the broader end goal you are ultimately trying to accomplish on behalf of the user. GitBook uses it to tailor the answer towards what is most useful for that goal.

The response will contain a direct answer to the question and relevant excerpts and sources from the documentation.

Use this mechanism when the answer is not explicitly present in the current page, you need clarification or additional context, or you want to retrieve related documentation sections.
