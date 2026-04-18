# Pico Agent

> A pico-sized coding agent used for experiment and testing agent harness with different LLM models.

Pico Agent is a minimal, single-file coding agent that connects to LLM providers via the OpenAI-compatible chat completions API. It ships with file reading, editing, searching, and shell execution tools — giving the model everything it needs to assist with real coding tasks, all in under 150 lines of Python.

## Features

- **File operations** — read, create, and edit files
- **Directory listing** — browse project structure
- **Regex search** — find patterns across files recursively
- **Shell execution** — run arbitrary commands (30s timeout)
- **Agentic loop** — multi-turn tool calling until the task is done
- **Multiple providers** — pluggable provider config for experimenting with different LLMs

## Quick Start

```bash
# Clone the repo
git clone https://github.com/your-org/pico-agent.git
cd pico-agent

# Install uv (if not already installed)
pip install uv

# Create virtual environment and install dependencies
uv sync

# Configure your API key
cp .env.example .env
# Edit .env and add your API key

# Run
uv run python agent.py
```

## System-wide Installation

To use `pico` from any directory:

```bash
# Add pico to your PATH (pick one option)

# Option 1: Link to ~/.local/bin (recommended)
mkdir -p ~/.local/bin
ln -s "$(pwd)/pico" ~/.local/bin/pico

# Option 2: Link to /usr/local/bin (requires sudo)
sudo ln -s "$(pwd)/pico" /usr/local/bin/pico

# Make sure ~/.local/bin is in your PATH (add to ~/.bashrc or ~/.zshrc)
export PATH="$HOME/.local/bin:$PATH"

# Now you can run from anywhere!
pico
```

The `pico` command will:
- Stay in your current working directory
- Use the installed virtual environment
- Run agent.py from the repo

## Configuration

Environment variables are loaded from a `.env` file:

| Variable       | Description                | Default  |
| -------------- | -------------------------- | -------- |
| `BASE_URL`     | Base URL for the API       | `https://api.z.ai/api/coding/paas/v4` |
| `MODEL`        | Model to use               | `glm-4.7`|
| `API_KEY`      | API key for the provider   | —        |



## Project Structure

```
pico-agent/
├── agent.py          # The entire agent (entry point)
├── requirements.txt  # Python dependencies
├── .env.example      # Template for environment variables
└── README.md
```

## License

MIT
