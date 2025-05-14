## Starting the Service (Default)

This command initializes the RAM Agent Service, loads agent configurations from `config/agent_manifest.json`, and starts listening for input triggers.

```bash
# Make sure your Python virtual environment is activated
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows

# Run the main Python script from the project root
python src/ras/main.py


# RAM Agent Service (RAS)
RAM Agent Service (RAS) is an agentic platform developed by RAM Software for orchestrating and executing autonomous AI agents that integrate deeply with business systems and workflows. RAS supports the Model Context Protocol (MCP) to manage structured inputs and actions, utilizes RAG (Retrieval-Augmented Generation) for dynamic, real-time knowledge access, and enables scalable inference pipelines for context-aware decision-making. Designed for modularity and control, RAS empowers teams to build and manage intelligent agents that adapt to complex environments and deliver high-leverage automation.

## ✨ Key Features

- **🔌 Model Context Protocol (MCP)**
  - Structured communication between agents and tools
  - Manages contextual input/output and defined agent actions

- **📚 Retrieval-Augmented Generation (RAG)**
  - Real-time knowledge access from external sources
  - Improves relevance and decision-making in dynamic environments

- **⚙️ Scalable Inference Pipelines**
  - Efficient execution of AI workloads across agents
  - Maintains traceability and context awareness

---

## 🧠 Agent Architecture

All agents are defined in: config/agent_manifest.json

Each agent is composed of the following modular components:

| Component             | Description                                                                 |
|-----------------------|-----------------------------------------------------------------------------|
| `Input Trigger`       | Initiates the agent (e.g. webhook, scheduler, command)                      |
| `Chat Model`          | The core LLM used for reasoning and output generation                       |
| `Output Action`       | Defines how results are delivered (e.g. message, file, API call)            |
| `Memory` (opt.)       | Stores contextual state or historical data                                  |
| `Tools & Data` (opt.) | Allows use of external APIs, MCP commands, or RAG-enhanced data access      |

---

## 🧩 Design Principles

- **Modularity** – Components can be swapped or extended with minimal friction
- **Agentic Behavior** – Agents reason and act autonomously within defined scopes
- **Observability** – Detailed logging and diagnostics for transparency and debugging
- **Control** – Secure, declarative control over agent execution paths

## Prerequisites

- Python 3.12


## Development

The project structure is organized as follows (relative to the project root):

- `src/ras/main.py`: Main entry point for the service.
- `config/`: Configuration settings.
  - `agent_manifest.json`: Defines all available agents and their components.
- `src/input_triggers/`: Dynamically loaded modules for initiating agents (e.g., Discord, Email, File Watcher).
- `src/chat_models/`: Dynamically loaded modules for LLM communication (e.g., OpenAI, Anthropic, Google).
- `src/memory/`: Dynamically loaded modules for agent memory and history management.
- `src/tools_and_data/`: Dynamically loaded modules for tools, external APIs, MCP interactions, and RAG data access.

