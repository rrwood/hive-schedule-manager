#!/bin/bash
# Hive Schedule Manager - Repository Setup Script
# This script creates the complete directory structure and files for HACS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get user input
echo -e "${GREEN}=== Hive Schedule Manager - Repository Setup ===${NC}"
echo ""
read -p "Enter your GitHub username: " GITHUB_USERNAME
read -p "Enter your name for license: " USER_NAME
read -p "Enter repository name [hive-schedule-manager]: " REPO_NAME
REPO_NAME=${REPO_NAME:-hive-schedule-manager}

echo ""
echo -e "${YELLOW}Creating directory structure...${NC}"

# Create directory structure
mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE
mkdir -p custom_components/hive_schedule/translations

echo -e "${GREEN}✓ Directory structure created${NC}"

# Create .gitignore
cat > .gitignore << 'EOF'
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Distribution / packaging
*.egg-info/
dist/
build/

# Unit test / coverage
htmlcov/
.tox/
.coverage
.pytest_cache/

# Environments
.env
venv/
env/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
EOF

echo -e "${GREEN}✓ Created .gitignore${NC}"

# Create hacs.json
cat > hacs.json << EOF
{
  "name": "Hive Schedule Manager",
  "render_readme": true,
  "homeassistant": "2024.1.0"
}
EOF

echo -e "${GREEN}✓ Created hacs.json${NC}"

# Create manifest.json
cat > custom_components/hive_schedule/manifest.json << EOF
{
  "domain": "hive_schedule",
  "name": "Hive Schedule Manager",
  "version": "1.0.0",
  "documentation": "https://github.com/${GITHUB_USERNAME}/${REPO_NAME}",
  "issue_tracker": "https://github.com/${GITHUB_USERNAME}/${REPO_NAME}/issues",
  "codeowners": ["@${GITHUB_USERNAME}"],
  "config_flow": false,
  "dependencies": ["hive"],
  "requirements": ["requests>=2.31.0"],
  "iot_class": "cloud_polling",
  "after_dependencies": ["hive"]
}
EOF

echo -e "${GREEN}✓ Created manifest.json${NC}"

# Create services.yaml
cat > custom_components/hive_schedule/services.yaml << 'EOF'
set_heating_schedule:
  name: Set Heating Schedule
  description: Update the complete weekly heating schedule for your Hive thermostat
  fields:
    node_id:
      name: Node ID
      description: The Hive heating node ID
      required: true
      example: "d2708e98-f22f-483e-b590-9ddbd642a3b7"
      selector:
        text:
    schedule:
      name: Schedule
      description: Complete weekly schedule configuration
      required: true

set_day_schedule:
  name: Set Day Schedule
  description: Update the heating schedule for a single day
  fields:
    node_id:
      name: Node ID
      description: The Hive heating node ID
      required: true
      selector:
        text:
    day:
      name: Day
      description: Day of the week to update
      required: true
      selector:
        select:
          options:
            - "monday"
            - "tuesday"
            - "wednesday"
            - "thursday"
            - "friday"
            - "saturday"
            - "sunday"
    schedule:
      name: Schedule
      description: Schedule entries for the day
      required: true

update_from_calendar:
  name: Update from Calendar
  description: Update tomorrow's schedule based on calendar
  fields:
    node_id:
      name: Node ID
      description: The Hive heating node ID
      required: true
      selector:
        text:
    is_workday:
      name: Is Workday
      description: Whether tomorrow is a work day
      required: true
      selector:
        boolean:
    wake_time:
      name: Wake Time
      description: Optional custom wake time (HH:MM format)
      required: false
      selector:
        time:
EOF

echo -e "${GREEN}✓ Created services.yaml${NC}"

# Create strings.json
cat > custom_components/hive_schedule/strings.json << 'EOF'
{
  "title": "Hive Schedule Manager",
  "services": {
    "set_heating_schedule": {
      "name": "Set heating schedule",
      "description": "Update the complete weekly heating schedule."
    },
    "set_day_schedule": {
      "name": "Set day schedule",
      "description": "Update the heating schedule for a single day."
    },
    "update_from_calendar": {
      "name": "Update from calendar",
      "description": "Update tomorrow's schedule based on calendar."
    }
  }
}
EOF

echo -e "${GREEN}✓ Created strings.json${NC}"

# Copy strings.json to translations
cp custom_components/hive_schedule/strings.json custom_components/hive_schedule/translations/en.json

echo -e "${GREEN}✓ Created translations/en.json${NC}"

# Create LICENSE
cat > LICENSE << EOF
MIT License

Copyright (c) $(date +%Y) ${USER_NAME}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

echo -e "${GREEN}✓ Created LICENSE${NC}"

# Create GitHub workflows
cat > .github/workflows/validate.yml << 'EOF'
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"

jobs:
  validate:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - name: HACS validation
        uses: "hacs/action@main"
        with:
          category: "integration"
EOF

echo -e "${GREEN}✓ Created validate.yml workflow${NC}"

# Create bug report template
cat > .github/ISSUE_TEMPLATE/bug_report.md << 'EOF'
---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: bug
---

**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior.

**Expected behavior**
What you expected to happen.

**Configuration**
```yaml
# Your relevant configuration
```

