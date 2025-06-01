# RAM Agent Service Configuration System

The RAM Agent Service uses a hierarchical configuration system that allows you to define multiple AI agents, each with their own specialized capabilities, input sources, and output destinations.

## Configuration Overview

The configuration system is organized into two main levels:

1. **Agent Manifest** - Central registry of all available agents
2. **Individual Agent Configurations** - Detailed configuration for each agent's components

## Agent Manifest (config/agent_manifest.json)

The main configuration file that serves as a registry for all available agents in the system.

### Structure

```json
{
    "agents": [
        {
            "name": "AgentName",
            "description": "Description of what the agent does",
            "agent_config_file": "path/to/agent/config.json",
            "enabled": true/false
        }
    ]
}
```

### Fields

- **name**: Unique identifier for the agent
- **description**: Human-readable description of the agent's purpose and capabilities
- **agent_config_file**: Path to the agent's detailed configuration file
- **enabled**: Boolean flag to enable/disable the agent without removing its configuration

## Individual Agent Configuration

Each agent has its own configuration file that defines four main components:

### 1. Input Trigger

Defines how the agent receives input/requests.

```json
"input_trigger": {
    "python_code_module": "src/input_triggers/discord/discord_bot_trigger.py",
    "input_trigger_config_file": "config/agents/agent_name/trigger_config.json",
    "input_trigger_secrets_file": "config/agents/agent_name/secrets.json"
}
```

**Available Input Triggers:**
- **Discord Bot**: Listens for messages in specific Discord channels
- **Gmail Monitor**: Monitors Gmail inbox for new emails
- **File Watcher**: Monitors file system changes

**Configuration Files:**
- `input_trigger_config_file`: Contains trigger-specific settings (e.g., Discord channel name)
- `input_trigger_secrets_file`: Contains sensitive data (e.g., API keys, tokens)

### 2. Tools and Data (MCP Commands)

Defines what tools and data sources the agent can access through MCP (Model Context Protocol) commands.

```json
"tools_and_data": {
    "mcp_commands_config_file": "config/agents/agent_name/tools_config.json",
    "mcp_commands_secrets_file": "config/agents/agent_name/tools_secrets.json"
}
```

**MCP Command Structure:**
```json
{
    "command": "command_name",
    "aliases": ["/shortcut1", "/shortcut2"],
    "system_text": "/command_name",
    "system_description": "Description for the AI model",
    "description": "Human-readable description",
    "python_code_module": "path/to/implementation.py",
    "command_parameters": {
        "param1": "value1"
    },
    "response_format": "json|text",
    "enabled": true,
    "command_escape_text": "(in progress…)"
}
```

**Available Tool Categories:**
- **File I/O**: Read JSON files, Markdown files, plain text files
- **External APIs**: Timely time tracking, Calendar integration
- **LightRAG**: Document indexing and retrieval
- **UI Automation**: PyAutoGUI, TagUI runners

### 3. Chat Model

Defines the AI model configuration and behavior.

```json
"chat_model": {
    "chat_system_instructions_file": "config/agents/agent_name/system_instructions.txt",
    "chat_model_config_file": "config/agents/agent_name/chat_config.json",
    "chat_model_secrets_file": "config/agents/agent_name/chat_secrets.json"
}
```

**Chat Model Configuration:**
```json
{
    "python_code_module": "src/chat_models/chat_model_openai.py",
    "handler_function": "ask_chat_model_sync",
    "model": "gpt-4o",
    "temperature": 1.0,
    "max_tokens": 3000,
    "max_recusion_depth": 3,
    "use_memory": true,
    "memory_max_messages": 40,
    "memory_hours_limit": 192
}
```

### 4. Output Action

Defines how the agent sends responses or performs actions.

```json
"output_action": {
    "output_action_config_file": "config/agents/agent_name/output_config.json",
    "output_action_secrets_file": "config/agents/agent_name/output_secrets.json"
}
```

**Available Output Actions:**
- **Discord Bot**: Send messages to Discord channels
- **Gmail**: Create draft emails or send emails
- **File Writer**: Write to files on the file system

## Example Agent Configurations

### Kairos (Executive Assistant)

A time management assistant that:
- **Input**: Listens to Discord channel `executive_assistant_david`
- **Tools**: Access to projects, budgets, goals, tasks, and expense tracking
- **Output**: Responds via Discord
- **Model**: GPT-4o with memory (40 messages, 192 hours retention)

### Mercurius (Job Offer Responder)

An automated job application responder that:
- **Input**: Monitors Gmail for new emails
- **Tools**: Access to resume and response templates
- **Output**: Creates Gmail draft responses
- **Model**: GPT-4o for generating personalized responses

## Configuration File Organization

```
config/
├── agent_manifest.json                 # Main agent registry
├── example_agent_manifest.json         # Template/example
└── agents/
    ├── executive_assistant/
    │   ├── kairos_config.json          # Main agent config
    │   ├── discord_bot_trigger_config.json
    │   ├── discord_bot_secrets.json
    │   ├── kairos_tools_and_data_config.json
    │   ├── kairos_tools_and_data_secrets.json
    │   ├── kairos_chat_models_config.json
    │   ├── kairos_chat_models_secrets.json
    │   ├── kairos_chat_system_instructions.txt
    │   └── discord_bot_output_action.json
    └── gmail_job_offer_responder/
        ├── mercurius_config.json
        └── [similar structure...]
```

## Security Considerations

- **Secrets Files**: Store sensitive information like API keys, tokens, and passwords
- **Config Files**: Store non-sensitive configuration parameters
- **Separation**: Secrets are kept in separate files to enable secure deployment practices

## Adding New Agents

1. Create a new directory under `config/agents/your_agent_name/`
2. Create the main agent configuration file
3. Create component-specific configuration and secrets files
4. Add the agent entry to `config/agent_manifest.json`
5. Set `enabled: true` to activate the agent

## Best Practices

1. **Modular Design**: Each agent should have a clear, single responsibility
2. **Reusable Components**: Share common input triggers and output actions across agents
3. **Security**: Never commit secrets files to version control
4. **Documentation**: Include clear descriptions for each agent and tool
5. **Testing**: Use the `enabled` flag to safely test new agents without affecting production
