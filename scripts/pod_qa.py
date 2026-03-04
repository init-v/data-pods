#!/usr/bin/env python3
"""
Data Pod Q&A - Chat with your knowledge base
Competitive with Khoj
"""
import sqlite3
import json
import os
import argparse
import base64
from pathlib import Path
from typing import List
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import requests
import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

# ============ CORE FUNCTIONS ============

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
    for row in c.fetchall():
        try:
            emb = np.frombuffer(row[3], dtype=np.float32)
        except:
            emb = None
        yield {"id": row[0], "title": row[1], "content": row[2], "embedding": emb}

def get_all_content(conn) -> List[dict]:
    c = conn.cursor()
    c.execute("SELECT id, filename, content FROM documents")
    for row in c.fetchall():
        yield {"id": row[0], "title": row[1], "content": row[2]}

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

def build_context(docs: List[dict], max_chars: int = 4000) -> str:
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

def generate_answer(question: str, context: str, model: str = "minimax/MiniMax-M2.5") -> str:
    """Generate answer using LLM."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"error": "Set OPENROUTER_API_KEY env var"}
    
    prompt = f"""You are a helpful AI assistant. Based ONLY on the context below, answer the question.

If the answer is not in the context, say "I don't have enough information in your knowledge base to answer that."

Context:
{context}

Question: {question}

