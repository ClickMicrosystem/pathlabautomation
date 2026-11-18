"""Generate both Markdown and Word (.docx) Installation & Testing Guides with explicit Python prerequisites."""
import os
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

BASE_DIR = Path(r"d:\Pysian LIS\data")
DOCX_PATH_DATA = BASE_DIR / "HORIBA_Yumizen_H500_LIS_Installation_Guide.docx"
DOCX_PATH_ROOT = Path(r"d:\Pysian LIS") / "HORIBA_Yumizen_H500_LIS_Installation_Guide.docx"
MD_PATH = BASE_DIR / "INSTALLATION_AND_TESTING_GUIDE.md"

MARKDOWN_CONTENT = r"""# HORIBA Yumizen H500 / H500E ASTM LIS Integration
## Field Installation, Network Setup & End-to-End Testing Guide

**Version:** 2.0 (Production Release)  
**Target Instrument:** HORIBA Yumizen H500 / H500E (5-Part Hematology Analyzer)  
**LIS Cloud Server:** [https://www.piysan.com/](https://www.piysan.com/)  
**Document Purpose:** Complete standard operating procedure (SOP) for field installation teams, IT administrators, and lab technicians to set up the LIS bridge on a new client system.

---

## 1. System Architecture & Overview

The **LabDecoderService** is a high-reliability Windows background service and Web LIS application designed to bridge HORIBA Yumizen H500 / H500E hematology analyzers with the Piysan Cloud LIS.

```
+--------------------------+         TCP / ASTM 1381-95        +-----------------------------------+         HTTPS / REST API         +--------------------------+
|   HORIBA Yumizen H500    | --------------------------------> |     LabDecoderService (Host PC)   | -------------------------------> |     Piysan Cloud LIS     |
| (5-Part Diff Hematology) | <-------------------------------- | (FastAPI / Windows Svc / Decoder) | <------------------------------- | (https://www.piysan.com) |
+--------------------------+     Bidirectional Handshake       +-----------------------------------+     Order Sync & Result Push     +--------------------------+
```

### Key Capabilities:
1. **Real-time ASTM 1381/1394 Network Listener:** Listens on TCP Port `5000` for live analyzer data transmissions.
2. **Automated Hematology Decoder:** Decodes all 16-26 CBC parameters, flags, LOINC codes, WBC/RBC/PLT histograms, and LMNE scattergram matrices.
3. **Smart Test Code Resolution:** Translates analyzer codes (`WBC`, `6690-2`, `HGB`, etc.) into Piysan numeric IDs automatically.
4. **Piysan Cloud Sync & Auto-Submit:** Automatically downloads patient bookings from Piysan and immediately pushes verified test results upon analysis.
5. **Dynamic Lab Identity:** Automatically retrieves the client lab's official name, brand name, and credentials upon login.

---

## 2. Network Requirements & IP Address Allocation

Understanding which IP address belongs where is **the most critical step** in preventing connection failures.

### The Two Required IP Addresses:
1. **Host Computer IP Address (The PC running LabDecoderService):**
   * This is the local LAN IPv4 address of the lab's Windows computer (e.g. `192.168.1.14` or static `192.168.1.20`).
   * **Where to find it:** Open the LIS Dashboard (`http://localhost:8000/dashboard`) &ndash; it is displayed on the **Host / Computer IP Address** tile. Alternatively, open Command Prompt and run `ipconfig`.
   * **Where it is used:** Entered into the **HORIBA Analyzer** as the **"Host IP" / "Server IP"**.

2. **HORIBA Analyzer IP Address:**
   * This is the IP address assigned to the physical HORIBA Yumizen machine (e.g. `192.168.1.55`).
   * Must be on the **same subnet** as the Host PC (e.g. Subnet Mask `255.255.255.0`, same `192.168.1.x` network).
   * **Where it is used:** Configured in the HORIBA analyzer's network menu.

### Network Settings Summary Table:

| Parameter | Host Computer (PC) | HORIBA Analyzer (Instrument) |
| :--- | :--- | :--- |
| **Role** | TCP Server / Host Listener | TCP Client / ASTM Sender |
| **IP Address** | Assigned by LAN (e.g. `192.168.1.14`) | Unique Static LAN IP (e.g. `192.168.1.55`) |
| **Subnet Mask** | `255.255.255.0` | `255.255.255.0` (Must match PC) |
| **Default Gateway** | `192.168.1.1` (or local router) | `192.168.1.1` (Must match PC) |
| **Communication Port** | **`5000`** (Inbound listening port) | **`5000`** (Target destination port) |
| **Cable Connection** | Standard CAT5e/CAT6 Ethernet | Connected to same LAN switch or direct to PC |

---

## 3. System Prerequisites & Python Setup (Before Installation)

Before running the installation script on the client computer, ensure the system meets the prerequisites below.

### A. Operating System & Hardware:
* **Operating System:** Windows 10 (64-bit), Windows 11 (64-bit), or Windows Server 2016/2019/2022.
* **Architecture:** 64-bit (x64) is strictly required for the Windows Service (`pywin32`) wrapper.
* **RAM:** 4 GB minimum (8 GB recommended).
* **Disk Space:** 500 MB free space.
* **Network:** Dedicated Ethernet LAN port connected to the analyzer or lab switch.

### B. Required Python Version & Download Link:
* **Recommended Version:** **Python 3.11.x (64-bit)** &ndash; Specifically **Python 3.11.9 (64-bit)**.
  *(Python 3.10 and 3.12 64-bit are also supported, but 3.11 offers the highest stability with the Windows PyWin32 service runner).*
* **Direct Official Installer Download Link:**  
  [https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe](https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe)  
  *(Alternative download page: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/))*

### C. CRITICAL Python Installation Instructions:
> [!IMPORTANT]
> **MANDATORY STEP DURING PYTHON INSTALLATION:**
> 1. Launch the downloaded installer `python-3.11.9-amd64.exe`.
> 2. At the very bottom of the first setup window, you **MUST CHECK** the box:  
>    **`[X] Add python.exe to PATH`**  
>    *(If this box is NOT checked, the automated installer `install.ps1` will fail with "Python was not found on PATH".)*
> 3. Click **"Install Now"** (or choose *Customize installation* and check *Install for all users*).
> 4. On the final setup screen, click **"Disable path length limit"** (if prompted), then click **Close**.

### D. Verify Python Installation:
Open Command Prompt or PowerShell and type:
```powershell
python --version
```
Expected output:
```
Python 3.11.9
```
If Python outputs its version, the computer is fully prepared to run `install.ps1`.

---

## 4. HORIBA Yumizen H500 Machine Setup Steps

Follow this step-by-step menu navigation on the HORIBA Yumizen touchscreen:

1. **Access Settings:**
   * On the main screen, tap the **Menu** icon (top left).
   * Tap **Settings** &rarr; enter supervisor PIN if prompted (default is usually `1234` or `0000`).
2. **Navigate to LIS / Communication:**
   * Select **System** &rarr; **Output / Communication** &rarr; **LIS**.
3. **Configure Protocol:**
   * **Protocol:** Select `ASTM 1381-95 / ASTM 1394-91` (or `ASTM High Level`).
   * **Link Type / Connection:** Select `Ethernet` (or `TCP/IP`).
   * **Operating Mode:** Select `Client` (Analyzer initiates transmission to Host).
4. **Enter Network Settings:**
   * **Analyzer IP:** Enter the machine IP (e.g. `192.168.1.55`).
   * **Subnet Mask:** `255.255.255.0`.
   * **Default Gateway:** `192.168.1.1` (or router IP).
   * **Remote Host IP / Server IP:** Enter the **Host Computer IP** (from Dashboard or `ipconfig`).
   * **Remote Port / Server Port:** Enter **`5000`**.
5. **Transmission Options:**
   * **Auto Transmission:** Set to `Enabled` (transmits immediately when a run finishes).
   * **Send Histograms & Matrices:** Set to `Yes` / `Enabled` (sends full curve data).
6. **Save & Test Connection:**
   * Tap **Save / Validate**.
   * Tap **Test Link / Ping** &ndash; it should display `Success` or `Connected`.

---

## 5. Software Installation on Client PC (Step-by-Step)

### Step 1: Unzip the Package
1. Copy `production.zip` to the client computer (e.g. `C:\PiysanLIS` or `C:\Users\User\Downloads`).
2. Right-click `production.zip` &rarr; **Extract All...**
3. Open the extracted `production` folder.

### Step 2: Open PowerShell as Administrator
1. Press `Windows Key + X` &rarr; select **Windows PowerShell (Admin)** or **Terminal (Admin)**.
2. Navigate into the extracted folder:
   ```powershell
   cd "C:\path\to\production"
   ```

### Step 3: Run the Automated Installer
Execute the installation script:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

**What the installer does automatically:**
* Checks and verifies Python 3.11+.
* Creates an isolated virtual environment (`.venv`).
* Installs all required dependencies (`FastAPI`, `Uvicorn`, `HTTPX`, `OpenPyXL`, `PyWin32`).
* Generates a unique secure `SESSION_SECRET_KEY` in `.env`.
* Configures Windows Firewall to open inbound TCP Port `5000`.
* Registers and starts the Windows Service `LabDecoderService`.

### Step 4: Verify Service Status
Run:
```powershell
.\manage_service.ps1 status
```
You should see:
```
Service LabDecoderService is Running
```

---

## 6. Lab Configuration in the Web LIS Dashboard

1. Open your web browser (Chrome, Edge, or Firefox) and visit:
   ```
   http://localhost:8000
   ```
2. **Login to Dashboard:**
   * **Username:** `admin`
   * **Password:** `admin123`
3. **Configure Piysan Production Credentials:**
   * Click **Piysan Settings** in the left navigation (or go to `http://localhost:8000/piysan`).
   * Enter the new client lab's **Mobile Number** and **Password** (provided by Piysan administrator).
   * Ensure **Auto-Submit to Piysan** is set to `Enabled` (Checked).
   * Click **Save & Test Connection**.
   * *The system will authenticate with `https://www.piysan.com/`, fetch the lab's official profile, and automatically update the dashboard with the client lab's real brand name!*
4. **Verify Test Mappings:**
   * Click **Test Mapping** in the sidebar (`/mapping`).
   * The system **pre-seeds all 16 CBC parameters** (44 short and LOINC code pairs) out of the box:
     - `WBC` / `6690-2` &rarr; Total Leucocyte Count (ID: 4)
     - `RBC` / `789-8` &rarr; Total RBC (ID: 2)
     - `HGB` / `718-7` &rarr; Hemoglobin (HB) (ID: 1)
     - `PLT` / `777-3` &rarr; Platelet Count (ID: 3)
     - `HCT` / `4544-3` &rarr; Hematocrit (PCV / HCT) (ID: 15)
     - `NEU%` / `NEU#` &rarr; Neutrophils (ID: 5)
     - `LYM%` / `LYM#` &rarr; Lymphocytes (ID: 6)
     - `MON%` / `MON#` &rarr; Monocytes (ID: 7)
     - `EOS%` / `EOS#` &rarr; Eosinophils (ID: 8)
     - `BAS%` / `BAS#` &rarr; Basophils (ID: 9)
     - `RDW-CV` &rarr; Red Cell Dist. Width (RDW-CV) (ID: 19)
     - `RDW-SD` &rarr; Red Cell Dist. Width (RDW-SD) (ID: 20)
     - `MPV` &rarr; Mean Platelet Volume (ID: 21)
     - `PDW` &rarr; Platelet Distribution Width (ID: 431)
     - `PCT` &rarr; Plateletcrit (ID: 534)
     - `P-LCR` &rarr; P-LCR (ID: 24)
   * All 16 CBC parameters are mapped and ready.

---

## 7. End-to-End Testing Procedure (Sample Run to Piysan Cloud)

Follow this 4-step testing routine to verify full end-to-end operation:

### Step 1: Sync Patient Orders
1. On the Dashboard (`/dashboard`), click **Sync Piysan Bookings** (or **Fetch Latest Orders**).
2. The latest patient bookings from Piysan Production will appear in the table.
3. Note the **Reference Number / Sample ID** of the test order (e.g. `202611...`).

### Step 2: Run Blood Sample on HORIBA Yumizen
1. Place the EDTA blood tube into the Yumizen H500 tube holder.
2. On the analyzer touchscreen:
   * Select **Sample Mode**.
   * Enter the exact **Reference Number / Sample ID** into the **Sample ID / Barcode** field.
   * Verify patient name if matched, or leave as barcode.
3. Press **Start / Run**.

### Step 3: Verify Real-Time ASTM Capture
1. When analysis completes (~60 seconds), the analyzer automatically transmits the ASTM packet over TCP port 5000.
2. In the LIS Dashboard, refresh or watch the table:
   * The order will immediately move from *Pending* to **"Ready to Push"** with a green badge showing the decoded test count (e.g. `16 tests`).
   * Click **View Decoded Report** to inspect:
     - Exact numeric parameters (WBC, RBC, HGB, PLT, etc.).
     - Reference ranges & high/low flags.
     - Auto-generated WBC, RBC, and PLT Histograms.
     - 5-part LMNE Scattergrams.

### Step 4: Push to Piysan & Confirm Live Delivery
1. If **Auto-Submit** is enabled, the results are sent to Piysan automatically within 2 seconds.
2. If submitting manually: click **Push Results** next to the patient.
3. The status changes to **Success** (Green), displaying:
   `Results submitted successfully (16 tests updated)`.
4. Log into the Piysan web portal at [https://www.piysan.com/](https://www.piysan.com/) &ndash; verify that the patient's CBC lab report is fully populated with all numeric values!

---

## 8. Troubleshooting & FAQ

### Issue 1: "Python was not found on PATH" during install.ps1
* **Cause:** Python is either not installed or the "Add python.exe to PATH" checkbox was not selected during Python setup.
* **Fix:** Download Python 3.11.9 64-bit from [https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe](https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe). Run the installer, click **Modify** (or *Install*), and check **`[X] Add python.exe to PATH`**. Restart PowerShell and re-run `.\install.ps1`.

### Issue 2: Analyzer says "Connection Failed / Timeout"
* **Cause:** Analyzer cannot reach the PC on Port 5000.
* **Fix:**
  1. Check if Windows Firewall is blocking Port 5000. Run in Admin PowerShell:
     ```powershell
     New-NetFirewallRule -DisplayName "HORIBA Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
     ```
  2. Verify PC IP address: run `ipconfig`. Ensure the analyzer's "Host IP" matches this exact IP.
  3. Ensure both the PC and analyzer are on the same subnet (e.g. `192.168.1.x`).
  4. Test ping from PC to analyzer: `ping 192.168.1.55`.

### Issue 3: Service fails to start with "An instance of the service is already running"
* **Cause:** A previous instance of `pythonservice.exe` or `python.exe` was not terminated.
* **Fix:** In Admin PowerShell:
  ```powershell
  taskkill /F /IM pythonservice.exe /T
  taskkill /F /IM python.exe /T
  .\manage_service.ps1 start
  ```

### Issue 4: Managing the Service
* **Stop Service:** `.\manage_service.ps1 stop`
* **Start Service:** `.\manage_service.ps1 start`
* **Restart Service:** `.\manage_service.ps1 restart`
* **View Logs:** Open `artifacts\service.log` or run `Get-Content artifacts\service.log -Tail 50 -Wait`.
"""

