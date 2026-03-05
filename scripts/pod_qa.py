#!/usr/bin/env python3
"""
Data Pod Q&A - Chat with your knowledge base
Competitive with Khoj and NotebookLM
"""
import sqlite3
import json
import os
import argparse
import base64
import hashlib
from pathlib import Path
from typing import List
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
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
    conn = sqlite3.connect(str(db_path))
    return conn

def init_pod(pod_name: str):
    """Initialize a pod if it doesn't exist."""
    pod_path = PODS_DIR / pod_name
    pod_path.mkdir(parents=True, exist_ok=True)
    db_path = pod_path / "data.sqlite"
    
    conn = sqlite3.connect(str(db_path))
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
    return True

def get_file_hash(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()

def add_document(pod_name: str, filename: str, content: str) -> dict:
    """Add a document to the pod."""
    conn = load_pod_db(pod_name)
    if not conn:
        init_pod(pod_name)
        conn = load_pod_db(pod_name)
    
    c = conn.cursor()
    file_hash = get_file_hash(content)
    
    # Ensure table exists (for older pods)
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
    
    # Check if already exists
    c.execute("SELECT id FROM documents WHERE file_hash = ?", (file_hash,))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": "Document already exists"}
    
    from datetime import datetime
    c.execute("""INSERT INTO documents (filename, file_type, content, file_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
              (filename, Path(filename).suffix, content, file_hash, 
               datetime.now().isoformat(), datetime.now().isoformat()))
    
    doc_id = c.lastrowid
    conn.commit()
    
    # Generate embedding if available
    if EMBEDDINGS_AVAILABLE:
        try:
            model = SentenceTransformer("all-MiniLM-L6-v2")
            emb = model.encode(content[:5000], normalize_embeddings=True)
            c.execute("UPDATE documents SET embedding = ? WHERE id = ?", 
                      (emb.tobytes(), doc_id))
            conn.commit()
        except Exception as e:
            print(f"Embedding failed: {e}")
    
    conn.close()
    return {"success": True, "doc_id": doc_id, "filename": filename}

def list_sources(pod_name: str) -> List[dict]:
    """List all sources in a pod."""
    conn = load_pod_db(pod_name)
    if not conn:
        return []
    
    c = conn.cursor()
    # Ensure table exists
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
    
    c.execute("""SELECT id, filename, file_type, LENGTH(content) as size, created_at 
                FROM documents ORDER BY created_at DESC""")
    
    sources = []
    for row in c.fetchall():
        sources.append({
            "id": row[0],
            "filename": row[1],
            "file_type": row[2],
            "size_chars": row[3],
            "created_at": row[4]
        })
    
    conn.close()
    return sources

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

def generate_answer(question: str, context: str, model: str = "openai-codex/gpt-5.2-codex") -> str:
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
        .container{max-width:1000px;margin:0 auto;padding:20px}
        h1{color:#fff;text-align:center;margin-bottom:20px}
        h1 span{font-size:1.5em}
        
        .tabs{display:flex;gap:5px;margin-bottom:20px;background:#1a1a1a;padding:5px;border-radius:10px}
        .tab{padding:10px 20px;background:transparent;color:#888;border:none;border-radius:8px;cursor:pointer;font-size:14px}
        .tab.active{background:#2563eb;color:#fff}
        
        .panel{display:none}
        .panel.active{display:block}
        
        /* Sources Panel */
        .sources-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:15px}
        .source-card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;padding:15px}
        .source-card .name{font-weight:600;color:#fff;margin-bottom:5px}
        .source-card .meta{font-size:12px;color:#666}
        .source-card .size{font-size:12px;color:#888;margin-top:5px}
        
        /* Upload Panel */
        .upload-zone{
            border:2px dashed #3a3a3a;border-radius:12px;padding:40px;text-align:center;
            background:#1a1a1a;transition:all 0.2s;cursor:pointer;margin-top:15px
        }
        .upload-zone:hover,.upload-zone.dragover{border-color:#2563eb;background:#1a1a2a}
        .upload-zone .icon{font-size:48px;margin-bottom:15px}
        .upload-zone .text{color:#888}
        .upload-zone .hint{font-size:12px;color:#666;margin-top:10px}
        
        /* Chat Panel */
        .pod-select{background:#2a2a2a;border:1px solid #3a3a3a;border-radius:8px;padding:10px;color:#fff;margin-bottom:15px;width:200px}
        .chat{background:#1a1a1a;border-radius:12px;padding:20px;margin-bottom:20px;max-height:450px;overflow-y:auto}
        .message{padding:12px 16px;border-radius:8px;margin-bottom:12px;max-width:80%;white-space:pre-wrap}
        .message.user{background:#2563eb;color:#fff;margin-left:auto}
        .message.assistant{background:#2a2a2a;color:#e0e0e0}
        .message .meta{font-size:0.75em;opacity:0.7;margin-top:4px}
        
        .input-area{display:flex;gap:10px;background:#1a1a1a;border-radius:12px;padding:15px}
        input{flex:1;background:#2a2a2a;border:1px solid #3a3a3a;border-radius:8px;padding:12px;color:#fff;font-size:16px}
        input:focus{outline:none;border-color:#2563eb}
        button{background:#2563eb;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:16px;cursor:pointer;font-weight:600}
        button:hover{background:#1d4ed8}
        button:disabled{background:#4a4a4a;cursor:not-allowed}
        
        .sources-list{background:#1a1a1a;border-radius:12px;padding:15px;margin-top:20px}
        .sources-list h3{color:#888;margin:0 0 10px;font-size:0.9em}
        .source-item{padding:8px 12px;background:#2a2a2a;border-radius:6px;margin-bottom:6px;font-size:0.9em;display:flex;justify-content:space-between}
        
        .upload-item{background:#2a2a2a;border-radius:8px;padding:10px 12px;margin-bottom:8px}
        .upload-row{display:flex;justify-content:space-between;align-items:center;font-size:0.9em}
        .progress{height:6px;background:#333;border-radius:999px;overflow:hidden;margin-top:8px}
        .progress-bar{height:100%;width:0;background:#22c55e;transition:width .2s}
        .progress-text{font-size:12px;color:#888;margin-left:8px}
        
        .loading{color:#888;font-style:italic}
        .toast{position:fixed;bottom:20px;right:20px;background:#22c55e;color:#fff;padding:12px 20px;border-radius:8px;opacity:0;transition:opacity 0.3s}
        .toast.show{opacity:1}
    </style>
</head>
<body>
    <div class="container">
        <h1><span>🧠</span> Data Pod Q&A</h1>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('chat')">💬 Chat</button>
            <button class="tab" onclick="showTab('sources')">📚 Sources</button>
            <button class="tab" onclick="showTab('upload')">📥 Upload</button>
        </div>
        
        <!-- Chat Panel -->
        <div class="panel active" id="panel-chat">
            <select id="pod" class="pod-select" onchange="loadSources()"></select>
            
            <div class="chat" id="chat"></div>
            
            <div class="input-area">
                <input id="question" placeholder="Ask something..." autofocus>
                <button onclick="ask()" id="btn">Ask</button>
            </div>
            
            <div class="sources-list" id="chatSources" style="display:none">
                <h3>📄 Sources</h3>
                <div id="sourceList"></div>
            </div>
        </div>
        
        <!-- Sources Panel -->
        <div class="panel" id="panel-sources">
            <select id="pod-sources" class="pod-select" onchange="loadSources()"></select>
            <div class="sources-grid" id="sourcesGrid"></div>
        </div>
        
        <!-- Upload Panel -->
        <div class="panel" id="panel-upload">
            <select id="pod-upload" class="pod-select" onchange=""></select>
            
            <div class="upload-zone" id="dropZone">
                <div class="icon">📄</div>
                <div class="text">Drag & drop files here</div>
                <div class="text">or click to browse</div>
                <div class="hint">.txt, .md, .pdf, .html supported</div>
                <input type="file" id="fileInput" multiple style="display:none">
            </div>
            
            <div id="uploadList" style="margin-top:20px"></div>
        </div>
    </div>
    
    <div class="toast" id="toast"></div>

    <script>
        let currentPod = 'openclaw';
        
        function showTab(tab){
            document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('panel-'+tab).classList.add('active');
        }
        
        function showToast(msg){
            const t=document.getElementById('toast');
            t.textContent=msg;
            t.classList.add('show');
            setTimeout(()=>t.classList.remove('show'),3000);
        }
        
        async function loadPods(){
            const resp=await fetch('/pods');
            const pods=await resp.json();
            ['pod','pod-sources','pod-upload'].forEach(id=>{
                const sel=document.getElementById(id);
                sel.innerHTML=pods.map(p=>'<option value="'+p+'">'+p+'</option>').join('');
            });
            loadSources();
        }
        
        async function loadSources(){
            currentPod=document.getElementById('pod').value;
            const resp=await fetch('/sources?pod='+currentPod);
            const sources=await resp.json();
            
            // Chat sources
            document.getElementById('sourceList').innerHTML=sources.map(s=>
                '<div class="source-item"><span>'+s.filename+'</span><span style="color:#666">'+s.size_chars+' chars</span></div>'
            ).join('');
            
            // Sources grid
            document.getElementById('sourcesGrid').innerHTML=sources.map(s=>
                '<div class="source-card"><div class="name">'+s.filename+'</div>'+
                '<div class="meta">'+s.file_type+'</div><div class="size">'+s.size_chars+' chars</div></div>'
            ).join('') || '<p style="color:#666">No sources yet</p>';
        }
        
        // Chat
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
                const resp=await fetch('/ask?q='+encodeURIComponent(q)+'&pod='+currentPod);
                const data=await resp.json();
                lastMsg.remove();
                
                if(data.answer){
                    addMessage(data.answer,'assistant',data.results?.map(r=>r.title));
                    if(data.results?.length){
                        document.getElementById('chatSources').style.display='block';
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
        
        // Upload
        const dropZone=document.getElementById('dropZone');
        const fileInput=document.getElementById('fileInput');
        
        dropZone.onclick=()=>fileInput.click();
        dropZone.ondragover=e=>{e.preventDefault();dropZone.classList.add('dragover')};
        dropZone.ondragleave=()=>dropZone.classList.remove('dragover');
        dropZone.ondrop=e=>{
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        };
        fileInput.onchange=()=>handleFiles(fileInput.files);
        
        async function handleFiles(files){
            const pod=document.getElementById('pod-upload').value;
            const list=document.getElementById('uploadList');
            
            for(const file of files){
                const item=document.createElement('div');
                item.className='upload-item';
                item.innerHTML=`
                  <div class="upload-row">
                    <span>${file.name}</span>
                    <span class="progress-text">0%</span>
                  </div>
                  <div class="progress"><div class="progress-bar"></div></div>
                `;
                list.prepend(item);
                
                const progressText=item.querySelector('.progress-text');
                const progressBar=item.querySelector('.progress-bar');
                
                // Read file with progress
                const content=await readFileWithProgress(file, p=>{
                    progressText.textContent=`${p}% (reading)`;
                    progressBar.style.width=`${p}%`;
                });
                
                // Upload with progress
                await uploadWithProgress({pod, filename:file.name, content}, p=>{
                    progressText.textContent=`${p}% (uploading)`;
                    progressBar.style.width=`${p}%`;
                }).then(data=>{
                    if(data.success){
                        progressText.textContent='✓ Done';
                        progressBar.style.width='100%';
                        showToast('✓ Added '+file.name);
                        loadSources();
                    }else{
                        progressText.textContent='✕ Failed';
                        showToast('❌ '+data.error);
                    }
                }).catch(err=>{
                    progressText.textContent='✕ Failed';
                    showToast('❌ '+err);
                });
            }
        }

        function readFileWithProgress(file, onProgress){
            return new Promise((resolve, reject)=>{
                const reader=new FileReader();
                reader.onprogress=e=>{
                    if(e.lengthComputable){
                        const p=Math.round((e.loaded/e.total)*100);
                        onProgress(p);
                    }
                };
                reader.onload=()=>resolve(reader.result);
                reader.onerror=()=>reject('Read error');
                reader.readAsText(file);
            });
        }

        function uploadWithProgress(payload, onProgress){
            return new Promise((resolve, reject)=>{
                const xhr=new XMLHttpRequest();
                xhr.open('POST','/add');
                xhr.setRequestHeader('Content-Type','application/json');
                xhr.upload.onprogress=e=>{
                    if(e.lengthComputable){
                        const p=Math.round((e.loaded/e.total)*100);
                        onProgress(p);
                    }
                };
                xhr.onload=()=>{
                    if(xhr.status===200){
                        resolve(JSON.parse(xhr.responseText));
                    }else{
                        reject('Upload failed');
                    }
                };
                xhr.onerror=()=>reject('Network error');
                xhr.send(JSON.stringify(payload));
            });
        }
        
        loadPods();
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
        
        elif self.path.startswith("/sources?"):
            params = urllib.parse.parse_qs(self.path.split("?")[1])
            pod = params.get("pod", ["openclaw"])[0]
            sources = list_sources(pod)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(sources).encode())
        
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
    
    def do_POST(self):
        if self.path == "/add":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            
            result = add_document(data.get("pod", "openclaw"), data.get("filename"), data.get("content"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
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
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM")
    args = parser.parse_args()
    
    if args.server:
        run_server(args.port)
    elif args.pod and args.question:
        q = " ".join(args.question)
        result = ask_question(args.pod, q, generate=not args.no_llm)
        print(json.dumps(result, indent=2))
    elif args.pod:
        print("🧠 Data Pod Q&A")
        while True:
            q = input("Q: ").strip()
            if q.lower() in ["quit", "exit"]:
                break
            if q:
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
