export interface AutomationStatusResponse {
  status: "idle" | "running" | "completed" | "error" | "stopped";
  phase: "Idle" | "Login" | "Library" | "Assignments" | "Practice Tests" | "Completed" | "Error" | "Stopped";
  chrome: "closed" | "initializing" | "connected";
  login: "pending" | "authenticated" | "failed";
  execution_mode?: "local_visual" | "render_cloud";
  execution_location?: "LOCAL WINDOWS" | "RENDER CLOUD";
  browser_visibility?: "VISIBLE CHROME" | "HEADLESS CHROMIUM" | "WAITING FOR LOCAL AGENT" | "READY";
  local_agent_connected?: boolean;
  registered_agent_id?: string | null;
  current_subject?: string;
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
  sessionConfigured?: boolean;
  targetUrl: string;
}