MD_PATH.write_text(MARKDOWN_CONTENT, encoding="utf-8")
print(f"Created Markdown Guide: {MD_PATH}")

# Now build the Word (.docx) Document
doc = Document()

# Set standard margins (0.75 in)
for section in doc.sections:
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)

# Styling helpers
def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

# Title & Header
p_title = doc.add_paragraph()
r_title = p_title.add_run("HORIBA Yumizen H500 / H500E ASTM LIS Integration")
r_title.bold = True
r_title.font.size = Pt(22)
r_title.font.color.rgb = RGBColor(15, 23, 42) # Slate 900
p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER

p_sub = doc.add_paragraph()
r_sub = p_sub.add_run("Field Installation, Network Configuration & End-to-End Testing SOP")
r_sub.font.size = Pt(13)
r_sub.font.color.rgb = RGBColor(79, 70, 229) # Indigo 600
r_sub.bold = True
p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

# Metadata callout box
tbl_meta = doc.add_table(rows=1, cols=1)
tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
cell_meta = tbl_meta.cell(0, 0)
set_cell_background(cell_meta, "F1F5F9")
set_cell_margins(cell_meta, top=140, bottom=140, left=200, right=200)
p_meta = cell_meta.paragraphs[0]
p_meta.add_run("Target Instrument: ").bold = True
p_meta.add_run("HORIBA Yumizen H500 / H500E (5-Part Hematology Analyzer)\n")
p_meta.add_run("Required Runtime: ").bold = True
p_meta.add_run("Python 3.11.x (64-bit) [Add to PATH Required]\n")
p_meta.add_run("Cloud LIS Server: ").bold = True
p_meta.add_run("https://www.piysan.com/ | Production Release v2.0\n")
p_meta.add_run("Document Scope: ").bold = True
p_meta.add_run("Step-by-step standard operating procedure for installation teams & field technicians.")

