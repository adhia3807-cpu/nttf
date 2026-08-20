# Digital NTTF AI Auto Solver

A fast, sequential browser automation system for **Digital NTTF** assignments and practice tests powered by **Playwright** and **Groq AI**.

## 🚀 Features

- **Sequential Automation**: Executes assignments and practice tests strictly one by one.
- **Groq AI Answering**: Fast response generation using Groq's high-speed inference engine (`llama-3.3-70b-versatile`).
- **Dynamic Question Answering**: Supports MCQ, True/False, Checkbox, and Subjective questions with option validation and normalization.
- **Modern Web Dashboard**: Real-time status tracking, credential & Groq API key configuration, live console logs, and stop controls.
- **Zero Hardcoding**: Credentials and API keys are provided via the UI and kept in memory during the active session.

---

## 🛠️ Prerequisites

1. **Node.js** (v18 or higher)
2. **Python** (v3.9 or higher)
3. **Google Chrome** / Chromium

---

## 📦 Installation & Setup

### 1. Install Node Dependencies
```bash
npm install
```

### 2. Install Python Automation Dependencies
```bash
pip install -r digitalnttf_ai/requirements.txt
playwright install chromium
```

---

## 🖥️ Running the Application

Start the web dashboard & backend server:

```bash
npm run dev
```

Open your browser at `http://localhost:3000`.

1. Enter your **Digital NTTF Username**.
2. Enter your **Digital NTTF Password**.
3. Enter your **Groq API Key** (`gsk_...`).
4. (Optional) Choose a Groq Model (default: `llama-3.3-70b-versatile`).
5. Click **START AUTOMATION**.

---

## 📁 Project Structure

```text
├── digitalnttf_ai/            # Python Playwright & Groq Automation Core
│   ├── main.py                # Sequential state machine entrypoint
│   ├── groq_client.py         # Groq AI answer client & JSON parser
│   ├── browser.py             # Playwright browser controller
│   ├── question_engine.py     # Question detector & answer pipeline
│   ├── assignment.py          # Assignment runner & submission verifier
│   ├── practice_test.py       # Practice test runner & score verifier
│   ├── library.py             # Library course & activity scanner
│   ├── login.py               # Auto-login handler
│   └── requirements.txt       # Python dependencies
├── src/                       # React Web Dashboard
│   ├── App.tsx                # Status dashboard & credential inputs
│   └── types.ts               # TypeScript interfaces
├── server.ts                  # Express + Vite full-stack server
├── package.json               # Node packages and run scripts
└── README.md
```
