"""
Digital NTTF Local Automation Agent
Runs locally on Windows to open a real, visible Google Chrome window (headless=False)
and communicate live status & logs with the Digital NTTF web dashboard.
"""

import sys
import os
import re
import time
import json
import argparse
import subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] 'requests' package not found. Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "playwright", "groq"])
    import requests

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
AI_DIR = PROJECT_DIR / "digitalnttf_ai"

# Ensure digitalnttf_ai is in Python path so existing modules are imported directly without code duplication
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

class LocalAgent:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip("/")
        self.agent_id = f"win_agent_{int(time.time())}"
        self.is_running = False
        self.current_process = None

    def ping(self) -> bool:
        """Send heartbeat to server and register active agent ID."""
        try:
            res = requests.get(f"{self.server_url}/api/agent/ping", params={"agent_id": self.agent_id}, timeout=3)
            return res.status_code == 200
        except Exception:
            return False

    def send_log(self, message: str, log_type: str = "info"):
        """Forward local log line to server dashboard."""
        try:
            requests.post(
                f"{self.server_url}/api/agent/log",
                json={"message": message, "type": log_type, "agent_id": self.agent_id},
                timeout=3
            )
        except Exception:
            pass

    def send_status_update(self, data: dict):
        """Update live status in the web UI."""
        try:
            requests.post(
                f"{self.server_url}/api/agent/status",
                json={"data": data, "agent_id": self.agent_id},
                timeout=3
            )
        except Exception:
            pass

    def notify_completion(self, success: bool, message: str = ""):
        """Notify server that local automation has completed."""
        try:
            requests.post(
                f"{self.server_url}/api/agent/complete",
                json={"success": success, "message": message, "agent_id": self.agent_id},
                timeout=3
            )
        except Exception:
            pass

    def poll_for_job(self) -> dict:
        """Check for pending start request from server."""
        try:
            res = requests.get(f"{self.server_url}/api/agent/poll", params={"agent_id": self.agent_id}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get("hasJob"):
                    return data.get("job", {})
        except Exception:
            pass
        return {}

    def execute_job(self, job: dict):
        """Execute Digital NTTF automation locally in real visible Google Chrome."""
        print("\n" + "="*60)
        print(" [LOCAL AGENT] RECEIVED AUTOMATION JOB")
        print(" Launching local visible Google Chrome...")
        print("="*60)

        username = job.get("username", "")
        password = job.get("password", "")
        groq_key = job.get("groqApiKey", "")
        groq_model = job.get("groqModel", "llama-3.3-70b-versatile")
        subject = job.get("subject", "all")
        mode = job.get("mode", "all")

        auto_submit_val = str(job.get("autoSubmit", False)).lower()

        # Environment configuration strictly for Local Visible Chrome
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "HEADLESS": "false",
            "VISUAL_MODE": "true",
            "BROWSER_CHANNEL": "chrome",
            "BROWSER_SLOW_MO": "500",
            "VISUAL_DELAY": "400",
            "KEEP_BROWSER_OPEN": "true",
            "BROWSER_CLOSE_DELAY": "30000",
            "AUTO_SUBMIT": "false" if auto_submit_val in ("false", "0", "") else auto_submit_val,
            "CONTINUE_ON_ERROR": "false",
            "DIGITAL_NTTF_USERNAME": username,
            "DIGITAL_NTTF_PASSWORD": password,
            "GROQ_API_KEY": groq_key,
            "GROQ_MODEL": groq_model,
            "TARGET_SUBJECT": subject,
            "AUTOMATION_MODE": mode,
        }

        self.send_log(f"[LOCAL_AGENT] Starting Local Visible Chrome for user '{username}'...", "info")
        self.send_log("[START] Headless: False | Visual mode: True | Browser channel: chrome", "info")

        python_cmd = sys.executable
        main_script = str(AI_DIR / "main.py")

        try:
            self.current_process = subprocess.Popen(
                [python_cmd, main_script],
                cwd=str(AI_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in iter(self.current_process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    print(clean_line)
                    log_type = "error" if "ERROR" in clean_line else "success" if ("SUCCESS" in clean_line or "FINISHED" in clean_line or "VERIFIED" in clean_line) else "info"
                    self.send_log(clean_line, log_type)

                    # Parse stdout for rich status updates
                    status_update = {}
                    if "STATE_LOGIN" in clean_line:
                        status_update = {"phase": "Login", "current_action": "Logging in to Digital NTTF..."}
                    elif "STATE_ASSIGNMENTS" in clean_line:
                        status_update = {"phase": "Assignments", "current_action": "Opening Assignments portal..."}
                    elif "STATE_ASSIGNMENT_RUNNING" in clean_line:
                        match = re.search(r"Starting Assignment\s+(\d+/\d+):\s*['\"]([^'\"]+)['\"]", clean_line)
                        if match:
                            status_update = {
                                "phase": "Assignments",
                                "current_assignment": f"Assignment {match.group(1)} - {match.group(2)}",
                                "current_action": f"Solving Assignment {match.group(1)}: {match.group(2)}"
                            }
                    elif "STATE_PRACTICE_TESTS" in clean_line:
                        status_update = {"phase": "Practice Tests", "current_action": "Opening Practice Tests portal..."}
                    elif "STATE_TEST_RUNNING" in clean_line:
                        match = re.search(r"Starting Practice Test\s+(\d+/\d+):\s*['\"]([^'\"]+)['\"]", clean_line)
                        if match:
                            status_update = {
                                "phase": "Practice Tests",
                                "current_test": f"Test {match.group(1)} - {match.group(2)}",
                                "current_action": f"Solving Practice Test {match.group(1)}: {match.group(2)}"
                            }
                    elif "QUESTION_LIST" in clean_line:
                        match = re.search(r"Detected (\d+) question", clean_line)
                        if match:
                            status_update = {"current_action": f"Detected {match.group(1)} questions in assignment"}
                    elif "QUESTION" in clean_line and ("Processing Question" in clean_line or "Opening Question" in clean_line):
                        match = re.search(r"Question #?(\d+)(?:/(\d+))?", clean_line)
                        if match:
                            q_num = match.group(1)
                            total_q = f"/{match.group(2)}" if match.group(2) else ""
                            status_update = {"current_question": f"Q{q_num}{total_q}", "current_action": f"Processing Question {q_num}{total_q}"}
                    elif "QUESTION_READ" in clean_line:
                        match = re.search(r"Q(\d+(?:/\d+)?)", clean_line)
                        if match:
                            status_update = {"current_question": f"Q{match.group(1)}", "current_action": f"Reading Question {match.group(1)}"}
                    elif "QUESTION_COMPLETED" in clean_line:
                        match = re.search(r"Question #?(\d+/\d+)", clean_line)
                        if match:
                            status_update = {"current_action": f"Completed Question {match.group(1)}"}
                    elif "FULLSCREEN" in clean_line:
                        status_update = {"current_action": "Fullscreen: Active"}
                    elif "CURRENT_ACTION" in clean_line:
                        action_text = clean_line.split("CURRENT_ACTION")[-1].strip(" :-\t")
                        if action_text:
                            status_update = {"current_action": action_text}
                    elif "ANSWER_SELECTED" in clean_line:
                        status_update = {"current_action": "Selected Groq AI Answer in Chrome"}

                    if status_update:
                        self.send_status_update(status_update)

            self.current_process.wait()
            rc = self.current_process.returncode

            if rc == 0:
                print("\n[LOCAL AGENT] Local automation completed successfully.")
                self.send_log("[LOCAL_AGENT] Automation completed successfully.", "success")
                self.notify_completion(True, "All automation activities completed successfully.")
            else:
                print(f"\n[LOCAL AGENT] Automation ended with code {rc}.")
                self.send_log(f"[LOCAL_AGENT] Automation ended with code {rc}.", "warning")
                self.notify_completion(False, f"Process ended with code {rc}")

        except Exception as e:
            err_msg = f"Local execution error: {e}"
            print(f"[!] {err_msg}")
            self.send_log(f"[ERROR] {err_msg}", "error")
            self.notify_completion(False, err_msg)
        finally:
            self.current_process = None
            # Wipe in-memory sensitive variables
            job.clear()
            env.clear()

    def run(self):
        """Main local agent listener loop with heartbeat."""
        print("="*60)
        print("       DIGITAL NTTF LOCAL VISIBLE CHROME AGENT")
        print("="*60)
        print(f" Target Server:  {self.server_url}")
        print(f" Agent ID:       {self.agent_id}")
        print(" Mode:           REAL VISIBLE CHROME (headless=False)")
        print("="*60)
        print("\nConnecting to dashboard...")

        connected = False
        while not connected:
            if self.ping():
                connected = True
                print(f"\nConnected to:\n{self.server_url}\n")
                print(f"Agent ID:\n{self.agent_id}\n")
                print("Status:\nREADY")
                print("\nWaiting for 'START AUTOMATION' click in the web UI...\n")
                self.send_log(f"[LOCAL_AGENT] Local Agent ({self.agent_id}) connected and ready for Visible Chrome automation.", "success")
            else:
                print(f"[...] Waiting to reach {self.server_url}... (Retrying in 3s)")
                time.sleep(3)

        last_ping_time = time.time()
        while True:
            try:
                # Periodic heartbeat ping every 3 seconds
                if time.time() - last_ping_time > 3:
                    self.ping()
                    last_ping_time = time.time()

                job = self.poll_for_job()
                if job:
                    self.execute_job(job)
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n[!] Local agent stopped by user.")
                break
            except Exception as e:
                print(f"[!] Agent polling error: {e}")
                time.sleep(2)

def main():
    parser = argparse.ArgumentParser(description="Digital NTTF Local Automation Agent")
    parser.add_argument("--server", type=str, default="http://localhost:3000", help="Web dashboard server URL (e.g. http://localhost:3000 or https://your-render-app.onrender.com)")
    args = parser.parse_args()

    agent = LocalAgent(args.server)
    agent.run()

if __name__ == "__main__":
    main()
