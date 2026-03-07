#!/usr/bin/env python3
"""
Data Pods v0.1 - Modular portable database management
Usage: python pod.py <command> [options]
"""

import sqlite3
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import yaml

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def ensure_dir():
    PODS_DIR.mkdir(parents=True, exist_ok=True)

def create_pod(name: str, pod_type: str = "shared"):
    """Create a new data pod."""
    ensure_dir()
    pod_path = PODS_DIR / name
    if pod_path.exists():
        print(f"Error: Pod '{name}' already exists")
        return False
    
    pod_path.mkdir(parents=True, exist_ok=True)
    
    # Create SQLite database
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Default notes table
    c.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        content TEXT,
        tags TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    
    # Default embeddings table (placeholder for vector store)
    c.execute('''CREATE TABLE IF NOT EXISTS embeddings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id INTEGER,
        chunk_text TEXT,
        embedding BLOB,
        FOREIGN KEY(note_id) REFERENCES notes(id)
    )''')
    
    conn.commit()
    conn.close()
    
    # Create metadata
    metadata = {
        "name": name,
        "type": pod_type,
        "created": datetime.now().isoformat(),
        "version": "0.1",
        "tables": ["notes", "embeddings"]
    }
    (pod_path / "metadata.json").write_text(json.dumps(metadata, indent=2))
    
    # Create manifest
    manifest = {
        "name": name,
        "type": pod_type,
        "access": "private",
        "created": metadata["created"],
        "version": "0.1"
    }
    (pod_path / "manifest.yaml").write_text(yaml.dump(manifest))
    
    print(f"✅ Created pod: {name} ({pod_type}) at {pod_path}")
    return True

def list_pods():
    """List all pods."""
    ensure_dir()
    pods = []
    for d in PODS_DIR.iterdir():
        if d.is_dir():
            meta = d / "metadata.json"
            if meta.exists():
                data = json.loads(meta.read_text())
                pods.append(f"- {d.name} ({data.get('type', 'unknown')})")
            else:
                pods.append(f"- {d.name}")
    
    if pods:
        print("📦 Available pods:")
        print("\n".join(pods))
    else:
        print("No pods found. Create one with: pod create <name>")

def add_note(pod_name: str, title: str, content: str, tags: str = ""):
    """Add a note to a pod."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return False
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    now = datetime.now().isoformat()
    c.execute("INSERT INTO notes (title, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
              (title, content, tags, now, now))
    
    note_id = c.lastrowid
    conn.commit()
    conn.close()
    
    print(f"✅ Added note to '{pod_name}' (ID: {note_id})")
    return True

def query_pod(pod_name: str, text: str = None, sql: str = None):
    """Query a pod."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return False
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    if sql:
        try:
            c.execute(sql)
            rows = c.fetchall()
            for row in rows:
                print(row)
        except Exception as e:
            print(f"SQL Error: {e}")
    elif text:
        # Simple text search
        c.execute("SELECT id, title, content, tags FROM notes WHERE content LIKE ? OR title LIKE ?", 
                  (f"%{text}%", f"%{text}%"))
        rows = c.fetchall()
        if rows:
            print(f"📄 Found {len(rows)} results for '{text}':")
            for row in rows:
                print(f"  [{row[0]}] {row[1]}: {row[2][:80]}...")
        else:
            print(f"No results for '{text}'")
    else:
        c.execute("SELECT id, title, tags, created_at FROM notes")
        rows = c.fetchall()
        if rows:
            print(f"📄 Notes in '{pod_name}':")
            for row in rows:
                print(f"  [{row[0]}] {row[1]} | {row[2]} | {row[3]}")
        else:
            print("No notes yet.")
    
    conn.close()
    return True

def export_pod(pod_name: str, output_path: str = None):
    """Export pod as zip."""
    import zipfile
    
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return False
    
    if output_path is None:
        output_path = f"{pod_name}.zip"
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in pod_path.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(pod_path)
                zipf.write(file, arcname)
    
    print(f"✅ Exported '{pod_name}' to {output_path}")
    return True

def backup_pod(pod_name: str):
    """Create timestamped backup of a pod."""
    import zipfile
    import shutil
    from datetime import datetime
    
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return False
    
    # Create backups directory
    backups_dir = PODS_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamped backup name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{pod_name}_{timestamp}.zip"
    backup_path = backups_dir / backup_name
    
    # Create zip backup
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in pod_path.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(pod_path)
                zipf.write(file, arcname)
    
    # Clean old backups (keep last 10)
    backups = sorted(backups_dir.glob(f"{pod_name}_*.zip"))
    while len(backups) > 10:
        old = backups.pop(0)
        old.unlink()
        print(f"🗑️  Removed old backup: {old.name}")
    
    print(f"✅ Backed up '{pod_name}' to {backup_path}")
    return True

def list_backups(pod_name: str = None):
    """List available backups."""
    backups_dir = PODS_DIR / "backups"
    if not backups_dir.exists():
        print("No backups found.")
        return
    
    pattern = f"{pod_name}_*.zip" if pod_name else "*.zip"
    backups = sorted(backups_dir.glob(pattern), reverse=True)
    
    if not backups:
        print(f"No backups found for '{pod_name}'." if pod_name else "No backups found.")
        return
    
    print(f"📦 Backups{' for ' + pod_name if pod_name else ''}:")
    for b in backups:
        size_kb = b.stat().st_size / 1024
        print(f"  - {b.name} ({size_kb:.1f} KB)")

def main():
    parser = argparse.ArgumentParser(description="Data Pods v0.1")
    sub = parser.add_subparsers(dest="cmd")
    
    sub.add_parser("list", help="List all pods")
    sub.add_parser("init", help="List all pods (alias)")
    
    create = sub.add_parser("create", help="Create a new pod")
    create.add_argument("name")
    create.add_argument("--type", default="shared", choices=["scholar", "health", "shared", "projects"])
    
    add = sub.add_parser("add", help="Add a note to pod")
    add.add_argument("pod")
    add.add_argument("--title", required=True)
    add.add_argument("--content", required=True)
    add.add_argument("--tags", default="")
    
    query = sub.add_parser("query", help="Query a pod")
    query.add_argument("pod")
    query.add_argument("--text", help="Search text")
    query.add_argument("--sql", help="Raw SQL")
    
    exp = sub.add_parser("export", help="Export pod as zip")
    exp.add_argument("pod")
    exp.add_argument("--output", help="Output path")
    
    backup = sub.add_parser("backup", help="Create timestamped backup")
    backup.add_argument("pod", nargs="?", help="Pod name to backup (or omit for all)")
    
    backups_list = sub.add_parser("backups", help="List available backups")
    backups_list.add_argument("pod", nargs="?", help="Filter by pod name")
    
    args = parser.parse_args()
    
    if args.cmd in ("list", "init"):
        list_pods()
    elif args.cmd == "create":
        create_pod(args.name, args.type)
    elif args.cmd == "add":
        add_note(args.pod, args.title, args.content, args.tags)
    elif args.cmd == "query":
        query_pod(args.pod, args.text, args.sql)
    elif args.cmd == "export":
        export_pod(args.pod, args.output)
    elif args.cmd == "backup":
        if args.pod:
            backup_pod(args.pod)
        else:
            # Backup all pods
            ensure_dir()
            for d in PODS_DIR.iterdir():
                if d.is_dir() and d.name != "backups" and (d / "metadata.json").exists():
                    backup_pod(d.name)
    elif args.cmd == "backups":
        list_backups(args.pod)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
