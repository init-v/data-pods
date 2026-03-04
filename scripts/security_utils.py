#!/usr/bin/env python3
"""
Security & Portability Utils for Data Pods
- Encryption at rest
- Compression for sharing
- Secure export
"""
import os
import sqlite3
import json
import zipfile
import tarfile
import hashlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from cryptography.fernet import Fernet
    ENCRYPTION = True
except ImportError:
    ENCRYPTION = False

PODS_DIR = Path.home() / ".openclaw" / "data-pods"

def generate_encryption_key(password: str, salt: bytes = None) -> tuple:
    """Generate encryption key from password."""
    if not ENCRYPTION:
        return None, None
    
    if salt is None:
        salt = os.urandom(16)
    
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    kdf = PBKDF2(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key), salt

def encrypt_pod(pod_name: str, password: str, output: str = None) -> str:
    """Encrypt a pod with a password."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return None
    
    if not ENCRYPTION:
        print("Encryption not available")
        return None
    
    fernet, salt = generate_encryption_key(password)
    if not output:
        output = f"{pod_name}.encrypted"
    
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in pod_path.rglob('*'):
            if file.is_file():
                rel_path = file.relative_to(pod_path)
                with open(file, 'rb') as f:
                    content = f.read()
                    encrypted = fernet.encrypt(content)
                    zf.writestr(str(rel_path), encrypted)
        
        metadata = {
            "pod_name": pod_name,
            "encrypted_at": datetime.now().isoformat(),
            "salt": base64.b64encode(salt).decode()
        }
        zf.writestr("_metadata.json", json.dumps(metadata))
    
    print(f"✅ Encrypted pod: {output}")
    return output

def decrypt_pod(encrypted_file: str, password: str, output_dir: str = None) -> str:
    """Decrypt an encrypted pod."""
    if not ENCRYPTION:
        print("Encryption not available")
        return None
    
    try:
        with zipfile.ZipFile(encrypted_file, 'r') as zf:
            metadata = json.loads(zf.read("_metadata.json"))
            salt = base64.b64decode(metadata["salt"])
            fernet, _ = generate_encryption_key(password, salt)
            
            if not output_dir:
                output_dir = PODS_DIR / metadata["pod_name"]
            
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            for name in zf.namelist():
                if name == "_metadata.json":
                    continue
                encrypted_content = zf.read(name)
                try:
                    decrypted = fernet.decrypt(encrypted_content)
                    (output_dir / name).write_bytes(decrypted)
                except:
                    print(f"Warning: Could not decrypt {name}")
            
            print(f"✅ Decrypted to: {output_dir}")
            return str(output_dir)
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None

def compress_pod(pod_name: str, format: str = "zip", output: str = None) -> str:
    """Export pod as compressed archive."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return None
    
    if not output:
        output = f"{pod_name}.{format}"
    
    if format == "zip":
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in pod_path.rglob('*'):
                if file.is_file():
                    rel_path = file.relative_to(pod_path)
                    zf.write(file, rel_path)
    elif format == "tar.gz":
        with tarfile.open(output, 'w:gz') as tf:
            tf.add(pod_path, arcname=pod_name)
    
    size_mb = Path(output).stat().st_size / 1024 / 1024
    print(f"✅ Exported {pod_name}: {output} ({size_mb:.1f} MB)")
    return output

def get_pod_size(pod_name: str) -> dict:
    """Get detailed size info for a pod."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return None
    
    total = 0
    files = []
    
    for file in pod_path.rglob('*'):
        if file.is_file():
            size = file.stat().st_size
            total += size
            files.append({"name": file.name, "size_kb": size / 1024})
    
    return {
        "pod": pod_name,
        "total_mb": total / 1024 / 1024,
        "files": len(files)
    }

def verify_pod_integrity(pod_name: str) -> dict:
    """Verify pod data integrity."""
    pod_path = PODS_DIR / pod_name
    if not pod_path.exists():
        return {"valid": False, "error": "Pod not found"}
    
    db_path = pod_path / "data.sqlite"
    if not db_path.exists():
        return {"valid": False, "error": "Database not found"}
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    try:
        c.execute("PRAGMA integrity_check")
        result = c.fetchone()
        c.execute("SELECT COUNT(*) FROM documents")
        doc_count = c.fetchone()[0]
        conn.close()
        return {"valid": result[0] == "ok", "documents": doc_count}
    except Exception as e:
        conn.close()
        return {"valid": False, "error": str(e)}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    
    enc_p = sub.add_parser("encrypt", help="Encrypt pod")
    enc_p.add_argument("pod", help="Pod name")
    enc_p.add_argument("password", help="Password")
    enc_p.add_argument("--output", help="Output file")
    
    dec_p = sub.add_parser("decrypt", help="Decrypt pod")
    dec_p.add_argument("file", help="Encrypted file")
    dec_p.add_argument("password", help="Password")
    dec_p.add_argument("--output", help="Output dir")
    
    comp_p = sub.add_parser("compress", help="Compress pod")
    comp_p.add_argument("pod", help="Pod name")
    comp_p.add_argument("--format", choices=["zip", "tar.gz"], default="zip")
    
    size_p = sub.add_parser("size", help="Pod size")
    size_p.add_argument("pod", help="Pod name")
    
    ver_p = sub.add_parser("verify", help="Verify pod")
    ver_p.add_argument("pod", help="Pod name")
    
    args = parser.parse_args()
    
    if args.encrypt:
        print(encrypt_pod(args.pod, args.password, args.output))
    elif args.decrypt:
        print(decrypt_pod(args.file, args.password, args.output))
    elif args.compress:
        print(compress_pod(args.pod, args.format))
    elif args.size:
        print(json.dumps(get_pod_size(args.pod), indent=2))
    elif args.verify:
        print(json.dumps(verify_pod_integrity(args.pod), indent=2))
