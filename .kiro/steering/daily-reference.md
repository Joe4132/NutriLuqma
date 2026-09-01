---
inclusion: always
---

# AWS Agent Workshop - Daily Guidelines

## Quick Reference

1. **Documentation First**: Use MCP tools (aws-documentation, bedrock-agentcore, strands-agents) before coding
2. **Python**: Type hints + short comments
3. **Strands**: Use @tool decorator pattern
4. **AWS**: us-west-2 region, --no-cli-pager flag
5. **Code**: Minimal, focused examples

## MCP Commands to Remember
- Search AWS docs before implementing AWS services
- Check AgentCore patterns before CLI usage  
- Review Strands examples before tool creation

## AWS Commands Template
```bash
aws <service> <command> --region us-west-2 --no-cli-pager [--profile workshop]
```

## Python Tool Template
```python
from strands import tool

@tool
def example_tool(param: str) -> str:
    """Short description of what this tool does."""
    # Implementation here
    return result
```
