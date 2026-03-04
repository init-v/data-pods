#!/usr/bin/env python3
"""
Notion Importer - Import pages from Notion into your data pod
Usage: python notion_import.py <pod> [--token NOTION_TOKEN] [--page-id PAGE_ID]

Requires: pip install notion-client
Set NOTION_TOKEN environment variable or pass via --token
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

def get_notion_content(page_id: str, token: str) -> dict:
    """Fetch page content from Notion API."""
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        # Get page metadata
        page_resp = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers
        )
        
        if page_resp.status_code != 200:
            print(f"Error fetching page: {page_resp.status_code}")
            return None
        
        page_data = page_resp.json()
        
        # Get title
        title = "Untitled"
        if "properties" in page_data:
            for prop in page_data["properties"].values():
                if prop.get("type") == "title":
                    title_obj = prop.get("title", [])
                    if title_obj:
                        title = title_obj[0].get("plain_text", "Untitled")
                    break
        
        # Get page content (blocks)
        blocks_resp = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers
        )
        
        content = []
        if blocks_resp.status_code == 200:
            blocks = blocks_resp.json().get("results", [])
            for block in blocks:
                block_type = block.get("type")
                if block_type == "paragraph":
                    text = block.get("paragraph", {}).get("rich_text", [])
                    content.append("".join([t.get("plain_text", "") for t in text]))
                elif block_type == "heading_1":
                    text = block.get("heading_1", {}).get("rich_text", [])
                    content.append("# " + "".join([t.get("plain_text", "") for t in text]))
                elif block_type == "heading_2":
                    text = block.get("heading_2", {}).get("rich_text", [])
                    content.append("## " + "".join([t.get("plain_text", "") for t in text]))
                elif block_type == "heading_3":
                    text = block.get("heading_3", {}).get("rich_text", [])
                    content.append("### " + "".join([t.get("plain_text", "") for t in text]))
                elif block_type == "bulleted_list_item":
                    text = block.get("bulleted_list_item", {}).get("rich_text", [])
                    content.append("- " + "".join([t.get("plain_text", "") for t in text]))
                elif block_type == "numbered_list_item":
                    text = block.get("numbered_list_item", {}).get("rich_text", [])
                    content.append("1. " + "".join([t.get("plain_text", "") for t in text]))
        
        return {
            "title": title,
            "content": "\n\n".join(content),
            "url": page_data.get("url", "")
        }
        
    except ImportError:
        print("Error: requests library needed")
        print("Install: pip install requests")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def import_from_notion(pod_name: str, page_id: str, token: str = None):
    """Import a Notion page into pod."""
    pod_path = ensure_pod(pod_name)
    if not pod_path:
        return False
    
    # Get token from env if not provided
    if not token:
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            print("Error: Notion token required")
            print("Set NOTION_TOKEN env var or pass --token")
            return False
    
    init_documents_table(pod_path)
    
    # Fetch content
    print(f"Fetching Notion page: {page_id}")
    data = get_notion_content(page_id, token)
    
    if not data:
        return False
    
    # Store in DB
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    file_hash = hashlib.sha256(page_id.encode()).hexdigest()[:16]
    now = datetime.now().isoformat()
    
    c.execute("""INSERT INTO documents 
        (filename, file_type, content, file_hash, chunks, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (data["title"] + ".md", ".md", data["content"], file_hash, 
         json.dumps(data["content"].split("\n\n")), now, now))
    
    conn.commit()
    conn.close()
    
    print(f"✅ Imported: {data['title']}")
    print(f"   Chars: {len(data['content']):,}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notion Importer for Data Pods")
    sub = parser.add_subparsers(dest="cmd")
    
    import_p = sub.add_parser("import", help="Import Notion page to pod")
    import_p.add_argument("pod", help="Pod name")
    import_p.add_argument("--page-id", required=True, help="Notion page ID")
    import_p.add_argument("--token", help="Notion API token")
    
    args = parser.parse_args()
    
    PODS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.cmd == "import":
        import_from_notion(args.pod, args.page_id, args.token)
    else:
        parser.print_help()
