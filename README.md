# Omarchy Troubleshooter & Task Recipes

A plugin for Omarchy Linux that provides a centralized hub to log recurring PC issues, trigger auto-fixes via your AI agent, and run ordered shell command sequences (recipes).

## Features

- **Agent Fixes Tab**:
  - Log recurring system issues with symptom descriptions, known solutions, and custom prompts.
  - Automatically combine your context with system logs to run "Auto-Fixes" via your default configured Omarchy agent (e.g., OpenCode, Claude).

- **Shell Recipes Tab**:
  - Save ordered multi-step shell command sequences.
  - Interactive execution in an Omarchy terminal with step-by-step confirmation.

## Installation

1. Clone or download this repository.
2. Link the plugin folder to your omarchy config:
   `ln -s /path/to/omarchy-troubleshooter ~/.config/omarchy/plugins/mahan.troubleshooter`
3. Restart the shell:
   `omarchy restart shell`

## Publishing

This plugin follows Omarchy's plugin manifest schema and is ready for submission to the marketplace.
