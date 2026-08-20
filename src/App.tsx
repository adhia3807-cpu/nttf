import React, { useState, useEffect, useRef } from "react";
import {
  Play,
  Square,
  Key,
  User,
  Cpu,
  Globe,
  Terminal,
  Activity,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Clock,
  Sparkles,
  Layers,
  Sliders,
  Monitor,
  Cloud,
  Eye,
  Laptop,
  HelpCircle,
  Radio,
  Copy,
  Check,
  Zap,
  ArrowRight
} from "lucide-react";
import { AutomationStatusResponse } from "./types";

export function App() {
  const [data, setData] = useState<AutomationStatusResponse>({
    status: "idle",
    phase: "Idle",
    chrome: "closed",
    login: "pending",
    execution_mode: "local_visual",
    execution_location: "LOCAL WINDOWS",
    browser_visibility: "VISIBLE CHROME",
    local_agent_connected: false,
    registered_agent_id: null,
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
      percentage: 0,
    },
    errors: [],
    logs: [
      {
        time: new Date().toLocaleTimeString(),
        message: "Digital NTTF Auto Solver ready. Enter credentials and click START AUTOMATION.",
        type: "info",
      },
    ],
    targetUrl: "https://digitalnttf.com",
  });

  // User credential & API key inputs (In-memory for security)
  const [username, setUsername] = useState(() => localStorage.getItem("nttf_remembered_username") || "");
  const [password, setPassword] = useState("");
  const [groqApiKey, setGroqApiKey] = useState("");
  const [groqModel, setGroqModel] = useState(() => localStorage.getItem("nttf_remembered_model") || "llama-3.3-70b-versatile");
  const [subject, setSubject] = useState("all");
  const [mode, setMode] = useState("all");
  const [executionMode, setExecutionMode] = useState<"local_visual" | "render_cloud">("local_visual");
  const [rememberUsername, setRememberUsername] = useState(() => Boolean(localStorage.getItem("nttf_remembered_username")));
  const [rememberModel, setRememberModel] = useState(() => Boolean(localStorage.getItem("nttf_remembered_model")));

  const [validationError, setValidationError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [showAgentHelp, setShowAgentHelp] = useState(false);
  const [copiedCommand, setCopiedCommand] = useState(false);

  const serverOrigin = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";
  const agentCommand = `python local_agent/agent.py --server ${serverOrigin}`;

  const handleCopyCommand = () => {
    navigator.clipboard.writeText(agentCommand);
    setCopiedCommand(true);
    setTimeout(() => setCopiedCommand(false), 2500);
  };

  const handleSwitchToCloud = () => {
    setExecutionMode("render_cloud");
    setValidationError(null);
  };

  const logsContainerRef = useRef<HTMLDivElement>(null);

  // Poll status from backend
  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const json: AutomationStatusResponse = await res.json();
        setData(json);
      }
    } catch {
      // Backend polling error
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [data.logs]);

  const handleStartAutomation = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);

    // Validate all required fields
    if (!username.trim()) {
      setValidationError("Please enter your Digital NTTF username.");
      return;
    }
    if (!password.trim()) {
      setValidationError("Please enter your Digital NTTF password.");
      return;
    }
    if (!groqApiKey.trim()) {
      setValidationError("Please enter your Groq API key.");
      return;
    }

    // Handle optional remember choices
    if (rememberUsername) {
      localStorage.setItem("nttf_remembered_username", username.trim());
    } else {
      localStorage.removeItem("nttf_remembered_username");
    }

    if (rememberModel && groqModel.trim()) {
      localStorage.setItem("nttf_remembered_model", groqModel.trim());
    } else {
      localStorage.removeItem("nttf_remembered_model");
    }

    setIsProcessing(true);
    try {
      const res = await fetch("/api/automation/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          password: password.trim(),
          groqApiKey: groqApiKey.trim(),
          groqModel: groqModel.trim() || "llama-3.3-70b-versatile",
          subject: subject.trim(),
          mode: mode.trim(),
          executionMode: executionMode,
        }),
      });

      const resJson = await res.json();
      if (!res.ok || resJson.success === false) {
        setValidationError(resJson.message || "Failed to start automation");
      } else {
        await fetchStatus();
      }
    } catch (err: any) {
      setValidationError(err.message || "Network error launching automation");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStopAutomation = async () => {
    setIsProcessing(true);
    try {
      await fetch("/api/automation/stop", { method: "POST" });
      await fetchStatus();
    } catch (err) {
      console.error(err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClearLogs = async () => {
    try {
      await fetch("/api/automation/clear-logs", { method: "POST" });
      fetchStatus();
    } catch {
      // ignore
    }
  };

  const isRunning = data.status === "running";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-slate-950">
      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-30 px-6 py-4">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white flex items-center space-x-2">
                <span>DIGITAL NTTF AUTO SOLVER</span>
                <span className="text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  Groq AI
                </span>
              </h1>
              <p className="text-xs text-slate-400 flex items-center space-x-2 mt-0.5">
                <Globe className="w-3.5 h-3.5 text-slate-500" />
                <span>Portal: digitalnttf.com</span>
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            {/* Local Agent Status */}
            <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
              <span
                className={`w-2 h-2 rounded-full ${
                  data.local_agent_connected ? "bg-emerald-400" : "bg-amber-400"
                }`}
              ></span>
              <span className="text-slate-400 font-medium">LOCAL AGENT:</span>
              <span className={data.local_agent_connected ? "text-emerald-400 font-bold uppercase" : "text-amber-400 font-bold uppercase"}>
                {data.local_agent_connected ? "CONNECTED" : "NOT CONNECTED"}
              </span>
            </div>

            {/* Browser Visibility Badge */}
            <div className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
              <Eye className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-slate-400 font-medium">Browser:</span>
              <span
                className={
                  data.browser_visibility === "VISIBLE CHROME"
                    ? "text-emerald-400 font-bold"
                    : data.browser_visibility === "READY"
                    ? "text-cyan-400 font-bold"
                    : data.browser_visibility === "WAITING FOR LOCAL AGENT"
                    ? "text-amber-400 font-bold"
                    : "text-purple-400 font-bold"
                }
              >
                {data.browser_visibility || "VISIBLE CHROME"}
              </span>
            </div>

            {/* Automation Status */}
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
              <span
                className={`w-2 h-2 rounded-full ${
                  isRunning ? "bg-cyan-400 animate-pulse" : "bg-emerald-400"
                }`}
              ></span>
              <span className="text-slate-400 font-medium">Status:</span>
              <span className={isRunning ? "text-cyan-400 font-bold uppercase" : "text-emerald-400 font-bold uppercase"}>
                {data.status}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl w-full mx-auto p-6 flex-1 flex flex-col gap-6">
        {/* Conditional Layout: Configuration Form vs Active Running Dashboard */}
        {!isRunning ? (
          /* =======================================================
             CONFIGURATION & START SCREEN
             ======================================================= */
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 sm:p-8 shadow-2xl">
            <div className="max-w-2xl mx-auto space-y-6">
              <div className="text-center space-y-2 border-b border-slate-800 pb-5">
                <h2 className="text-2xl font-bold tracking-tight text-white">
                  Digital NTTF Auto Solver
                </h2>
                <p className="text-xs sm:text-sm text-slate-300">
                  Select your execution mode below. Local Visual Mode launches a real Google Chrome window on your Windows PC to answer questions sequentially with Groq AI.
                </p>
              </div>

              {validationError && (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs space-y-3">
                  <div className="flex items-start space-x-2.5">
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
                    <div className="font-semibold leading-relaxed whitespace-pre-line">{validationError}</div>
                  </div>

                  {validationError.includes("Local Chrome Agent is not connected") && (
                    <div className="pt-2 border-t border-rose-500/20 space-y-3">
                      <div className="flex flex-col sm:flex-row gap-2">
                        {/* Action 1: Switch to Cloud Mode */}
                        <button
                          type="button"
                          onClick={handleSwitchToCloud}
                          className="flex-1 py-2 px-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs flex items-center justify-center space-x-2 transition shadow-md"
                        >
                          <Zap className="w-3.5 h-3.5" />
                          <span>Switch to Cloud Mode (Run Instantly)</span>
                        </button>

                        {/* Action 2: Copy Local Agent Command */}
                        <button
                          type="button"
                          onClick={handleCopyCommand}
                          className="flex-1 py-2 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-cyan-500/30 font-bold text-xs flex items-center justify-center space-x-2 transition"
                        >
                          {copiedCommand ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                              <span className="text-emerald-400">Copied to Clipboard!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy Windows Command</span>
                            </>
                          )}
                        </button>
                      </div>

                      <div className="p-2.5 rounded bg-slate-950/80 border border-slate-800 font-mono text-[11px] text-slate-300 select-all overflow-x-auto">
                        <code>{agentCommand}</code>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <form onSubmit={handleStartAutomation} className="space-y-5">
                {/* Execution Mode Selector */}
                <div className="space-y-2 bg-slate-950/60 p-4 rounded-xl border border-slate-800">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-200 flex items-center space-x-1.5">
                      <Monitor className="w-4 h-4 text-cyan-400" />
                      <span>Execution Mode</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => setShowAgentHelp(!showAgentHelp)}
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 flex items-center space-x-1"
                    >
                      <HelpCircle className="w-3.5 h-3.5" />
                      <span>{showAgentHelp ? "Hide Local Agent Guide" : "How to connect Local Agent?"}</span>
                    </button>
                  </div>

                  {showAgentHelp && (
                    <div className="p-3 rounded-lg bg-slate-900 border border-cyan-500/30 text-[11px] text-slate-300 space-y-2">
                      <p className="font-bold text-cyan-300">How to run with Visible Chrome on Windows:</p>
                      <ol className="list-decimal list-inside space-y-1 text-slate-400">
                        <li>Open the project folder on your Windows computer.</li>
                        <li>Double-click <code className="text-cyan-300 font-mono">local_agent/run_agent.bat</code> (or run <code className="text-cyan-300 font-mono">python local_agent/agent.py --server {window.location.origin}</code>).</li>
                        <li>The status badge at top will switch to <span className="text-emerald-400 font-bold">LOCAL AGENT: CONNECTED</span>.</li>
                        <li>Enter your credentials and click <span className="text-cyan-400 font-bold">START AUTOMATION</span>.</li>
                      </ol>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    {/* Option 1: Local Visual Chrome */}
                    <div
                      onClick={() => setExecutionMode("local_visual")}
                      className={`cursor-pointer p-3.5 rounded-xl border transition-all flex items-start space-x-3 ${
                        executionMode === "local_visual"
                          ? "bg-cyan-500/10 border-cyan-500/50 shadow-md shadow-cyan-500/10"
                          : "bg-slate-900 border-slate-800 hover:border-slate-700 opacity-80"
                      }`}
                    >
                      <input
                        type="radio"
                        name="execMode"
                        checked={executionMode === "local_visual"}
                        onChange={() => setExecutionMode("local_visual")}
                        className="mt-0.5 text-cyan-500 focus:ring-cyan-500"
                      />
                      <div>
                        <div className="text-xs font-bold text-slate-100 flex items-center space-x-1.5">
                          <Eye className="w-3.5 h-3.5 text-cyan-400" />
                          <span>Local Visual Chrome</span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                          Opens real Google Chrome on your PC desktop. Visible DOM clicks & highlights.
                        </p>
                      </div>
                    </div>

                    {/* Option 2: Render Cloud */}
                    <div
                      onClick={() => setExecutionMode("render_cloud")}
                      className={`cursor-pointer p-3.5 rounded-xl border transition-all flex items-start space-x-3 ${
                        executionMode === "render_cloud"
                          ? "bg-purple-500/10 border-purple-500/50 shadow-md shadow-purple-500/10"
                          : "bg-slate-900 border-slate-800 hover:border-slate-700 opacity-80"
                      }`}
                    >
                      <input
                        type="radio"
                        name="execMode"
                        checked={executionMode === "render_cloud"}
                        onChange={() => setExecutionMode("render_cloud")}
                        className="mt-0.5 text-purple-500 focus:ring-purple-500"
                      />
                      <div>
                        <div className="text-xs font-bold text-slate-100 flex items-center space-x-1.5">
                          <Cloud className="w-3.5 h-3.5 text-purple-400" />
                          <span>Render Cloud</span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                          Runs headless in cloud container without opening a desktop window.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Username Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                    <span>Digital NTTF Username / Email</span>
                    <span className="text-[10px] text-rose-400 font-normal">*Required</span>
                  </label>
                  <div className="flex items-center space-x-2 bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 focus-within:border-cyan-500 transition">
                    <User className="w-4 h-4 text-slate-400 shrink-0" />
                    <input
                      id="input-username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="Student Roll No / Email / Username"
                      className="bg-transparent text-slate-100 placeholder-slate-500 focus:outline-none w-full text-xs"
                    />
                  </div>
                </div>

                {/* Password Input (Hidden in UI & never saved to storage) */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                    <span>Digital NTTF Password</span>
                    <span className="text-[10px] text-rose-400 font-normal">*Required (Session In-Memory)</span>
                  </label>
                  <div className="flex items-center space-x-2 bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 focus-within:border-cyan-500 transition">
                    <Key className="w-4 h-4 text-slate-400 shrink-0" />
                    <input
                      id="input-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      className="bg-transparent text-slate-100 placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
                    />
                  </div>
                </div>

                {/* Subject and Mode Options */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Subject Filter */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                      <Layers className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Subject Selection</span>
                    </label>
                    <select
                      id="select-subject"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      className="w-full bg-slate-950 text-slate-100 px-3.5 py-2.5 rounded-xl border border-slate-800 focus:outline-none focus:border-cyan-500 text-xs"
                    >
                      <option value="all">All Subjects (Auto Detect All)</option>
                      <option value="Advanced PLC">Advanced PLC</option>
                      <option value="Robotics">Robotics</option>
                      <option value="CNC Technology">CNC Technology (CP15 Sem5)</option>
                      <option value="Product Design & Development">Product Design & Development</option>
                    </select>
                  </div>

                  {/* Mode Filter */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                      <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                      <span>Activity Mode</span>
                    </label>
                    <select
                      id="select-mode"
                      value={mode}
                      onChange={(e) => setMode(e.target.value)}
                      className="w-full bg-slate-950 text-slate-100 px-3.5 py-2.5 rounded-xl border border-slate-800 focus:outline-none focus:border-cyan-500 text-xs"
                    >
                      <option value="all">All Activities (Assignments & Tests)</option>
                      <option value="assignments_only">Assignments Only</option>
                      <option value="tests_only">Practice Tests Only</option>
                    </select>
                  </div>
                </div>

                {/* Groq API Key Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                    <span>Groq API Key</span>
                    <span className="text-[10px] text-rose-400 font-normal">*Required (Session In-Memory)</span>
                  </label>
                  <div className="flex items-center space-x-2 bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 focus-within:border-cyan-500 transition">
                    <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
                    <input
                      id="input-groq-key"
                      type="password"
                      value={groqApiKey}
                      onChange={(e) => setGroqApiKey(e.target.value)}
                      placeholder="gsk_..."
                      className="bg-transparent text-slate-100 placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
                    />
                  </div>
                </div>

                {/* Groq Model Selector */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                    <span>Groq Model</span>
                    <span className="text-[10px] text-cyan-400 font-normal">Active Groq API Models</span>
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <select
                      id="select-groq-preset"
                      value={[
                        "llama-3.3-70b-versatile",
                        "llama-3.1-8b-instant",
                        "llama-3.1-70b-versatile",
                        "llama3-70b-8192",
                        "mixtral-8x7b-32768",
                        "gemma2-9b-it"
                      ].includes(groqModel) ? groqModel : "custom"}
                      onChange={(e) => {
                        if (e.target.value !== "custom") {
                          setGroqModel(e.target.value);
                        }
                      }}
                      className="bg-slate-950 text-slate-100 px-3.5 py-2.5 rounded-xl border border-slate-800 focus:outline-none focus:border-cyan-500 text-xs"
                    >
                      <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile (Recommended)</option>
                      <option value="llama-3.1-8b-instant">llama-3.1-8b-instant (Fastest)</option>
                      <option value="llama-3.1-70b-versatile">llama-3.1-70b-versatile</option>
                      <option value="llama3-70b-8192">llama3-70b-8192</option>
                      <option value="mixtral-8x7b-32768">mixtral-8x7b-32768</option>
                      <option value="gemma2-9b-it">gemma2-9b-it</option>
                      <option value="custom">Custom Model Name...</option>
                    </select>

                    <div className="flex items-center space-x-2 bg-slate-950 px-3.5 py-2.5 rounded-xl border border-slate-800 focus-within:border-cyan-500 transition">
                      <Cpu className="w-4 h-4 text-slate-400 shrink-0" />
                      <input
                        id="input-groq-model"
                        type="text"
                        value={groqModel}
                        onChange={(e) => setGroqModel(e.target.value)}
                        placeholder="e.g. llama-3.3-70b-versatile"
                        className="bg-transparent text-slate-100 placeholder-slate-500 focus:outline-none w-full text-xs font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* Remember Checkboxes */}
                <div className="flex flex-wrap items-center gap-6 pt-1 text-xs text-slate-400">
                  <label className="flex items-center space-x-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={rememberUsername}
                      onChange={(e) => setRememberUsername(e.target.checked)}
                      className="rounded border-slate-700 text-cyan-500 focus:ring-cyan-500 bg-slate-950"
                    />
                    <span>Remember username</span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={rememberModel}
                      onChange={(e) => setRememberModel(e.target.checked)}
                      className="rounded border-slate-700 text-cyan-500 focus:ring-cyan-500 bg-slate-950"
                    />
                    <span>Remember Groq model</span>
                  </label>
                </div>

                {/* Main START Button */}
                <div className="pt-2">
                  <button
                    id="btn-start-automation"
                    type="submit"
                    disabled={isProcessing}
                    className="w-full py-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-extrabold text-sm tracking-wider flex items-center justify-center space-x-3 shadow-xl shadow-cyan-500/20 transition-all transform hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50"
                  >
                    <Play className="w-5 h-5 fill-slate-950" />
                    <span>START AUTOMATION</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : (
          /* =======================================================
             ACTIVE RUNNING STATUS DASHBOARD
             ======================================================= */
          <div className="space-y-6">
            {/* Running Header Banner with Stop Button */}
            <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
                  <h2 className="text-xl font-bold text-white tracking-tight">
                    AUTOMATION RUNNING ({data.browser_visibility || "VISIBLE CHROME"})
                  </h2>
                </div>
                <p className="text-xs text-slate-300 mt-1">
                  Sequential Execution: Processing activities one by one in {data.execution_location || "LOCAL WINDOWS"} with Groq AI.
                </p>
              </div>

              <button
                id="btn-stop-automation"
                onClick={handleStopAutomation}
                disabled={isProcessing}
                className="px-6 py-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-extrabold text-sm tracking-wide flex items-center justify-center space-x-2 shadow-lg shadow-rose-600/25 transition-all transform hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
              >
                <Square className="w-4 h-4 fill-white" />
                <span>STOP AUTOMATION</span>
              </button>
            </div>

            {/* Structured Status Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              {/* Login Status */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Login Status</span>
                <div className="flex items-center space-x-1.5 text-sm font-bold">
                  {data.login === "authenticated" ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      <span className="text-emerald-400">✓ Logged in</span>
                    </>
                  ) : data.login === "failed" ? (
                    <>
                      <AlertCircle className="w-4 h-4 text-rose-400" />
                      <span className="text-rose-400">Login Failed</span>
                    </>
                  ) : (
                    <>
                      <Clock className="w-4 h-4 text-amber-400 animate-spin" />
                      <span className="text-amber-400">Authenticating...</span>
                    </>
                  )}
                </div>
              </div>

              {/* Current Phase */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Current Phase</span>
                <span className="text-sm font-bold text-cyan-300 block">
                  {data.phase}
                </span>
              </div>

              {/* Current Assignment */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Current Assignment</span>
                <span className="text-sm font-bold text-indigo-300 block truncate" title={data.current_assignment}>
                  {data.current_assignment !== "-"
                    ? data.current_assignment
                    : data.assignments_total > 0
                    ? `${data.assignments_completed} / ${data.assignments_total}`
                    : "-"}
                </span>
              </div>

              {/* Current Practice Test */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Current Practice Test</span>
                <span className="text-sm font-bold text-purple-300 block truncate" title={data.current_test}>
                  {data.current_test !== "-"
                    ? data.current_test
                    : data.tests_total > 0
                    ? `${data.tests_completed} / ${data.tests_total}`
                    : "-"}
                </span>
              </div>

              {/* Current Question */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Current Question</span>
                <span className="text-sm font-bold text-cyan-400 block">
                  {data.current_question || "-"}
                </span>
              </div>

              {/* AI Engine */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">AI Engine</span>
                <span className="text-sm font-bold text-amber-300 block truncate">
                  Groq ({data.ai_model || "llama-3.3-70b-versatile"})
                </span>
              </div>

              {/* Execution / Browser */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Browser Target</span>
                <span className="text-sm font-bold text-emerald-400 block truncate">
                  {data.browser_visibility} ({data.execution_location})
                </span>
              </div>

              {/* Completed Count */}
              <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-1">
                <span className="text-slate-400 font-medium block">Completed Activities</span>
                <span className="text-sm font-bold text-emerald-400 block">
                  {data.assignments_completed + data.tests_completed} Completed
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Real-time Automation Console (automation.log) */}
        <div className="bg-slate-950 border border-slate-800 rounded-2xl p-5 shadow-xl flex-1 flex flex-col min-h-[300px]">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs">
            <div className="flex items-center space-x-2 font-mono text-slate-300">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span className="font-bold">LIVE AUTOMATION LOGS</span>
              <span className="text-slate-500">({data.logs.length} events)</span>
            </div>

            <button
              onClick={handleClearLogs}
              className="text-slate-400 hover:text-slate-200 transition flex items-center space-x-1"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Clear</span>
            </button>
          </div>

          <div
            ref={logsContainerRef}
            className="flex-1 overflow-y-auto mt-3 space-y-1.5 font-mono text-xs max-h-[360px] scrollbar-thin scrollbar-thumb-slate-800 pr-2"
          >
            {data.logs.map((log, index) => (
              <div key={index} className="flex items-start space-x-2 leading-relaxed">
                <span className="text-slate-600 shrink-0 select-none">[{log.time}]</span>
                <span
                  className={`${
                    log.type === "error"
                      ? "text-rose-400 font-bold"
                      : log.type === "success"
                      ? "text-emerald-400 font-semibold"
                      : log.type === "warning"
                      ? "text-amber-400"
                      : "text-slate-300"
                  }`}
                >
                  {log.message}
                </span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
export default App;
