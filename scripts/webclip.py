#!/usr/bin/env python3
"""
Web Clipper - Grab articles/webpages into your data pod
Usage: python webclip.py <pod> <url> [--title "title"]
"""
import sqlite3
import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import hashlib

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def ensure_pod(pod_name: str) -> Path:
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        print(f"Error: Pod '{pod_name}' not found")
        return None
    return pod_path

def init_documents_table(pod_path: Path):
    """Ensure documents table exists."""
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        file_type TEXT,
        content TEXT,
        file_hash TEXT,
        chunks TEXT,
        embedding BLOB,
        created_at TEXT,
        updated_at TEXT
    )''')
    
    conn.commit()
    conn.close()

def get_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]

def clip_url(pod_name: str, url: str, title: str = None):
    """Clip a URL to the pod."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return False
    
    init_documents_table(pod_path)
    
    # Use web_fetch to get content
    try:
        import subprocess
        result = subprocess.run(
            ['curl', '-s', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        content = result.stdout
        
        if not content:
            print(f"Error: Could not fetch {url}")
            return False
        
        # Extract title if not provided
        if not title:
            import re
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else url
        
        # Clean HTML tags (basic)
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Truncate if too long
        if len(text) > 50000:
            text = text[:50000] + "... [truncated]"
        
        # Store in DB
        db_path = pod_path / "data.sqlite"
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        file_hash = get_url_hash(url)
        now = datetime.now().isoformat()
        
        c.execute("""INSERT INTO documents 
            (filename, file_type, content, file_hash, chunks, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title + ".html", ".html", text, file_hash, json.dumps([text]), now, now))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Clipped: {title}")
        print(f"   URL: {url}")
        print(f"   Chars: {len(text):,}")
        return True
        
    except Exception as e:
        print(f"Error clipping {url}: {e}")
        return False

def list_clips(pod_name: str):
    """List all web clips in pod."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT id, filename, file_hash, created_at FROM documents WHERE file_type = '.html' ORDER BY created_at DESC")
    rows = c.fetchall()
    
    if rows:
        print(f"Web clips in '{pod_name}':")
        for row in rows:
            print(f"  [{row[0]}] {row[1]} - {row[3][:10]}")
    else:
        print("No web clips yet.")
    
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web Clipper for Data Pods")
    sub = parser.add_subparsers(dest="cmd")
    
    clip_p = sub.add_parser("clip", help="Clip a URL to pod")
    clip_p.add_argument("pod", help="Pod name")
    clip_p.add_argument("url", help="URL to clip")
    clip_p.add_argument("--title", help="Title for the clip")
    
    list_p = sub.add_parser("list", help="List web clips")
    list_p.add_argument("pod", help="Pod name")
    
    args = parser.parse_args()
    
    PODS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.cmd == "clip":
        clip_url(args.pod, args.url, args.title)
    elif args.cmd == "list":
        list_clips(args.pod)
    else:
        parser.print_help()
