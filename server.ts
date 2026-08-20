import express from "express";
import http from "http";
import path from "path";
import fs from "fs";
import { spawn, ChildProcess } from "child_process";
import { createServer as createViteServer } from "vite";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const server = http.createServer(app);
const PORT = Number(process.env.PORT) || 3000;

app.use(express.json());

// Automation Process State
interface AutomationState {
  status: "idle" | "running" | "completed" | "error" | "stopped";
  phase: "Idle" | "Login" | "Assignments" | "Practice Tests" | "Completed" | "Error" | "Stopped";
  chrome: "closed" | "initializing" | "connected";
  login: "pending" | "authenticated" | "failed";
  execution_mode: "local_visual" | "render_cloud";
  execution_location: "LOCAL WINDOWS" | "RENDER CLOUD";
  browser_visibility: "VISIBLE CHROME" | "HEADLESS CHROMIUM" | "WAITING FOR LOCAL AGENT" | "READY";
  local_agent_connected: boolean;
  current_subject: string;
  current_assignment: string;
  current_test: string;
  current_question: string;
  current_action: string;
  ai_provider: string;
  ai_model: string;
  assignments_completed: number;
  assignments_total: number;
  tests_completed: number;
  tests_total: number;
  progress: {
    answered: number;
    total: number;
    percentage: number;
  };
  errors: string[];
  logs: { time: string; message: string; type: string }[];
}

let automationProcess: ChildProcess | null = null;
let pendingAgentJob: any | null = null;
let lastAgentPingTime = 0;
let registeredAgentId = "";

let activeSessionCreds: {
  username?: string;
  password?: string;
  groqApiKey?: string;
  groqModel?: string;
  subject?: string;
  mode?: string;
  executionMode?: "local_visual" | "render_cloud";
} = {};

const state: AutomationState = {
  status: "idle",
  phase: "Idle",
  chrome: "closed",
  login: "pending",
  execution_mode: "local_visual",
  execution_location: "LOCAL WINDOWS",
  browser_visibility: "VISIBLE CHROME",
  local_agent_connected: false,
  current_subject: "All Subjects",
  current_assignment: "-",
  current_test: "-",
  current_question: "-",
  current_action: "Ready",
  ai_provider: "Groq",
  ai_model: "llama-3.3-70b-versatile",
  assignments_completed: 0,
  assignments_total: 0,
  tests_completed: 0,
  tests_total: 0,
  progress: {
    answered: 0,
    total: 0,
    percentage: 0
  },
  errors: [],
  logs: [
    { time: new Date().toLocaleTimeString(), message: "Digital NTTF Auto Solver ready. Enter credentials and click START.", type: "info" }
  ]
};

function isLocalAgentActive(): boolean {
  return registeredAgentId !== "" && Date.now() - lastAgentPingTime < 10000;
}

