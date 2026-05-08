# Contributing to HC Agent

Thank you for your interest in contributing to HC Agent! This document provides guidelines and steps for contributing.

## Getting Started

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/your-username/HC_Agent.git
   cd HC_Agent
   ```
3. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Development Guidelines

### Code Style
- Follow PEP 8 conventions
- Use meaningful variable and function names
- Add docstrings for public functions and classes
- Keep line length under 120 characters

### Project Structure
- `hc_agent.py` - Core orchestrator
- `memory/` - Memory system (CSA + HCA)
- `evolution/` - Self-evolution subsystem
- `frontends/` - User interfaces (Streamlit + Console)
- `tools.py` - Tool registry

### Commit Messages
- Use present tense: "Add feature" not "Added feature"
- Use imperative mood: "Fix bug" not "Fixes bug"
- Reference issues where applicable: "Fix #123: resolve null pointer"

## Submitting Changes

1. Ensure your code passes linting:
   ```bash
   flake8 . --max-line-length=120
   ```
2. Test your changes locally
3. Push to your fork and submit a **Pull Request**
4. Fill in the PR template with a clear description

## Reporting Issues

Use the [Issue Templates](https://github.com/emomg/HC_Agent/issues/new/choose) to report bugs or request features.

## Architecture Notes

HC Agent uses a hybrid attention memory system:
- **CSA (Contextual Semantic Attention)**: Scores relevance by semantic similarity
- **HCA (Historical Context Attention)**: Scores by temporal decay + access frequency
- **CDH Context Budget**: Allocates context window across memory domains

When modifying memory or evolution modules, please ensure compatibility with the scoring pipeline.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
