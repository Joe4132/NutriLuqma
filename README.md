# AWS Workshop Setup Guide

## Prerequisites

You build on your own machine, so install these tools before the event. Each one has a quick verification command so you can confirm it works.

| Tool | Purpose | Minimum Version | Installation |
|------|---------|----------------|--------------|
| Kiro | The agentic IDE you build in | Latest | [kiro.dev](https://kiro.dev) |
| Node.js | Runs the AgentCore CLI | 20 or later | [nodejs.org/download](https://nodejs.org/download) |
| Python | The agent language | 3.12 or later | [python.org/downloads](https://python.org/downloads) |
| uv | Python environment and package manager | Latest | [docs.astral.sh/uv](https://docs.astral.sh/uv) |
| AWS CLI | Talks to AWS | v2 | [AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| git | Version control for your repository | Latest | [git-scm.com/downloads](https://git-scm.com/downloads) |
| Docker (optional) | Only for local container builds | Latest | [Docker Desktop](https://docker.com/desktop) |

## Platform Notes

The terminal commands in this workshop use a **POSIX shell** (bash or zsh), the default on macOS and Linux.

### On Windows:
- Run commands in **WSL** (Windows Subsystem for Linux) or **Git Bash**
- **Do NOT** use PowerShell or Command Prompt for workshop commands
- For AWS CLI commands you can also use **AWS CloudShell** in the browser

## Installation Steps

### 1. Install Required Tools

**Node.js 20+**:
```bash
# Download from nodejs.org or use package manager
node --version  # Verify: should show v20.x.x or higher
```

**Python 3.12+**:
```bash
# Windows with winget:
winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements

# Or download from python.org
python --version  # Verify: should show Python 3.12.x or higher
```

**uv** (Python package manager):
```bash
# Windows PowerShell:
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# POSIX shells (WSL/Git Bash):
curl -LsSf https://astral.sh/uv/install.sh | sh

uv --version  # Verify installation
```

**AWS CLI v2**:
- Download MSI installer from [AWS CLI install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Run the installer
```bash
aws --version  # Verify installation
```

**git**:
- Download from [git-scm.com](https://git-scm.com/downloads)
```bash
git --version  # Verify installation
```

### 2. Install AgentCore CLI
```bash
npm install -g @aws/agentcore
agentcore --version  # Should print a version number
agentcore --help     # Should list dev, deploy, and add commands
```

**Note**: If `agentcore --version` shows a usage error or different commands, another tool named `agentcore` might be shadowing it. Ensure the npm global bin directory is ahead of other paths.

### 3. Install Kiro
- Download from [kiro.dev](https://kiro.dev)
- Install and launch Kiro IDE

### 4. Configure AWS Credentials

Create or update your AWS credentials file at `~/.aws/credentials`:

```ini
[workshop]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
aws_session_token = YOUR_SESSION_TOKEN
region = us-west-2
```

## Verification

Run these commands and confirm each returns a version:

```bash
node --version
python --version      # Should be 3.12.x or higher
uv --version
aws --version
git --version
agentcore --version
```

Expected output (versions may vary):
```
v20.17.0
Python 3.12.4
uv 0.5.11
aws-cli/2.17.0 Python/3.12.4
git version 2.45.2
agentcore/1.0.0
```

## AWS CDK Note

`agentcore deploy` provisions your agent with AWS CDK under the hood. The CLI generates and manages a CDK app inside your project (`agentcore/`), so you do not install the CDK yourself.

Deploying does require the AWS account to be CDK-bootstrapped once:
- At an AWS event, the provided account is already bootstrapped
- In your own account, run `npx aws-cdk bootstrap` once before your first `agentcore deploy`

## Docker (Optional)

Docker is optional. The workshop's default build path (CodeZip) uploads your code and builds the container image in the cloud with AWS CodeBuild, so you do not need Docker running on your machine.

Install and run Docker only if you deliberately switch to a local container build.

## Troubleshooting

### Common Issues:

1. **Python version too old**:
   - Upgrade to Python 3.12+ from python.org

2. **AWS CLI not found**:
   - Ensure AWS CLI v2 is installed and in PATH
   - On Windows, may need to restart terminal after installation

3. **AgentCore CLI conflict**:
   - Check `npm config get prefix` for npm global bin directory
   - Ensure this directory is first in your PATH

4. **POSIX shell commands on Windows**:
   - Use WSL or Git Bash instead of PowerShell/CMD
   - Or use AWS CloudShell in browser

### Quick Setup Script (WSL/Git Bash):
```bash
#!/bin/bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install AgentCore CLI
npm install -g @aws/agentcore

# Verify installations
echo "=== Verification ==="
node --version
python3 --version
uv --version
aws --version
git --version
agentcore --version
```

## Next Steps

1. Complete all verifications above
2. Configure AWS credentials with your workshop profile
3. Launch Kiro IDE
4. Begin workshop exercises

---

*Last updated: September 1, 2026*