function sanitizeLog(message: string): string {
  let clean = message;
  if (activeSessionCreds.password && activeSessionCreds.password.length > 2) {
    clean = clean.replace(new RegExp(activeSessionCreds.password.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '********');
  }
  if (activeSessionCreds.groqApiKey && activeSessionCreds.groqApiKey.length > 5) {
    clean = clean.replace(new RegExp(activeSessionCreds.groqApiKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '[REDACTED_GROQ_KEY]');
  }
  clean = clean.replace(/gsk_[0-9A-Za-z]{20,}/g, '[REDACTED_GROQ_KEY]');
  return clean;
}

function addLog(message: string, type: "info" | "success" | "warning" | "error" = "info") {
  const time = new Date().toLocaleTimeString();
  const cleanMsg = sanitizeLog(message);
  state.logs.push({ time, message: cleanMsg, type });
  if (state.logs.length > 500) {
    state.logs.shift();
  }

  // Parse state updates and tag logs
  const lower = cleanMsg.toLowerCase();
  if (lower.includes("[browser_opened]") || lower.includes("visible chrome browser launched") || lower.includes("chrome window ready") || lower.includes("chrome browser window opened")) {
    state.chrome = "connected";
    state.current_action = "Browser Connected (Visible Chrome Window)";
  }
  if (lower.includes("headless browser launched") || lower.includes("headless chromium launched")) {
    state.chrome = "connected";
    state.current_action = "Browser Connected (Headless Cloud)";
  }
  if (lower.includes("state_login") || lower.includes("authenticating user") || lower.includes("[login_attempt]")) {
    state.phase = "Login";
    state.current_action = "Logging into Digital NTTF...";
  }
  if (lower.includes("login successful") || lower.includes("[login_success]") || lower.includes("authenticated")) {
    state.login = "authenticated";
    state.current_action = "Authenticated";
  }
  if (lower.includes("state_assignments") || lower.includes("opening assignments portal")) {
    state.phase = "Assignments";
    state.current_action = "Browsing Assignments...";
  }
  if (lower.includes("[subject]") || lower.includes("subject:") || lower.includes("processing subject")) {
    const match = message.match(/subject[^\:\'\"]*[\:\'\"]+([^'"]+)/i);
    if (match) state.current_subject = match[1].trim();
  }
  if (lower.includes("state_assignment_running") || lower.includes("starting assignment") || lower.includes("[assignment]")) {
    state.phase = "Assignments";
    state.current_action = "Solving Assignment...";
    const match = message.match(/assignment\s+(\d+\/\d+)[^\:\'\"]*[\:\'\"]+([^'"]+)/i);
    if (match) {
      state.current_assignment = `Assignment ${match[1]} - ${match[2]}`;
    } else {
      const match2 = message.match(/assignment[^\:\'\"]*[\:\'\"]+([^'"]+)/i);
      if (match2) state.current_assignment = match2[1].trim();
    }
  }
  if (lower.includes("verified completion of") && state.phase === "Assignments") {
    state.assignments_completed += 1;
    state.current_action = "Assignment Completed & Verified";
  }
  if (lower.includes("state_practice_tests") || lower.includes("opening practice tests portal")) {
    state.phase = "Practice Tests";
    state.current_action = "Browsing Practice Tests...";
  }
  if (lower.includes("state_test_running") || lower.includes("starting practice test") || lower.includes("[test]")) {
    state.phase = "Practice Tests";
    state.current_action = "Solving Practice Test...";
    const match = message.match(/practice test\s+(\d+\/\d+)[^\:\'\"]*[\:\'\"]+([^'"]+)/i);
    if (match) {
      state.current_test = `Test ${match[1]} - ${match[2]}`;
    } else {
      const match2 = message.match(/practice test[^\:\'\"]*[\:\'\"]+([^'"]+)/i);
      if (match2) state.current_test = match2[1].trim();
    }
  }
  if (lower.includes("verified completion of") && state.phase === "Practice Tests") {
    state.tests_completed += 1;
    state.current_action = "Practice Test Completed & Verified";
  }
  if (lower.includes("asking groq") || lower.includes("[ai_ready]") || lower.includes("groq_request")) {
    state.current_action = "Asking Groq AI...";
  }
  if (lower.includes("reading question") || lower.includes("[question]")) {
    state.current_action = "Reading Question...";
  }
  if (lower.includes("selecting option") || lower.includes("[answer_selected]") || lower.includes("answer_selected")) {
    state.current_action = "Selecting AI Answer in browser...";
    state.progress.answered += 1;
  }
  if (lower.includes("q") && lower.includes("question")) {
    const match = message.match(/Q(\d+(?:\/\d+)?)/i);
    if (match) state.current_question = `Q${match[1]}`;
  }
  if (lower.includes("error") || type === "error") {
    state.errors.push(message);
    if (state.errors.length > 50) state.errors.shift();
  }
}

// API Routes
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

app.get("/api/status", (req, res) => {
  const isAgentActive = isLocalAgentActive();
  const isRender = process.env.RENDER === "true" || Boolean(process.env.RENDER_SERVICE_ID);
  const isWindowsOrMac = process.platform === "win32" || process.platform === "darwin";

  let computedVisibility: "VISIBLE CHROME" | "HEADLESS CHROMIUM" | "WAITING FOR LOCAL AGENT" | "READY" = "VISIBLE CHROME";

  if (state.status === "running") {
    computedVisibility = state.execution_mode === "local_visual" ? "VISIBLE CHROME" : "HEADLESS CHROMIUM";
  } else {
    if (state.execution_mode === "local_visual") {
      if (isRender && !isAgentActive) {
        computedVisibility = "WAITING FOR LOCAL AGENT";
      } else if (isRender && isAgentActive) {
        computedVisibility = "READY";
      } else {
        computedVisibility = "VISIBLE CHROME";
      }
    } else {
      computedVisibility = "HEADLESS CHROMIUM";
    }
  }

  res.json({
    ...state,
    browser_visibility: computedVisibility,
    local_agent_connected: isAgentActive,
    registered_agent_id: isAgentActive ? registeredAgentId : null,
    sessionConfigured: Boolean(activeSessionCreds.username && activeSessionCreds.password && activeSessionCreds.groqApiKey),
    targetUrl: "https://digitalnttf.com"
  });
});

// Local Agent Heartbeat & Polling Endpoints
app.get("/api/agent/ping", (req, res) => {
  const agentId = String(req.query.agent_id || "");
  if (agentId) {
    registeredAgentId = agentId;
    lastAgentPingTime = Date.now();
  }
  res.json({ ok: true, timestamp: Date.now() });
});

app.get("/api/agent/poll", (req, res) => {
  const agentId = String(req.query.agent_id || "");
  if (!agentId || agentId !== registeredAgentId || !isLocalAgentActive()) {
    return res.status(403).json({ hasJob: false, error: "Unauthorized or unregistered agent" });
  }

  if (pendingAgentJob) {
    const job = pendingAgentJob;
    pendingAgentJob = null;
    return res.json({ hasJob: true, job });
  }
  res.json({ hasJob: false });
});

app.post("/api/agent/log", (req, res) => {
  const { message, type, agent_id } = req.body;
  if (agent_id && registeredAgentId && agent_id !== registeredAgentId) {
    return res.status(403).json({ ok: false, error: "Agent ID mismatch" });
  }
  if (message) {
    addLog(message, type || "info");
  }
  res.json({ ok: true });
});

app.post("/api/agent/status", (req, res) => {
  const { data, agent_id } = req.body;
  if (agent_id && registeredAgentId && agent_id !== registeredAgentId) {
    return res.status(403).json({ ok: false, error: "Agent ID mismatch" });
  }
  if (data) {
    if (data.phase) state.phase = data.phase;
    if (data.chrome) state.chrome = data.chrome;
    if (data.login) state.login = data.login;
    if (data.current_subject) state.current_subject = data.current_subject;
    if (data.current_assignment) state.current_assignment = data.current_assignment;
    if (data.current_test) state.current_test = data.current_test;
    if (data.current_question) state.current_question = data.current_question;
    if (data.current_action) state.current_action = data.current_action;
    if (typeof data.assignments_completed === "number") state.assignments_completed = data.assignments_completed;
    if (typeof data.assignments_total === "number") state.assignments_total = data.assignments_total;
    if (typeof data.tests_completed === "number") state.tests_completed = data.tests_completed;
    if (typeof data.tests_total === "number") state.tests_total = data.tests_total;
    if (data.progress) state.progress = { ...state.progress, ...data.progress };
  }
  res.json({ ok: true });
});

app.post("/api/agent/complete", (req, res) => {
  const { success, message, agent_id } = req.body;
  if (agent_id && registeredAgentId && agent_id !== registeredAgentId) {
    return res.status(403).json({ ok: false, error: "Agent ID mismatch" });
  }

  if (success) {
    state.status = "completed";
    state.phase = "Completed";
    state.chrome = "closed";
    state.current_action = "Automation Complete";
    addLog(">>> AUTOMATION COMPLETED SUCCESSFULLY", "success");
  } else {
    state.status = "error";
    state.phase = "Error";
    state.chrome = "closed";
    state.current_action = "Stopped with error";
    addLog(message || "Automation encountered an error", "warning");
  }
  activeSessionCreds = {};
  pendingAgentJob = null;
  res.json({ ok: true });
});

// Automation Start / Stop
app.post("/api/automation/start", (req, res) => {
  if (state.status === "running") {
    return res.json({ success: false, message: "Automation is already running" });
  }

  const { username, password, groqApiKey, groqModel, subject, mode, executionMode } = req.body;

  // Validation of mandatory user-provided fields
  const missing: string[] = [];
  const finalUsername = (username || "").trim();
  const finalPassword = (password || "").trim();
  const finalGroqApiKey = (groqApiKey || "").trim();
  const finalGroqModel = (groqModel || "llama-3.3-70b-versatile").trim();
  const finalSubject = (subject || "all").trim();
  const finalMode = (mode || "all").trim();
  const finalExecMode = (executionMode || "local_visual") as "local_visual" | "render_cloud";

  if (!finalUsername) missing.push("Digital NTTF Username");
  if (!finalPassword) missing.push("Digital NTTF Password");
  if (!finalGroqApiKey) missing.push("Groq API Key");

  if (missing.length > 0) {
    return res.status(400).json({
      success: false,
      message: `Please provide: ${missing.join(", ")}`
    });
  }

  const isRender = process.env.RENDER === "true" || Boolean(process.env.RENDER_SERVICE_ID);
  const isWindowsOrMac = process.platform === "win32" || process.platform === "darwin";

  // Check if Local Visual mode requested on Render but no Local Agent is active
  if (isRender && finalExecMode === "local_visual") {
    if (!isLocalAgentActive()) {
      return res.status(400).json({
        success: false,
        message: "Local Chrome Agent is not connected.\n\nStart 'local_agent/run_agent.bat' on your Windows computer, then click START AUTOMATION again."
      });
    }
  }

  activeSessionCreds = {
    username: finalUsername,
    password: finalPassword,
    groqApiKey: finalGroqApiKey,
    groqModel: finalGroqModel,
    subject: finalSubject,
    mode: finalMode,
    executionMode: finalExecMode
  };

  state.status = "running";
  state.phase = "Login";
  state.chrome = "initializing";
  state.login = "pending";
  state.execution_mode = finalExecMode;
  state.current_subject = finalSubject === "all" ? "All Subjects" : finalSubject;
  state.current_assignment = "-";
  state.current_test = "-";
  state.current_question = "-";
  state.ai_provider = "Groq";
  state.ai_model = finalGroqModel;
  state.assignments_completed = 0;
  state.assignments_total = 0;
  state.tests_completed = 0;
  state.tests_total = 0;
  state.progress = { answered: 0, total: 0, percentage: 0 };
  state.errors = [];

  if (finalExecMode === "local_visual") {
    state.execution_location = "LOCAL WINDOWS";
    state.browser_visibility = "VISIBLE CHROME";
    state.current_action = "Launching Visible Google Chrome on Windows...";
  } else {
    state.execution_location = "RENDER CLOUD";
    state.browser_visibility = "HEADLESS CHROMIUM";
    state.current_action = "Launching Headless Chromium on Cloud...";
  }

  addLog(`>>> START AUTOMATION: Initializing session for user '${finalUsername}' | Subject: ${finalSubject} | Mode: ${finalMode} | Target: ${state.execution_location} (${state.browser_visibility})`, "info");

  // CASE 1: Render Cloud Backend + Local Visual Chrome Requested -> Dispatch via Active Local Agent
  if (isRender && finalExecMode === "local_visual") {
    pendingAgentJob = {
      username: finalUsername,
      password: finalPassword,
      groqApiKey: finalGroqApiKey,
      groqModel: finalGroqModel,
      subject: finalSubject,
      mode: finalMode,
      assignedAgentId: registeredAgentId,
      timestamp: Date.now()
    };

    return res.json({
      success: true,
      message: "Job dispatched to Local Agent. Visible Chrome is opening on your Windows PC."
    });
  }

  // CASE 2: Running directly on local machine OR running Render Cloud mode directly on server
  const pythonScript = path.join(process.cwd(), "digitalnttf_ai", "main.py");
  const pythonCmd = process.platform === "win32" ? "python" : "python3";

  const isHeadless = finalExecMode === "render_cloud" || (isRender && !isWindowsOrMac) ? "true" : "false";

  const env = {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    HEADLESS: isHeadless,
    VISUAL_MODE: isHeadless === "false" ? "true" : "false",
    VISUAL_DELAY: "400",
    KEEP_BROWSER_OPEN: "true",
    BROWSER_CLOSE_DELAY: "30000",
    AUTO_SUBMIT: "true",
    CONTINUE_ON_ERROR: "false",
    BROWSER_SLOW_MO: isHeadless === "false" ? "500" : "0",
    BROWSER_CHANNEL: isHeadless === "false" && isWindowsOrMac ? "chrome" : "",
    TARGET_SUBJECT: finalSubject,
    AUTOMATION_MODE: finalMode,
    DIGITAL_NTTF_USERNAME: finalUsername,
    DIGITAL_NTTF_PASSWORD: finalPassword,
    GROQ_API_KEY: finalGroqApiKey,
    GROQ_MODEL: finalGroqModel
  };

  try {
    automationProcess = spawn(pythonCmd, [pythonScript], {
      cwd: path.join(process.cwd(), "digitalnttf_ai"),
      env
    });

    automationProcess.stdout?.on("data", (data) => {
      const lines = data.toString().split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed) {
          const type = trimmed.includes("ERROR") ? "error" : trimmed.includes("SUCCESS") || trimmed.includes("FINISHED") ? "success" : "info";
          addLog(trimmed, type);
        }
      }
    });

    automationProcess.stderr?.on("data", (data) => {
      const trimmed = data.toString().trim();
      if (trimmed) {
        addLog(`[STDERR] ${trimmed}`, "warning");
      }
    });

    automationProcess.on("close", (code) => {
      if (code === 0) {
        state.status = "completed";
        state.phase = "Completed";
        state.chrome = "closed";
        state.current_action = "Automation Complete";
        addLog(">>> AUTOMATION COMPLETED SUCCESSFULLY", "success");
      } else {
        if (state.status !== "stopped") {
          state.status = "error";
          state.phase = "Error";
          state.chrome = "closed";
          state.current_action = "Stopped with error";
          addLog(`Automation stopped with exit code ${code}`, "warning");
        }
      }
      automationProcess = null;
      activeSessionCreds = {};
    });

    res.json({ success: true, message: "Automation started successfully" });
  } catch (err: any) {
    state.status = "error";
    state.phase = "Error";
    state.chrome = "closed";
    activeSessionCreds = {};
    addLog(`Failed to launch python automation: ${err.message}`, "error");
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post("/api/automation/stop", (req, res) => {
  activeSessionCreds = {};
  pendingAgentJob = null;
  if (automationProcess) {
    automationProcess.kill("SIGINT");
    setTimeout(() => {
      if (automationProcess) {
        automationProcess.kill("SIGKILL");
        automationProcess = null;
      }
    }, 2000);
  }
  state.status = "stopped";
  state.phase = "Stopped";
  state.chrome = "closed";
  state.current_action = "Automation Stopped";
  addLog(">>> STOP AUTOMATION: Process terminated by user.", "warning");
  return res.json({ success: true, message: "Automation stopped" });
});

app.post("/api/automation/clear-logs", (req, res) => {
  state.logs = [];
  res.json({ success: true });
});

// Setup Vite or Static serving
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        hmr: {
          server,
        },
      },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  server.listen(PORT, "0.0.0.0", () => {
    console.log(`Digital NTTF Auto Solver running on http://localhost:${PORT}`);
  });
}

startServer();