**Versions:**
 - Home Assistant: [e.g. 2024.1.0]
 - Hive Schedule Manager: [e.g. 1.0.0]

**Logs**
```
# Paste relevant logs
```
EOF

echo -e "${GREEN}✓ Created bug report template${NC}"

# Create feature request template
cat > .github/ISSUE_TEMPLATE/feature_request.md << 'EOF'
---
name: Feature request
about: Suggest an idea
title: '[FEATURE] '
labels: enhancement
---

**Is your feature request related to a problem?**
Description of the problem.

**Describe the solution you'd like**
What you want to happen.

**Additional context**
Any other context.
EOF

echo -e "${GREEN}✓ Created feature request template${NC}"

# Create README
cat > README.md << EOF
# Hive Schedule Manager for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/${GITHUB_USERNAME}/${REPO_NAME}.svg)](https://github.com/${GITHUB_USERNAME}/${REPO_NAME}/releases)
[![License](https://img.shields.io/github/license/${GITHUB_USERNAME}/${REPO_NAME}.svg)](LICENSE)

A Home Assistant custom integration that extends the official Hive integration to enable programmatic control of heating schedules.

## Features

- ✅ Full schedule control for any day of the week
- ✅ Calendar-based automation
- ✅ Works with existing Hive integration
- ✅ Simple service calls

## Installation

### HACS (Recommended)

1. Open HACS
2. Go to "Integrations"
3. Click the three dots (top right) → "Custom repositories"
4. Add: \`https://github.com/${GITHUB_USERNAME}/${REPO_NAME}\`
5. Category: "Integration"
6. Click "Add"
7. Find "Hive Schedule Manager" and click "Download"
8. Restart Home Assistant

### Manual

Copy \`custom_components/hive_schedule\` to your \`<config>/custom_components/\` directory.

## Configuration

Add to \`configuration.yaml\`:

\`\`\`yaml
hive_schedule:
\`\`\`

Restart Home Assistant.

## Finding Your Node ID

1. Go to https://my.hivehome.com
2. Open Developer Tools (F12)
3. Go to Network tab
4. Make a change to your heating
5. Look for requests to \`beekeeper-uk.hivehome.com\`
6. The URL contains your node ID

## Usage

### Set Tomorrow's Schedule

\`\`\`yaml
service: hive_schedule.update_from_calendar
data:
  node_id: "YOUR_NODE_ID"
  is_workday: true
\`\`\`

### Set Specific Day

\`\`\`yaml
service: hive_schedule.set_day_schedule
data:
  node_id: "YOUR_NODE_ID"
  day: "monday"
  schedule:
    - time: "06:30"
      temp: 18.0
    - time: "21:30"
      temp: 16.0
\`\`\`

## Example Automation

\`\`\`yaml
automation:
  - alias: "Update Tomorrow's Heating"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: hive_schedule.update_from_calendar
        data:
          node_id: "YOUR_NODE_ID"
          is_workday: >
            {{ (now() + timedelta(days=1)).weekday() < 5 }}
\`\`\`

## Support

- [Report a Bug](https://github.com/${GITHUB_USERNAME}/${REPO_NAME}/issues/new?template=bug_report.md)
- [Request a Feature](https://github.com/${GITHUB_USERNAME}/${REPO_NAME}/issues/new?template=feature_request.md)

## License

MIT License - see [LICENSE](LICENSE)

## Disclaimer

This is unofficial and not affiliated with British Gas or Hive.
EOF

echo -e "${GREEN}✓ Created README.md${NC}"

# Create info.md for HACS
cat > info.md << 'EOF'
# Hive Schedule Manager

Extends the Hive integration to enable programmatic control of heating schedules.

## Features

✅ Update heating schedules via service calls
✅ Set schedules for individual days or full week  
✅ Calendar-based automation support
✅ Compatible with existing Hive integration

## Quick Start

After installation:

1. Add to `configuration.yaml`:
   ```yaml
   hive_schedule:
   ```
2. Restart Home Assistant
3. Find your Node ID (see README)
4. Use service calls in automations

## Services

- `hive_schedule.set_heating_schedule` - Full week schedule
- `hive_schedule.set_day_schedule` - Single day
- `hive_schedule.update_from_calendar` - Calendar-based

## Example

```yaml
service: hive_schedule.update_from_calendar
data:
  node_id: "YOUR_NODE_ID"
  is_workday: true
```

See full documentation in [README](https://github.com/YOUR_USERNAME/hive-schedule-manager).
EOF

echo -e "${GREEN}✓ Created info.md${NC}"

echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Copy the __init__.py from the artifact to custom_components/hive_schedule/"
echo "2. Initialize git repository:"
echo "   git init"
echo "   git add ."
echo "   git commit -m 'Initial commit'"
echo ""
echo "3. Create GitHub repository and push:"
echo "   git remote add origin https://github.com/${GITHUB_USERNAME}/${REPO_NAME}.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "4. Add repository description and topics on GitHub"
echo ""
echo "5. Create first release:"
echo "   git tag -a v1.0.0 -m 'Initial release'"
echo "   git push origin v1.0.0"
echo ""
echo -e "${GREEN}Repository URL: https://github.com/${GITHUB_USERNAME}/${REPO_NAME}${NC}"
