#!/usr/bin/env python3
"""
Data Pod Q&A - Ask questions to your knowledge base
"""
import sqlite3
import json
import os
import argparse
import base64
from pathlib import Path
from typing import List
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_pod_db(pod_name: str):
    db_path = PODS_DIR / pod_name / "data.sqlite"
    if not db_path.exists():
        return None
    return sqlite3.connect(str(db_path))

def get_documents_with_embeddings(conn) -> List[dict]:
    c = conn.cursor()
    c.execute("SELECT id, filename, content, embedding FROM documents WHERE embedding IS NOT NULL")
    rows = c.fetchall()
    
    docs = []
    for row in rows:
        try:
            emb = np.frombuffer(row[3], dtype=np.float32)
        except:
            emb = None
        docs.append({"id": row[0], "title": row[1], "content": row[2], "embedding": emb})
    return docs

def get_all_content(conn) -> List[dict]:
    c = conn.cursor()
    c.execute("SELECT id, filename, content FROM documents")
    return [{"id": r[0], "title": r[1], "content": r[2]} for r in c.fetchall()]

def search_by_similarity(question: str, docs: List[dict], model, top_k: int = 3) -> List[dict]:
    question_emb = model.encode(question, normalize_embeddings=True)
    results = []
    for doc in docs:
        if doc.get("embedding") is not None:
            sim = cosine_similarity(question_emb, doc["embedding"])
            results.append({**doc, "score": float(sim)})
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:top_k]

def keyword_search(question: str, docs: List[dict], top_k: int = 3) -> List[dict]:
    keywords = question.lower().split()
    results = []
    for doc in docs:
        score = sum(1 for kw in keywords if kw in doc["content"].lower())
        if score > 0:
            results.append({**doc, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

def build_context(docs: List[dict], max_chars: int = 3000) -> str:
    context = ""
    for doc in docs:
        content = doc["content"]
        if len(context) + len(content) > max_chars:
            remaining = max_chars - len(context)
            if remaining > 100:
                context += f"\n\n## {doc['title']}\n"
                context += content[:remaining] + "..."
        else:
            context += f"\n\n## {doc['title']}\n"
            context += content
    return context.strip()

def ask_question(pod_name: str, question: str, top_k: int = 3) -> dict:
    conn = load_pod_db(pod_name)
    if not conn:
        return {"success": False, "error": f"Pod '{pod_name}' not found"}
    
    docs = get_documents_with_embeddings(conn)
    all_docs = get_all_content(conn)
    
    if not all_docs:
        conn.close()
        return {"success": False, "error": "No documents in pod"}
    
    results = []
    if docs and EMBEDDINGS_AVAILABLE:
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            results = search_by_similarity(question, docs, model, top_k)
        except Exception as e:
            print(f"Falling back to keywords: {e}")
    
    if not results:
        results = keyword_search(question, all_docs, top_k)
    
    if not results:
        return {"success": False, "error": "No relevant documents found"}
    
    context = build_context(results)
    conn.close()
    
    return {
        "success": True,
        "question": question,
        "results": [{"title": r["title"], "score": r.get("score", 0)} for r in results],
        "context": context
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Pod Q&A")
    parser.add_argument("pod", help="Pod name")
    parser.add_argument("question", nargs="*", help="Question")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    
    q = " ".join(args.question) if args.question else None
    
    if not q:
        print("🧠 Data Pod Q&A")
        while True:
            q = input("Q: ").strip()
            if q.lower() in ["quit", "exit"]:
                break
            result = ask_question(args.pod, q, args.top_k)
            if result.get("success"):
                print("\n📄 Results:")
                for i, r in enumerate(result["results"], 1):
                    print(f"  {i}. {r['title']} ({r['score']:.2f})")
                print(f"\n📝 Context:\n{result['context'][:400]}...")
            else:
                print(f"❌ {result.get('error')}")
            print()
    else:
        print(json.dumps(ask_question(args.pod, q, args.top_k), indent=2))

def generate_answer(question: str, context: str, api_key: str = None) -> str:
    """Generate answer using LLM with context."""
    import requests
    
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY")
    
    if not api_key:
        return "Set OPENROUTER_API_KEY to generate answers"
    
    prompt = f"""You are a helpful AI assistant. Based only on the context below, answer the question.

If the answer is not in the context, say "I don't have enough information to answer that."

Context:
{context}

Question: {question}

Answer:"""
    
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "minimax/MiniMax-M2.5",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
    )
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        return f"Error: {response.text}"

def run_server(port: int = 7868):
    """Run Q&A as HTTP server."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse
    
    class QAHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            elif self.path.startswith("/ask?"):
                params = urllib.parse.parse_qs(self.path.split("?")[1])
                q = params.get("q", [""])[0]
                pod = params.get("pod", ["openclaw"])[0]
                
                result = ask_question(pod, q)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                html = '''<!DOCTYPE html>
<html><head><title>Data Pod Q&A</title>
<style>
body{font-family:system-ui;max-width:800px;margin:50px auto;padding:20px}
input,button{padding:12px;font-size:16px;border-radius:8px;border:1px solid #ccc}
input{width:70%}button{width:25%;background:#007bff;color:white;border:none;cursor:pointer}
#results{margin-top:20px;padding:20px;background:#f5f5f5;border-radius:8px}
</style></head>
<body>
<h1>🧠 Data Pod Q&A</h1>
<input id="q" placeholder="Ask a question...">
<button onclick="ask()">Ask</button>
<div id="results"></div>
<script>
function ask(){
  const q=document.getElementById("q").value;
  fetch("/ask?q="+encodeURIComponent(q)).then(r=>r.json()).then(d=>{
    let html="<h3>Results:</h3>";
    if(d.results){d.results.forEach(r=>html+="<p><b>"+r.title+"</b> ("+r.score.toFixed(2)+")</p>");}
    if(d.context){html+="<pre>"+d.context.substring(0,1000)+"...</pre>";}
    document.getElementById("results").innerHTML=html;
  });
}
</script></body></html>'''
                self.wfile.write(html.encode())
        
        def log_message(self, format, *args):
            print(f"{self.client_address[0]} - {format % args}")
    
    server = HTTPServer(("0.0.0.0", port), QAHandler)
    print(f"🧠 Data Pod Q&A Server running on http://localhost:{port}")
    print(f"   GET /ask?q=<question>&pod=<podname>")
    server.serve_forever()

if __name__ == "__main__" and "--server" in __import__("sys").argv:
    run_server()
