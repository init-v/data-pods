---
name: data-pods
description: Create and manage modular portable database pods (SQLite + metadata + embeddings). Use to build personal knowledge bases, research archives, and consent-scoped data stores.
---

# Data Pods

## Overview
Create portable, consent-scoped database pods that can be zipped, moved, and queried via natural language.

## Core Features
- **Create pod:** Initialize a new pod with SQLite + metadata
- **Add data:** Insert records, notes, embeddings
- **Query:** Search via natural language or SQL
- **Export:** Zip pod for portability
- **Import:** Load existing pod

## Pod Structure
```
pod-name/
├── data.sqlite       # Main database
├── metadata.json     # Tags, schema, created date
├── embeddings/      # Vector store (optional)
└── manifest.yaml    # Access rules
```

## Usage
```
pod create <name> [--type scholar|health|shared]
pod add <pod> --table <table> --data <json>
pod query <pod> --text "search query"
pod export <pod> --output <path>
pod list
```

## Data Types
- **scholar:** Research papers, notes, embeddings
- **health:** Wearable data, biometrics (consent-only)
- **shared:** Family/group data with permissions
- **projects:** Workspace-specific knowledge

## Why Modular
- Users own their data
- No vendor lock-in
- Agents work across pods
- GDPR-friendly by design
