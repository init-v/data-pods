#!/usr/bin/env python3
"""
Data Pod Portable - Compress, Encrypt, Transport
"""
import sqlite3
import json
import gzip
import zipfile
import os
import shutil
import hashlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse

try:
    from cryptography.fernet import Fernet
    ENCRYPTION = True
except ImportError:
    ENCRYPTION = False

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def compress_pod(pod_name: str, output: str = None) -> dict:
    """Compress pod for transport - lossless."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return {"success": False, "error": "Pod not found"}
    
    if not output:
        output = str(PODS_DIR / f"{pod_name}.dpod")
    
    # Get metadata before compression
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    doc_count = c.fetchone()[0]
    c.execute("SELECT SUM(LENGTH(content)) FROM documents")
    total_content = c.fetchone()[0] or 0
    conn.close()
    
    # Create .dpod file (zip with gzip-compressed DB inside)
    original_size = 0
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Compress and add database
        if db_path.exists():
            with open(db_path, 'rb') as f:
                db_data = f.read()
                original_size += len(db_data)
                # Store raw - zip handles compression
                zf.writestr("data.sqlite", db_data)
        
        # Add manifest
        manifest = {
            "pod_name": pod_name,
            "created": datetime.now().isoformat(),
            "version": "1.0",
            "documents": doc_count,
            "content_bytes": total_content
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        
        # Add metadata if exists
        meta_files = ["metadata.json", "manifest.yaml"]
        for mf in meta_files:
            fp = pod_path / mf
            if fp.exists():
                zf.writestr(mf, fp.read_text())
    
    compressed_size = Path(output).stat().st_size
    ratio = (1 - compressed_size/original_size) * 100 if original_size > 0 else 0
    
    return {
        "success": True,
        "file": output,
        "original_mb": round(original_size/1024/1024, 2),
        "compressed_mb": round(compressed_size/1024/1024, 2),
        "ratio": round(ratio, 1),
        "documents": doc_count
    }

def decompress_pod(dpod_file: str, pod_name: str = None) -> dict:
    """Decompress .dpod file - lossless."""
    if not Path(dpod_file).exists():
        return {"success": False, "error": "File not found"}
    
    if not pod_name:
        pod_name = Path(dpod_file).stem.replace(".dpod", "")
    
    pod_path = PODS_DIR / pod_name
    pod_path.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(dpod_file, 'r') as zf:
        # Extract manifest
        manifest = json.loads(zf.read("manifest.json"))
        
        # Extract database
        if "data.sqlite" in zf.namelist():
            zf.extract("data.sqlite", pod_path)
        
        # Extract metadata
        for f in ["metadata.json", "manifest.yaml"]:
            if f in zf.namelist():
                zf.extract(f, pod_path)
    
    # Verify
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    restored_docs = c.fetchone()[0]
    conn.close()
    
    return {
        "success": True,
        "pod": pod_name,
        "path": str(pod_path),
        "documents": restored_docs,
        "verified": restored_docs == manifest["documents"]
    }

def encrypt_pod(pod_name: str, password: str, output: str = None) -> dict:
    """Encrypt pod with password."""
    if not ENCRYPTION:
        return {"success": False, "error": "cryptography not installed"}
    
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return {"success": False, "error": "Pod not found"}
    
    if not output:
        output = str(PODS_DIR / f"{pod_name}.encrypted")
    
    # Generate key from password
    salt = os.urandom(16)
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    f = Fernet(key)
    
    # Create encrypted archive
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all pod files
        for fpath in pod_path.rglob('*'):
            if fpath.is_file():
                rel = fpath.relative_to(pod_path)
                content = fpath.read_bytes()
                encrypted = f.encrypt(content)
                zf.writestr(str(rel), encrypted)
        
        # Add salt and manifest
        zf.writestr("_salt", base64.b64encode(salt).decode())
    
    return {"success": True, "file": output, "size_mb": round(Path(output).stat().st_size/1024/1024, 2)}

def decrypt_pod(encrypted_file: str, password: str, pod_name: str = None) -> dict:
    """Decrypt pod."""
    if not ENCRYPTION:
        return {"success": False, "error": "cryptography not installed"}
    
    ep = Path(encrypted_file)
    if not ep.exists():
        return {"success": False, "error": "File not found"}
    
    if not pod_name:
        pod_name = ep.stem.replace(".encrypted", "")
    
    pod_path = PODS_DIR / pod_name
    pod_path.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(ep, 'r') as zf:
        # Get salt
        salt = base64.b64decode(zf.read("_salt"))
        
        # Generate key
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        f = Fernet(key)
        
        # Decrypt files
        for name in zf.namelist():
            if name.startswith("_"):
                continue
            try:
                encrypted = zf.read(name)
                decrypted = f.decrypt(encrypted)
                (pod_path / name).write_bytes(decrypted)
            except Exception as e:
                return {"success": False, "error": f"Decrypt failed: {e}"}
    
    return {"success": True, "pod": pod_name, "path": str(pod_path)}

def add_documents(pod_name: str, files: list) -> dict:
    """Add documents to pod."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return {"success": False, "error": "Pod not found"}
    
    db_path = pod_path / "data.sqlite"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    
    added = 0
    for fp in files:
        p = Path(fp)
        if p.exists():
            content = p.read_text()
            c.execute("INSERT INTO documents (title, content, file_type, created_at) VALUES (?, ?, ?, ?)",
                     (p.stem, content, p.suffix, datetime.now().isoformat()))
            added += 1
    
    conn.commit()
    c.execute("SELECT COUNT(*) FROM documents")
    total = c.fetchone()[0]
    conn.close()
    
    return {"success": True, "added": added, "total": total}

# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data Pod Portable")
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    # Compress
    comp = sub.add_parser("compress", help="Compress pod for transport")
    comp.add_argument("pod", help="Pod name")
    comp.add_argument("-o", "--output", help="Output file")
    
    # Decompress
    decomp = sub.add_parser("decompress", help="Decompress .dpod file")
    decomp.add_argument("file", help=".dpod file")
    decomp.add_argument("name", help="Pod name", nargs="?")
    
    # Encrypt
    enc = sub.add_parser("encrypt", help="Encrypt pod")
    enc.add_argument("pod", help="Pod name")
    enc.add_argument("password", help="Password")
    enc.add_argument("-o", "--output", help="Output file")
    
    # Decrypt
    dec = sub.add_parser("decrypt", help="Decrypt pod")
    dec.add_argument("file", help="Encrypted file")
    dec.add_argument("password", help="Password")
    dec.add_argument("name", help="Pod name", nargs="?")
    
    # Add
    add = sub.add_parser("add", help="Add documents to pod")
    add.add_argument("pod", help="Pod name")
    add.add_argument("files", nargs="+", help="Files to add")
    
    args = parser.parse_args()
    
    if args.cmd == "compress":
        print(json.dumps(compress_pod(args.pod, args.output), indent=2))
    elif args.cmd == "decompress":
        print(json.dumps(decompress_pod(args.file, args.name), indent=2))
    elif args.cmd == "encrypt":
        print(json.dumps(encrypt_pod(args.pod, args.password, args.output), indent=2))
    elif args.cmd == "decrypt":
        print(json.dumps(decrypt_pod(args.file, args.password, args.name), indent=2))
    elif args.cmd == "add":
        print(json.dumps(add_documents(args.pod, args.files), indent=2))
