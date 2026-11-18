"""Script to clean and build the latest production PackageInstaller."""
import os
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(r"d:\Pysian LIS\data")
INSTALLER_DIR = BASE_DIR / "PackageInstaller"
OLD_ZIP = BASE_DIR / "app.zip"
FINAL_ZIP = BASE_DIR / "PackageInstaller.zip"

# 1. Delete old installer and old zip files
if OLD_ZIP.exists():
    OLD_ZIP.unlink()
    print("Deleted old app.zip")

if FINAL_ZIP.exists():
    FINAL_ZIP.unlink()
    print("Deleted existing PackageInstaller.zip")

# Preserve the support scripts before deleting the old folder
saved_scripts = {}
script_names = [
    "install.ps1",
    "manage_service.ps1",
    "uninstall.ps1",
    "INSTALL.txt",
    "README.md",
]
for name in script_names:
    p = INSTALLER_DIR / name
    if p.exists():
        saved_scripts[name] = p.read_bytes()

if INSTALLER_DIR.exists():
    shutil.rmtree(INSTALLER_DIR)
    print("Deleted old PackageInstaller folder")

# 2. Re-create PackageInstaller directory
INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
(INSTALLER_DIR / "artifacts").mkdir(exist_ok=True)
(INSTALLER_DIR / "data").mkdir(exist_ok=True)

# 3. Copy app/ directory excluding __pycache__ and .pyc
def ignore_pycache(dirpath, contents):
    ignored = []
    for c in contents:
        if c == "__pycache__" or c.endswith(".pyc"):
            ignored.append(c)
    return ignored

shutil.copytree(BASE_DIR / "app", INSTALLER_DIR / "app", ignore=ignore_pycache)
print("Copied latest app/ (clean of pycache)")

# 4. Copy excel data files into PackageInstaller/data
data_src = BASE_DIR / "data"
for fname in ["new stag test ids.xlsx", "SK CBC and ESR test id list.xlsx"]:
    shutil.copy2(data_src / fname, INSTALLER_DIR / "data" / fname)
print("Copied clean Excel master data files")

# 5. Restore support scripts
for name, content in saved_scripts.items():
    (INSTALLER_DIR / name).write_bytes(content)
print("Restored installer support scripts")

# 6. Copy service_installer.py and requirements.txt from latest project root
shutil.copy2(BASE_DIR / "service_installer.py", INSTALLER_DIR / "service_installer.py")
shutil.copy2(BASE_DIR / "requirements.txt", INSTALLER_DIR / "requirements.txt")
print("Copied service_installer.py and latest requirements.txt")

# 7. Write clean production .env.example
env_example_content = """PIYSAN_BASE_URL=https://piysan.com/

# Required for production: install.ps1 auto-generates SESSION_SECRET_KEY into
# .env on first install if it's missing. Set ADMIN_PASSWORD to change the
# local fallback admin login from the default (admin / admin123).
# SESSION_SECRET_KEY=
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=
"""
(INSTALLER_DIR / ".env.example").write_text(env_example_content, encoding="utf-8")
print("Wrote production .env.example")

# 8. Create PackageInstaller.zip
print("Creating final PackageInstaller.zip...")
with zipfile.ZipFile(FINAL_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(INSTALLER_DIR):
        for file in files:
            file_path = Path(root) / file
            archive_path = file_path.relative_to(BASE_DIR)
            zf.write(file_path, archive_path)

print(f"Successfully created: {FINAL_ZIP} ({FINAL_ZIP.stat().st_size:,} bytes)")

