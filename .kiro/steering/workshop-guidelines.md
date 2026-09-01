# AWS Agent Workshop Steering

## Project Overview
Building an agentic AI solution with the Strands Agents SDK and the AgentCore CLI.

## Core Principles

### Documentation First
- **Always** look up current AWS, AgentCore, and Strands documentation with MCP tools before writing code
- Never rely solely on prior knowledge or training data
- Use the MCP servers configured in `.kiro/settings/mcp.json`:
  - `aws-documentation` for AWS services
  - `bedrock-agentcore` for AgentCore CLI
  - `strands-agents` for Strands SDK

### Python Coding Standards
- Use type hints for all function parameters and return values
- Add short explanatory comments for non-obvious logic
- Keep functions focused and single-purpose
- Follow PEP 8 style guidelines

### Strands SDK Patterns
- Agent tools MUST use the Strands `@tool` decorator pattern
- Tools should have clear descriptions and parameter definitions
- Follow Strands best practices for tool design and error handling

### AWS Configuration
- All AWS operations target `us-west-2` region
- AWS CLI commands include `--no-cli-pager` option for clean output
- Use the workshop profile from AWS credentials

### Code Philosophy
- Stay minimal and focused on the concept being demonstrated
- Avoid unnecessary abstraction or over-engineering
- Each example should illustrate one clear concept
- Remove debug code and verbose logging from final implementations

## MCP Tool Usage
When writing code that involves:
- AWS services → query `aws-documentation` MCP server
- AgentCore CLI → query `bedrock-agentcore` MCP server  
- Strands SDK → query `strands-agents` MCP server

## File Structure
- Keep source code in `src/` directory
- Configuration files in root or config directories
- Documentation in `docs/` or README files
- Tests in `tests/` directory

## Verification Checklist
Before submitting any code:
1. [ ] MCP documentation consulted
2. [ ] Type hints added to Python functions
3. [ ] AWS region set to us-west-2
4. [ ] Strands @tool decorator used for agent tools
5. [ ] Code is minimal and focused
6. [ ] AWS CLI commands include --no-cli-pager