Answer:"""
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 600}
        )
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Error: {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

def ask_question(pod_name: str, question: str, top_k: int = 3, generate: bool = True) -> dict:
    conn = load_pod_db(pod_name)
    if not conn:
        return {"success": False, "error": f"Pod '{pod_name}' not found"}
    
    docs = list(get_documents_with_embeddings(conn))
    all_docs = list(get_all_content(conn))
    
    if not all_docs:
        conn.close()
        return {"success": False, "error": "No documents in pod"}
    
    results = []
    model = None
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
    
    answer = None
    if generate:
        answer = generate_answer(question, context)
    
    return {
        "success": True,
        "question": question,
        "results": [{"title": r["title"], "score": round(r.get("score", 0), 3)} for r in results],
        "context": context,
        "answer": answer
    }

# ============ WEB UI ============

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🧠 Data Pod Q&A</title>
    <style>
        *{box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0f0f0f;color:#e0e0e0;margin:0;min-height:100vh}
        .container{max-width:900px;margin:0 auto;padding:20px}
        h1{color:#fff;text-align:center;margin-bottom:30px}
        h1 span{font-size:1.5em}
        .chat{background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:20px;max-height:400px;overflow-y:auto}
        .message{padding:12px 16px;border-radius:8px;margin-bottom:12px;max-width:80%}
        .message.user{background:#2563eb;color:#fff;margin-left:auto}
        .message.assistant{background:#2a2a2a;color:#e0e0e0}
        .message .meta{font-size:0.75em;opacity:0.7;margin-top:4px}
        .input-area{display:flex;gap:10px;background:#1a1a1a;border-radius:12px;padding:15px}
        input{flex:1;background:#2a2a2a;border:1px solid #3a3a3a;border-radius:8px;padding:12px;color:#fff;font-size:16px}
        input:focus{outline:none;border-color:#2563eb}
        button{background:#2563eb;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:16px;cursor:pointer;font-weight:600}
        button:hover{background:#1d4ed8}
        button:disabled{background:#4a4a4a;cursor:not-allowed}
        .sources{background:#1a1a1a;border-radius:12px;padding:15px;margin-top:20px}
        .sources h3{color:#888;margin:0 0 10px;font-size:0.9em}
        .source-item{padding:8px 12px;background:#2a2a2a;border-radius:6px;margin-bottom:6px;font-size:0.9em}
        .loading{color:#888;font-style:italic}
        .pod-select{background:#2a2a2a;border:1px solid #3a3a3a;border-radius:8px;padding:10px;color:#fff;margin-bottom:15px}
    </style>
</head>
<body>
    <div class="container">
        <h1><span>🧠</span> Data Pod Q&A</h1>
        
        <select id="pod" class="pod-select">
            <option value="openclaw">openclaw</option>
        </select>
        
        <div class="chat" id="chat"></div>
        
        <div class="input-area">
            <input id="question" placeholder="Ask something..." autofocus>
            <button onclick="ask()" id="btn">Ask</button>
        </div>
        
        <div class="sources" id="sources" style="display:none">
            <h3>📄 Sources</h3>
            <div id="sourceList"></div>
        </div>
    </div>

    <script>
        const chat=document.getElementById('chat');
        const input=document.getElementById('question');
        const btn=document.getElementById('btn');
        
        input.addEventListener('keypress',e=>{if(e.key==='Enter')ask()});
        
        function addMessage(content,role,sources=null){
            const div=document.createElement('div');
            div.className='message '+role;
            div.innerHTML=content+(sources?'<div class="meta">'+sources.join(' | ')+'</div>':'');
            chat.appendChild(div);
            chat.scrollTop=chat.scrollHeight;
        }
        
        async function ask(){
            const q=input.value.trim();
            if(!q)return;
            input.value='';
            addMessage(q,'user');
            
            btn.disabled=true;
            addMessage('...','assistant');
            const lastMsg=chat.lastElementChild;
            
            try{
                const resp=await fetch('/ask?q='+encodeURIComponent(q)+'&pod='+document.getElementById('pod').value);
                const data=await resp.json();
                
                lastMsg.remove();
                
                if(data.answer){
                    addMessage(data.answer,'assistant',data.results?.map(r=>r.title));
                    
                    if(data.results?.length){
                        document.getElementById('sources').style.display='block';
                        document.getElementById('sourceList').innerHTML=data.results.map(r=>
                            '<div class="source-item">'+r.title+' ('+r.score+')</div>'
                        ).join('');
                    }
                }else{
                    addMessage('❌ '+data.error,'assistant');
                }
            }catch(e){
                lastMsg.innerHTML='❌ Error: '+e;
            }
            btn.disabled=false;
            input.focus();
        }
        
        // Load pods
        fetch('/pods').then(r=>r.json()).then(pods=>{
            const select=document.getElementById('pod');
            select.innerHTML=pods.map(p=>'<option value="'+p+'">'+p+'</option>').join('');
        });
    </script>
</body>
</html>'''

class QAHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        
        elif self.path == "/pods":
            pods = [d.name for d in PODS_DIR.iterdir() if d.is_dir()]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(pods).encode())
        
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
            self.wfile.write(HTML_TEMPLATE.encode())
    
    def log_message(self, format, *args):
        print(f"{self.client_address[0]} - {format % args}")

def run_server(port: int = 7868):
    server = HTTPServer(("0.0.0.0", port), QAHandler)
    print(f"🧠 Data Pod Q&A: http://localhost:{port}")
    print(f"   Set OPENROUTER_API_KEY for LLM answers")
    server.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Pod Q&A")
    parser.add_argument("pod", nargs="?", help="Pod name")
    parser.add_argument("question", nargs="*", help="Question")
    parser.add_argument("--server", action="store_true", help="Run web server")
    parser.add_argument("--port", type=int, default=7868, help="Server port")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM answer")
    args = parser.parse_args()
    
    if args.server:
        run_server(args.port)
    elif args.pod and args.question:
        q = " ".join(args.question)
        result = ask_question(args.pod, q, generate=not args.no_llm)
        print(json.dumps(result, indent=2))
    elif args.pod:
        print("🧠 Data Pod Q&A Interactive Mode (type 'quit' to exit)")
        while True:
            q = input("Q: ").strip()
            if q.lower() in ["quit", "exit"]:
                break
            if not q:
                continue
            result = ask_question(args.pod, q)
            if result.get("success"):
                print("\n📄 Results:")
                for r in result.get("results", []):
                    print(f"  • {r['title']} ({r['score']})")
                if result.get("answer"):
                    print(f"\n💬 Answer:\n{result['answer']}")
            else:
                print(f"❌ {result.get('error')}")
            print()
    else:
        parser.print_help()
