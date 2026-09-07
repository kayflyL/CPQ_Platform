import subprocess, sys, os
root = r"D:\CPQ_Platform_V1"
patch_file = sys.argv[1]
with open(os.path.join(root, patch_file), "r", encoding="utf-8") as f:
    patch = f.read()
exe = r"C:\Users\16891\AppData\Local\OpenAI\Codex\bin\b99306303521e97e\codex.exe"
r = subprocess.run([exe, "--codex-run-as-apply-patch", patch], capture_output=True, text=True, encoding="utf-8")
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
