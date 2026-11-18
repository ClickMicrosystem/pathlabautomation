# HORIBA Yumizen H500 / H500E ASTM LIS Integration
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
