# Digital NTTF AI Automation System
### Automated Assignment & Practice Test Solver powered by Playwright and Google Gemini AI

An enterprise-grade, modular browser automation system tailored for the **Digital NTTF** e-learning portal (`https://digitalnttf.com/library`).

---

## 🌟 Key Features

- **Multi-Activity Handling**: Seamlessly supports **Assignments**, **Practice Tests**, and **Skill Library Quizzes**.
- **Dynamic Activity Discovery**: Inspects the live website DOM to list available subjects, modules, assignments, and tests automatically without hard-coded names.
- **Smart Question Engine**: Handles **Multiple Choice (MCQ)**, **True/False**, **Checkbox**, **Dropdowns**, and **Subjective/Essay Rich Text Areas**.
- **Google Gemini Integration**: Uses `gemini-3.7-flash` via the official `google-genai` Python SDK with structured JSON prompts and confidence evaluation.
- **Strict Answer Validation**: Compares AI suggestions against real DOM options, matching normalized text and preventing misaligned selections.
- **Practice Test Timer Detection**: Monitors remaining time, with low-timer expedited modes.
- **Safety & Auto-Submit Guard**: `AUTO_SUBMIT=false` by default, pausing on a pre-submission review screen so you can inspect answers before final submission.
- **Zero Hard-Coded Credentials**: Securely loaded via `.env`.
- **Local SQLite Persistence**: Saves all runs, question histories, scores, error reports, and caches answers with SHA-256 to avoid redundant AI calls.
- **Crash & Interruption Recovery**: Interrupted activities can be resumed right where they left off.

---

## 🪟 Windows Setup & Installation (Step-by-Step)

Open **PowerShell** or **Command Prompt** and run:

```powershell
# 1. Navigate to the project directory
cd digitalnttf_ai

# 2. Create a Python virtual environment
python -m venv venv

# 3. Activate the virtual environment
# In PowerShell:
.\venv\Scripts\Activate.ps1
# Or in Command Prompt:
venv\Scripts\activate.bat

# 4. Install required Python packages
pip install -r requirements.txt

# 5. Install Playwright browser binaries (Chromium)
playwright install chromium

# 6. Configure your environment credentials
copy .env.example .env
```

Now open `.env` in Notepad or your editor and set:
```env
DIGITAL_NTTF_USERNAME=your_username
DIGITAL_NTTF_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
```

### Run the Application:
```bash
python main.py
```

---

## 🐧 Linux / macOS Setup

```bash
cd digitalnttf_ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env with your credentials
python3 main.py
```

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DIGITAL_NTTF_USERNAME` | *(Required)* | Your Digital NTTF student login ID / email |
| `DIGITAL_NTTF_PASSWORD` | *(Required)* | Your portal password |
| `GEMINI_API_KEY` | *(Required)* | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Gemini model name |
| `HEADLESS` | `false` | Set `false` to view browser actions live, `true` for background |
| `AUTO_SUBMIT` | `false` | `false` pauses before final submit; `true` auto-submits |
| `RESUME_ENABLED` | `true` | Enables auto-detection of interrupted runs |
| `GEMINI_REQUEST_DELAY` | `1.0` | Seconds delay between API calls |
| `AI_CONFIDENCE_THRESHOLD` | `0.60` | Threshold below which answers are marked for review |

---

## 📁 Architecture Overview

```
digitalnttf_ai/
├── main.py                # Interactive CLI control center
├── config.py              # Central config & fallback selectors
├── browser.py             # Playwright Chromium controller & screenshots
├── login.py               # Robust authentication manager
├── library.py             # Dynamic activity & topic discovery
├── assignment.py          # Assignment automation workflow
├── practice_test.py       # Practice test workflow & timer monitor
├── skill_quiz.py          # Skill library quiz runner
├── question_engine.py     # End-to-end question solving pipeline
├── question_parser.py     # Live DOM question and option parser
├── gemini_client.py       # Google Gemini API integration & caching
├── answer_validator.py    # Strict option and text validation
├── database.py            # SQLite database manager
├── recovery.py            # Session checkpoint & resumption
├── logger.py              # Secret-redacted file & console logging
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
└── digitalnttf.db         # Local SQLite storage (created on first run)
```
