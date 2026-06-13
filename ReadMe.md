We're building a AI Workspace for Agent Forge AI Hackathon Build Production AI Systems. The following is some details / features that we want to implement:

- One AI agent can receive prompts from team members
- That AI agent has the entire workspace as context
- The AI agent can vibecode and work with different team members prompts seamlessly and in parallel
- Problem: Too many conflicts if too many team members on the same project at the same time using different AI models that probably has different workspace context. Maybe the team can choose which model to use using TokenRouter

The stack is flexible but we want the following tools to be implemented:
- supabase
- BrightData - webscraping for KimiAI images, can also webscrape for ML data for training.
- Daytona - Sandbox for AI agents to safely run, test, and develop code.
- KimiAI - ChatGPT - for main AI model .
- Nosana - distributed cloud GPUs - for AI workspace ML research, train model on the spot
- SenseNova - Also ChatGPT - for when team members want to generate image?
- TokenRouter - Call different AI model APIs - maybe team can choose diff models?

Project Desription:
We are building a multi-agent AI collaboration system for a hackathon. Here is the full architecture:

## Project Overview
A shared workspace where 3 members (A, B, C) each have their own AI agent. All agents operate on the same codebase simultaneously with conflict detection and shared context.

## Core Components to Build

### 1. Conflict Checker
- Before any agent modifies a file/function, check if it is already locked by another active agent
- If conflict detected, warn the user and let them override or wait
- Example: Member A and B both try to modify function_login() → Member B gets warned

### 2. TokenRouter
- Routes each task to the correct model
- Injects full shared context (files + lock map + action log) into every model call
- Models available:
  - KimiAI k2.6 → coding tasks, sees full file context + ownership info
  - SenseNova U1 → image/doc generation in workspace context
  - Nosana GPU → ML training and heavy compute tasks
  - Bright Data → scrapes live docs and feeds into KimiAI

### 3. Shared Context Store
- Stores all project files, a function-level lock map, agent action log, assets, and models
- Lock map format: { "function_login": "Member A", "classifier.py": "Member C" }
- Updated after every agent action
- Broadcasts updates to all members via WebSocket

### 4. Daytona Sandbox
- Runs KimiAI-generated code in an isolated environment
- Returns stdout/stderr back to the system

## Flow
1. Member submits a task
2. Conflict Checker reads context store and checks locks
3. If clear → TokenRouter picks the right model and injects context
4. Model executes task → writes to Daytona Sandbox if code execution needed
5. Shared Context Store updates and broadcasts to all members via WebSocket

## What to do
Scaffold the full project structure for this system. Use Python. Create folders, placeholder files, a README explaining the architecture, and a CLAUDE.md summarising the project so future Claude Code sessions have full context. Start with the Shared Context Store and Conflict Checker as the foundation.

Set up the project structure, a README, and scaffold the main files to get us started.