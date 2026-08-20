# Digital NTTF Local Visible Chrome Agent

This lightweight agent runs on your Windows PC and executes the Digital NTTF automation in a **real, visible Google Chrome window** (`headless=False`) while syncing progress and logs directly with your web dashboard.

---

## 🚀 Quick Start (Windows)

### Option 1: Double-click `run_agent.bat`
1. Double-click `run_agent.bat`.
2. Enter your server URL (or press Enter for default `http://localhost:3000`, or enter your deployed Render URL like `https://your-app.onrender.com`).
3. Open your web dashboard, enter your credentials, and click **START AUTOMATION**.
4. A real Google Chrome window will immediately appear on your screen and solve your assignments and practice tests.

### Option 2: Run via PowerShell / Command Prompt
```powershell
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Start agent (connected to local server or Render)
python agent.py --server http://localhost:3000
# OR for Render:
# python agent.py --server https://your-app.onrender.com
```

---

## 🔒 Security Guarantee
- Credentials & API keys are passed in-memory during active execution.
- Sensitive values (passwords, tokens, keys) are never written to disk or logs.
- Memory is immediately purged upon job completion.
