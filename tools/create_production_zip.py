"""Create production.zip package for client systems."""
import os
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(r"d:\Pysian LIS\data")
ROOT_DIR = Path(r"d:\Pysian LIS")
PROD_FOLDER = BASE_DIR / "production"
PROD_ZIP_IN_DATA = BASE_DIR / "production.zip"
PROD_ZIP_IN_ROOT = ROOT_DIR / "production.zip"

# Clean up any existing production folder and zip files
if PROD_FOLDER.exists():
    shutil.rmtree(PROD_FOLDER)

for z in [PROD_ZIP_IN_DATA, PROD_ZIP_IN_ROOT]:
    if z.exists():
        z.unlink()

# Create clean production directory
PROD_FOLDER.mkdir(parents=True, exist_ok=True)
(PROD_FOLDER / "artifacts").mkdir(exist_ok=True)
(PROD_FOLDER / "data").mkdir(exist_ok=True)

# Ignore pycache and compiled pyc when copying app
def ignore_pycache(dirpath, contents):
    ignored = []
    for c in contents:
        if c == "__pycache__" or c.endswith(".pyc"):
            ignored.append(c)
    return ignored

shutil.copytree(BASE_DIR / "app", PROD_FOLDER / "app", ignore=ignore_pycache)
print("Copied clean app/ directory")

# Copy Excel catalog files
data_src = BASE_DIR / "data"
for fname in [
    "horiba_device_catalog.xlsx",
    "piysan_lab_test_catalog.xlsx",
    "new stag test ids.xlsx",
    "SK CBC and ESR test id list.xlsx",
]:
    src_file = data_src / fname
    if src_file.exists():
        shutil.copy2(src_file, PROD_FOLDER / "data" / fname)
print("Copied clean Excel data catalog files")

# Copy scripts and documents from PackageInstaller
installer_src = BASE_DIR / "PackageInstaller"
for fname in [
    "install.ps1",
    "manage_service.ps1",
    "uninstall.ps1",
    "INSTALL.txt",
    "README.md",
    "requirements.txt",
    "service_installer.py",
    ".env.example",
]:
    shutil.copy2(installer_src / fname, PROD_FOLDER / fname)
print("Copied installer automation scripts and documentation")

# Copy rich documentation guides
for fname in [
    "INSTALLATION_AND_TESTING_GUIDE.md",
    "HORIBA_Yumizen_H500_LIS_Installation_Guide.docx",
]:
    doc_file = BASE_DIR / fname
    if doc_file.exists():
        shutil.copy2(doc_file, PROD_FOLDER / fname)
print("Copied comprehensive installation & testing documentation (.md & .docx)")

# Ensure .env.example has canonical production URL
env_example = """# Piysan Production Base URL
PIYSAN_BASE_URL=https://www.piysan.com/

# Optional Laboratory Profile Details
# (When logged into Piysan LIS, the registered lab and brand name are auto-applied)
# LAB_NAME=Clinical Pathology Laboratory
# LAB_ADDRESS=Main Laboratory Facility
# LAB_CONTACT=

# Network Settings
# (Host computer IP is auto-detected dynamically on your local network)
# COMPUTER_IP=
# MACHINE_IP=192.168.1.55
# MACHINE_PORT=5000

# Local Dashboard Authentication
# SESSION_SECRET_KEY is automatically generated during install.ps1
# SESSION_SECRET_KEY=
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=admin123
"""
(PROD_FOLDER / ".env.example").write_text(env_example, encoding="utf-8")

# Build production.zip
print("Creating production.zip...")
with zipfile.ZipFile(PROD_ZIP_IN_DATA, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(PROD_FOLDER):
        for file in files:
            file_path = Path(root) / file
            # Store with 'production/' prefix so it unpacks into a clean folder
            archive_path = Path("production") / file_path.relative_to(PROD_FOLDER)
            zf.write(file_path, archive_path)

# Also copy production.zip to root "d:\Pysian LIS\production.zip"
shutil.copy2(PROD_ZIP_IN_DATA, PROD_ZIP_IN_ROOT)

print(f"Created {PROD_ZIP_IN_DATA} ({PROD_ZIP_IN_DATA.stat().st_size:,} bytes)")
print(f"Copied to {PROD_ZIP_IN_ROOT} ({PROD_ZIP_IN_ROOT.stat().st_size:,} bytes)")