doc.add_paragraph() # Spacer

# Helper to add styled section headings
def add_heading_1(text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(14)
    h.paragraph_format.space_after = Pt(4)
    r = h.add_run(text)
    r.bold = True
    r.font.size = Pt(15)
    r.font.color.rgb = RGBColor(30, 41, 59)
    # Add a thin line under heading
    p_bdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="8" w:space="4" w:color="4F46E5"/></w:pBdr>')
    h._p.get_or_add_pPr().append(p_bdr)
    return h

def add_heading_2(text):
    h = doc.add_paragraph()
    h.paragraph_format.space_before = Pt(10)
    h.paragraph_format.space_after = Pt(2)
    r = h.add_run(text)
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(79, 70, 229)
    return h

# Section 1
add_heading_1("1. System Architecture & Overview")
p1 = doc.add_paragraph()
p1.add_run(
    "The LabDecoderService is an automated, high-reliability Windows background service and Web LIS application. "
    "It establishes a bidirectional ASTM 1381/1394 connection with the HORIBA Yumizen H500/H500E analyzer over Ethernet LAN (TCP Port 5000), "
    "decodes the complete 5-part differential hematology results, histograms, and scattergrams, "
    "and automatically transmits the verified numeric results to the Piysan Cloud LIS (https://www.piysan.com/)."
)

# Section 2
add_heading_1("2. Network Requirements & IP Address Allocation")
p2 = doc.add_paragraph()
p2.add_run("Accurate IP address configuration is the single most important factor for reliable analyzer connectivity. Two distinct IP addresses are involved:\n")

p_ip1 = doc.add_paragraph(style='List Bullet')
r = p_ip1.add_run("Host Computer IP Address (The Windows PC): ")
r.bold = True
p_ip1.add_run(
    "This is the local LAN IPv4 address of the computer where LabDecoderService is installed (e.g., 192.168.1.14). "
    "It is displayed directly on the LIS Dashboard under 'Host / Computer IP Address'. "
    "This exact IP must be entered into the HORIBA machine as the 'Remote Server IP' or 'Host IP'."
)

p_ip2 = doc.add_paragraph(style='List Bullet')
r = p_ip2.add_run("HORIBA Analyzer IP Address: ")
r.bold = True
p_ip2.add_run(
    "This is the static IP address assigned to the physical Yumizen machine (e.g., 192.168.1.55). "
    "It must reside on the exact same local subnet as the PC (Subnet Mask: 255.255.255.0)."
)

# Network Comparison Table
tbl_net = doc.add_table(rows=6, cols=3)
tbl_net.alignment = WD_TABLE_ALIGNMENT.CENTER
headers = ["Network Parameter", "Host Computer (Windows PC)", "HORIBA Analyzer (Instrument)"]
widths = [Inches(1.8), Inches(2.5), Inches(2.7)]

for col_idx, (text, w) in enumerate(zip(headers, widths)):
    cell = tbl_net.cell(0, col_idx)
    cell.width = w
    set_cell_background(cell, "1E293B") # Dark slate
    set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.bold = True
    r.font.color.rgb = RGBColor(255, 255, 255)
    r.font.size = Pt(9.5)

net_data = [
    ("Role in ASTM", "TCP Server (Listening on Port 5000)", "TCP Client (Transmits results to Host)"),
    ("IP Address", "Auto-detected by LAN (e.g. 192.168.1.14)", "Static LAN IP (e.g. 192.168.1.55)"),
    ("Subnet Mask", "255.255.255.0", "255.255.255.0 (Must match PC)"),
    ("Default Gateway", "192.168.1.1 (Router IP)", "192.168.1.1 (Must match PC)"),
    ("Port Configuration", "5000 (Inbound TCP Port)", "5000 (Destination Host Port)"),
]

for row_idx, row_values in enumerate(net_data, start=1):
    bg = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
    for col_idx, text in enumerate(row_values):
        cell = tbl_net.cell(row_idx, col_idx)
        cell.width = widths[col_idx]
        set_cell_background(cell, bg)
        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(text)
        r.font.size = Pt(9)
        if col_idx == 0:
            r.bold = True

doc.add_paragraph() # Spacer

# Section 3: PYTHON PREREQUISITES
add_heading_1("3. System Prerequisites & Python Setup (Before Installation)")
p_pre = doc.add_paragraph()
p_pre.add_run(
    "Before running the automated installer script, Python 64-bit must be installed on the client machine. "
    "Please review the exact system and runtime requirements below:"
)

tbl_py = doc.add_table(rows=5, cols=2)
tbl_py.alignment = WD_TABLE_ALIGNMENT.CENTER
py_widths = [Inches(2.4), Inches(4.6)]

for col_idx, (text, w) in enumerate(zip(["Requirement Component", "Specification & Installation Guideline"], py_widths)):
    cell = tbl_py.cell(0, col_idx)
    cell.width = w
    set_cell_background(cell, "1E293B")
    set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.bold = True
    r.font.color.rgb = RGBColor(255, 255, 255)
    r.font.size = Pt(9.5)

py_specs = [
    ("Operating System", "Windows 10 (64-bit), Windows 11 (64-bit), or Windows Server 2016/2019/2022 (x64)"),
    ("Required Python Version", "Python 3.11.x (64-bit) — Strongly Recommended: Python 3.11.9 (64-bit)\n(Python 3.10 and 3.12 64-bit are also supported; 32-bit Python is NOT supported)"),
    ("Official Download Link", "Direct 64-bit Installer: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe\nGeneral Windows Python Hub: https://www.python.org/downloads/windows/"),
    ("Verification Command", "Open Command Prompt or PowerShell and type: python --version\nExpected output: Python 3.11.9 (or 3.10.x / 3.12.x)"),
]

for row_idx, (comp, spec) in enumerate(py_specs, start=1):
    bg = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
    for col_idx, text in enumerate([comp, spec]):
        cell = tbl_py.cell(row_idx, col_idx)
        cell.width = py_widths[col_idx]
        set_cell_background(cell, bg)
        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(text)
        r.font.size = Pt(9)
        if col_idx == 0:
            r.bold = True

doc.add_paragraph() # Spacer

# CRITICAL CALLOUT BOX FOR PYTHON CHECKBOX
tbl_warn = doc.add_table(rows=1, cols=1)
tbl_warn.alignment = WD_TABLE_ALIGNMENT.CENTER
cell_warn = tbl_warn.cell(0, 0)
set_cell_background(cell_warn, "FEF3C7") # Soft Amber
set_cell_margins(cell_warn, top=140, bottom=140, left=200, right=200)
# Red-amber border
tcPr = cell_warn._tc.get_or_add_tcPr()
tcBorders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:top w:val="single" w:sz="18" w:space="0" w:color="D97706"/><w:left w:val="single" w:sz="18" w:space="0" w:color="D97706"/><w:bottom w:val="single" w:sz="18" w:space="0" w:color="D97706"/><w:right w:val="single" w:sz="18" w:space="0" w:color="D97706"/></w:tcBorders>')
tcPr.append(tcBorders)

p_warn = cell_warn.paragraphs[0]
r_warn_title = p_warn.add_run("CRITICAL REQUIREMENT: 'Add python.exe to PATH' Checkbox\n")
r_warn_title.bold = True
r_warn_title.font.size = Pt(11)
r_warn_title.font.color.rgb = RGBColor(180, 83, 9) # Amber 700

p_warn.add_run(
    "When executing the Python 3.11 installer on the client PC:\n"
    "1. Look at the very bottom of the first setup window.\n"
    "2. YOU MUST CHECK THE BOX: [X] Add python.exe to PATH before clicking Install!\n"
    "   (If this checkbox is missed, the automated install.ps1 script will fail with 'Python was not found on PATH'.)\n"
    "3. Click 'Install Now' (or 'Customize installation' -> select 'Install for all users').\n"
    "4. On the final completion window, click 'Disable path length limit' if prompted, then click Close."
)

doc.add_paragraph() # Spacer

# Section 4
add_heading_1("4. HORIBA Yumizen H500 Machine Setup Steps")
p4 = doc.add_paragraph()
p4.add_run("Follow this step-by-step menu navigation on the HORIBA Yumizen touchscreen:")

steps_horiba = [
    ("1. Navigate to LIS Settings:", "Tap Menu (top-left) -> Settings -> enter supervisor PIN (default: 1234 or 0000) -> System -> Output -> LIS."),
    ("2. Select ASTM Protocol:", "Set Protocol to ASTM 1381-95 / 1394-91 (or ASTM High Level). Set Link Type to Ethernet (TCP/IP)."),
    ("3. Set Client Mode:", "Ensure Operating Mode is set to Client (the analyzer connects outward to the Host PC)."),
    ("4. Enter Network Settings:", "Set Analyzer IP to 192.168.1.55, Subnet Mask to 255.255.255.0, and Gateway to 192.168.1.1."),
    ("5. Set Target Host Server:", "Set Remote Host IP to the Host Computer IP (from the LIS Dashboard), and Remote Port to 5000."),
    ("6. Enable Real-Time Output:", "Enable Automatic Transmission so samples send automatically upon validation. Enable Histograms and Matrices."),
    ("7. Validate Connection:", "Tap Save / Validate, then tap Test Link. The screen will report Connection Successful.")
]

for title, desc in steps_horiba:
    p = doc.add_paragraph(style='List Number')
    r = p.add_run(title + " ")
    r.bold = True
    p.add_run(desc)

# Section 5
add_heading_1("5. Software Installation on Client PC (Step-by-Step)")
p5 = doc.add_paragraph()
p5.add_run("Once Python 3.11 (64-bit) is installed, execute the automated deployment:")

steps_install = [
    ("Step A - Extract Archive:", "Unzip production.zip to a permanent location, e.g., C:\\PiysanLIS or C:\\Users\\hp\\Downloads\\production."),
    ("Step B - Open Admin PowerShell:", "Press Win+X, choose Terminal (Admin) or Windows PowerShell (Admin), and cd into the unzipped folder."),
    ("Step C - Run install.ps1:", "Run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass ; .\\install.ps1"),
    ("Step D - Verify Service Running:", "Run: .\\manage_service.ps1 status. It should confirm 'Service LabDecoderService is Running'.")
]

for title, desc in steps_install:
    p = doc.add_paragraph(style='List Bullet')
    r = p.add_run(title + " ")
    r.bold = True
    p.add_run(desc)

# Section 6
add_heading_1("6. Lab Configuration in the Web LIS Dashboard")
p6 = doc.add_paragraph()
p6.add_run(
    "1. Open any web browser on the PC and go to http://localhost:8000 (login: admin / admin123).\n"
    "2. Navigate to 'Piysan Settings' (http://localhost:8000/piysan).\n"
    "3. Enter the new client lab's Mobile Number and Password (provided by Piysan admin), then click 'Save & Test Connection'.\n"
    "   -> The service automatically logs in, caches the JWT authentication token, and downloads the lab's official name!\n"
    "4. Ensure 'Auto-Submit to Piysan' is turned ON.\n"
    "5. Check 'Test Mapping' (/mapping): All 16 standard CBC parameters are pre-seeded and active out of the box."
)

# Section 7
add_heading_1("7. End-to-End Testing Procedure")
p7 = doc.add_paragraph()
p7.add_run("Verify the live installation following this 4-step testing routine:")

test_steps = [
    ("Step 1 - Fetch Bookings:", "On the Dashboard (/dashboard), click 'Sync Piysan Bookings'. Confirm the patient order appears in the list. Note the Reference Number (e.g. 202611a471ecaf)."),
    ("Step 2 - Run Sample on Machine:", "Place blood tube in Yumizen H500. Enter the exact Reference Number into the Sample ID / Barcode field. Press Start."),
    ("Step 3 - Automated ASTM Capture:", "Within 60 seconds of completion, the machine sends ASTM data to Port 5000. The Dashboard row turns green ('Ready to Push') with 16 decoded tests."),
    ("Step 4 - Push & Confirm Delivery:", "With Auto-Submit enabled, results push automatically to Piysan within 2 seconds. The badge shows 'Success' (HTTP 200). Confirm on https://www.piysan.com/.")
]

for title, desc in test_steps:
    p = doc.add_paragraph(style='List Bullet')
    r = p.add_run(title + " ")
    r.bold = True
    p.add_run(desc)

# Section 8
add_heading_1("8. Field Troubleshooting & Emergency Commands")

tbl_trouble = doc.add_table(rows=6, cols=2)
tbl_trouble.alignment = WD_TABLE_ALIGNMENT.CENTER
t_widths = [Inches(2.5), Inches(4.5)]

for col_idx, (text, w) in enumerate(zip(["Issue Encountered", "Solution / Action Required"], t_widths)):
    cell = tbl_trouble.cell(0, col_idx)
    cell.width = w
    set_cell_background(cell, "1E293B")
    set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
    p = cell.paragraphs[0]
    r = p.add_run(text)
    r.bold = True
    r.font.color.rgb = RGBColor(255, 255, 255)
    r.font.size = Pt(9.5)

trouble_data = [
    ("Installer says 'Python was not found on PATH'", "Python 3.11 is either not installed or was installed without checking 'Add python.exe to PATH'. Download Python 3.11.9 64-bit installer, choose Modify, check 'Add Python to environment variables', and restart PowerShell."),
    ("Analyzer displays 'Connection Failed / Timeout'", "Check Windows Firewall. Allow inbound TCP Port 5000 using: New-NetFirewallRule -DisplayName 'ASTM Port 5000' -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow"),
    ("manage_service.ps1 reports 'An instance is already running'", "Lingering process in memory. Run in Admin PowerShell: taskkill /F /IM pythonservice.exe /T ; taskkill /F /IM python.exe /T ; .\\manage_service.ps1 start"),
    ("Push results fails with 400 Bad Request", "Non-numeric test ID sent. The latest release automatically resolves all codes (WBC -> 4, HGB -> 1, etc.). Verify /mapping has active mappings."),
    ("Piysan login fails during connection test", "Check mobile/password at https://www.piysan.com/. Ensure lab account is active on production server.")
]

for row_idx, (issue, sol) in enumerate(trouble_data, start=1):
    bg = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
    for col_idx, text in enumerate([issue, sol]):
        cell = tbl_trouble.cell(row_idx, col_idx)
        cell.width = t_widths[col_idx]
        set_cell_background(cell, bg)
        set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
        p = cell.paragraphs[0]
        r = p.add_run(text)
        r.font.size = Pt(9)
        if col_idx == 0:
            r.bold = True

doc.save(DOCX_PATH_DATA)
doc.save(DOCX_PATH_ROOT)
print(f"Created Word Document: {DOCX_PATH_DATA}")
print(f"Copied to: {DOCX_PATH_ROOT}")
