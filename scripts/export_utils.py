#!/usr/bin/env python3
"""Export utilities for Data Pods"""
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def ensure_pod(pod_name: str) -> Path:
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return None
    return pod_path

def get_stats(pod_name: str):
    """Get pod statistics."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return
    
    db_path = pod_path / "data.sqlite"
    if not db_path.exists():
        print(f"Pod '{pod_name}' has no data")
        return
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*), SUM(LENGTH(content)) FROM documents")
    doc_count, total_chars = c.fetchone()
    
    c.execute("SELECT file_type, COUNT(*) FROM documents GROUP BY file_type")
    types = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL")
    embedded = c.fetchone()[0]
    
    print(f"\n📊 Pod Stats: {pod_name}")
    print("=" * 40)
    print(f"Documents: {doc_count}")
    print(f"Total text: {total_chars or 0:,} chars")
    print(f"With embeddings: {embedded}")
    print(f"\nFile types:")
    for ftype, count in types:
        print(f"  {ftype}: {count}")
    
    conn.close()

def export_to_khoj(pod_name: str, output_path: str = None):
    """Export pod to Khoj-compatible JSON format."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return False
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT filename, content, chunks, created_at FROM documents")
    rows = c.fetchall()
    
    if not rows:
        print("No documents to export")
        return False
    
    khoj_data = {
        "version": "1.0",
        "pod": pod_name,
        "exported_at": datetime.now().isoformat(),
        "documents": []
    }
    
    for filename, content, chunks_json, created_at in rows:
        khoj_data["documents"].append({
            "entry": content[:5000] if content else "",
            "file": filename,
            "created": created_at,
            "word_count": len(content.split()) if content else 0
        })
    
    if not output_path:
        output_path = str(PODS_DIR / pod_name / "khoj-export.json")
    
    with open(output_path, 'w') as f:
        json.dump(khoj_data, f, indent=2)
    
    print(f"Exported {len(rows)} documents to {output_path}")
    conn.close()
    return True

def export_to_markdown(pod_name: str, output_path: str = None):
    """Export pod as markdown (for ChatGPT, Claude, etc)."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return False
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT filename, content, created_at FROM documents ORDER BY created_at DESC")
    rows = c.fetchall()
    
    if not rows:
        print("No documents to export")
        return False
    
    if not output_path:
        output_path = str(PODS_DIR / pod_name / f"{pod_name}-export.md")
    
    with open(output_path, 'w') as f:
        f.write(f"# {pod_name}\n\n")
        f.write(f"*Exported: {datetime.now().strftime('%Y-%m-%d')}*\n\n")
        f.write("---\n\n")
        
        for filename, content, created_at in rows:
            f.write(f"## {filename}\n\n")
            f.write(f"*Created: {created_at}*\n\n")
            f.write(content)
            f.write("\n\n---\n\n")
    
    print(f"Exported {len(rows)} documents to {output_path}")
    print(f"Size: {os.path.getsize(output_path) / 1024:.1f} KB")
    
    conn.close()
    return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export Data Pods")
    sub = parser.add_subparsers(dest="cmd")
    
    stats_p = sub.add_parser("stats", help="Show pod statistics")
    stats_p.add_argument("pod", help="Pod name")
    
    export_mk_p = sub.add_parser("export-md", help="Export to Markdown")
    export_mk_p.add_argument("pod", help="Pod name")
    export_mk_p.add_argument("--output", help="Output file path")
    
    export_khoj_p = sub.add_parser("export-khoj", help="Export to Khoj format")
    export_khoj_p.add_argument("pod", help="Pod name")
    export_khoj_p.add_argument("--output", help="Output file path")
    
    args = parser.parse_args()
    
    if args.cmd == "stats":
        get_stats(args.pod)
    elif args.cmd == "export-md":
        export_to_markdown(args.pod, args.output)
    elif args.cmd == "export-khoj":
        export_to_khoj(args.pod, args.output)
    else:
        parser.print_help()
