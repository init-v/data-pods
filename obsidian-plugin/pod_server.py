#!/usr/bin/env python3
"""
Data Pods API Server - For Obsidian plugin connection
Run this to expose your pods via REST API
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sqlite3
from pathlib import Path
import urllib.parse

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

class PodsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == '/pods':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            pods = []
            if PODS_DIR.exists():
                for p in PODS_DIR.iterdir():
                    if p.is_dir():
                        pods.append(p.name)
            
            self.wfile.write(json.dumps(pods).encode())
            
        elif path.startswith('/search/'):
            pod_name = path.split('/')[-1]
            query = urllib.parse.parse_qs(parsed.query).get('q', [''])[0]
            
            results = search_pod(pod_name, query)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(results).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[Pods API] {format % args}")

def search_pod(pod_name, query):
    pod_path = PODS_DIR / pod_name / "data.sqlite"
    if not pod_path.exists():
        return []
    
    conn = sqlite3.connect(pod_path)
    c = conn.cursor()
    
    # Simple text search
    c.execute("SELECT filename, content FROM documents WHERE content LIKE ? LIMIT 10", 
              (f'%{query}%',))
    
    results = []
    for filename, content in c.fetchall():
        results.append({
            'file': filename,
            'preview': content[:500] if content else ''
        })
    
    conn.close()
    return results

def run_server(port=8765):
    server = HTTPServer(('', port), PodsHandler)
    print(f"Data Pods API running on http://localhost:{port}")
    print(f"Endpoints:")
    print(f"  GET /pods - List all pods")
    print(f"  GET /search/<pod>?q=<query> - Search a pod")
    server.serve_forever()

if __name__ == '__main__':
    run_server()
