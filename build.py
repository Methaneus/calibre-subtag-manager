"""Build /workspace/Subtag_Manager.zip from ./subtag_manager (files at zip root)."""
import os, sys, zipfile
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'subtag_manager')
OUT = sys.argv[1] if len(sys.argv) > 1 else '/workspace/Subtag_Manager.zip'
for f in sorted(os.listdir(SRC)):
    if f.endswith('.py'):  # syntax check without leaving .pyc files behind
        compile(open(os.path.join(SRC, f), encoding='utf-8').read(), f, 'exec')
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            if f.endswith('.pyc'):
                continue
            p = os.path.join(root, f)
            z.write(p, os.path.relpath(p, SRC).replace(os.sep, '/'))
print(OUT)
