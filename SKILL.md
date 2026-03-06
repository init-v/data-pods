---
name: data-pods
description: Create and manage modular portable database pods (SQLite + metadata + embeddings). Includes document ingestion with embeddings for semantic search. Full automation - just ask.
---

# Data Pods

## Overview
Create and manage portable, consent-scoped database pods. Handles document ingestion with embeddings and semantic search.

## Architecture
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Ingestion  │ ──► │   DB Pods   │ ──► │  Generation │ ──► │   Export    │
│  (ingest)   │     │  (storage)  │     │   (query)   │     │ (md/khoj/vpod)│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

## What's New (v0.4)
- **Web Clipping**: Grab articles from URLs directly
- **Notion Import**: Import pages from Notion
- **PDF Support**: Now works with PyPDF2
- **Obsidian Plugin**: Connect pods from Obsidian
- **API Server**: Expose pods via REST API
- **Q&A Server**: Chat with your pods via HTTP API
- **PodSync**: Sync pods across devices

## Triggers
- "create a pod" / "new pod"
- "list my pods" / "what pods do I have"
- "add to pod" / "add note" / "add content"
- "query pod" / "search pod"
- "ingest documents" / "add files"
- "semantic search" / "find相关内容"
- "export pod" / "pack pod"
- "pod stats" / "pod statistics"
- "export to markdown" / "export for chatgpt"
- "export to khoj"
- "clip url" / "save webpage" / "web clip"
- "import from notion" / "notion page"

## Core Features

### 1. Create Pod
When user asks to create a pod:
1. Ask for pod name and type (scholar/health/shared/projects)
2. Run: `python3 .../scripts/pod.py create <name> --type <type>`
3. Confirm creation

### 2. Add Content (Manual)
When user asks to add content:
1. Ask for pod name, title, content, tags
2. Run: `python3 .../scripts/pod.py add <pod> --title "<title>" --content "<content>" --tags "<tags>"`
3. Confirm

### 3. Ingest Documents (Automated)
When user wants to ingest files:
1. Ask for pod name and folder path
2. Run: `python3 .../scripts/ingest.py ingest <pod> <folder>`
3. Supports: PDF, TXT, MD, DOCX, PNG, JPG
4. Auto-embeds text (if sentence-transformers installed)

### 4. Semantic Search
When user wants to search:
1. Ask for pod name and query
2. Run: `python3 .../scripts/ingest.py search <pod> "<query>"`
3. Returns ranked results with citations

### 5. Query (Basic)
When user asks to search notes:
1. Run: `python3 .../scripts/pod.py query <pod> --text "<query>"`

### 6. Export Pods
When user asks to export a pod:
1. Ask for pod name and format (markdown/khoj)
2. For Markdown (LLM-ready): `python3 .../scripts/export_utils.py export-md <pod> [--output path]`
3. For Khoj format: `python3 .../scripts/export_utils.py export-khoj <pod> [--output path]`
4. Returns portable .md file or Khoj-compatible JSON

### 7. Pod Statistics
When user asks for pod stats:
1. Run: `python3 .../scripts/export_utils.py stats <pod>`
2. Shows document count, total text, embeddings, file types

### 8. Web Clipping
When user wants to save a webpage:
1. Ask for pod name and URL
2. Run: `python3 .../scripts/webclip.py clip <pod> <url> [--title "title"]`
3. Saves webpage content to pod

### 9. Notion Import
When user wants to import from Notion:
1. Ask for pod name and Notion page ID
2. Set NOTION_TOKEN env var or pass --token
3. Run: `python3 .../scripts/notion_import.py import <pod> --page-id <id> [--token <token>]`

### 10. Obsidian Plugin
When user wants to use pods in Obsidian:
1. Copy `obsidian-plugin/` folder to your Obsidian plugins folder
2. Or run API server: `python3 .../scripts/pod_qa.py server`
3. Configure pods path in Obsidian settings

### 11. Q&A Server (Chat with your Pods)
When user wants to chat with their knowledge base:
1. Run: `python3 .../scripts/pod_qa.py server [--port 8080]`
2. Access via REST API or use the built-in UI
3. Supports conversational queries over your pod data

### 12. PodSync (Cross-device Sync)
When user wants to sync pods across devices:
1. Run: `python3 .../scripts/podsync.py list` - List pods
2. Run: `python3 .../scripts/podsync.py sync <pod>` - Sync a pod
3. Run: `python3 .../scripts/podsync.py export <pod> --output <file>` - Export for sharing

```bash
pip install PyPDF2 python-docx pillow pytesseract sentence-transformers
```

## Storage Location
`~/.openclaw/data-pods/`

## Key Commands
```bash
# Create pod
python3 .../scripts/pod.py create research --type scholar

# Add note
python3 .../scripts/pod.py add research --title "..." --content "..." --tags "..."

# Ingest folder
python3 .../scripts/ingest.py ingest research ./documents/

# Semantic search
python3 .../scripts/ingest.py search research "transformers"

# List documents
python3 .../scripts/ingest.py list research

# Query notes
python3 .../scripts/pod.py query research --text "..."

# Export to Markdown (for ChatGPT/Claude)
python3 .../scripts/export_utils.py export-md research

# Export to Khoj format
python3 .../scripts/export_utils.py export-khoj research

# Pod statistics
python3 .../scripts/export_utils.py stats research

# Web clipping
python3 .../scripts/webclip.py clip research https://example.com/article

# Notion import
python3 .../scripts/notion_import.py import research --page-id <notion-id> --token <token>

# Q&A Server (chat with your pods)
python3 .../scripts/pod_qa.py server --port 8080

# PodSync - sync across devices
python3 .../scripts/podsync.py list
python3 .../scripts/podsync.py sync research
python3 .../scripts/podsync.py export research --output research.zip
```

## Notes
- Ingestion auto-chunks large documents
- Embeddings enable semantic search
- File hash prevents duplicate ingestion
- All data stored locally in SQLite
