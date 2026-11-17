import { defineConfig } from "@playwright/test";

// Serves the production build through the real backend with a throwaway database and workspace.
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8123" },
  webServer: {
    command:
      "rm -rf /tmp/forgedesk-e2e && mkdir -p /tmp/forgedesk-e2e/ws && ../backend/.venv/bin/python -m uvicorn forgedesk.main:app --port 8123 --app-dir ../backend",
    url: "http://127.0.0.1:8123/api/settings",
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      FORGEDESK_DATABASE_URL: "sqlite:////tmp/forgedesk-e2e/e2e.db",
      FORGEDESK_WORKSPACE_ROOTS: '["/tmp/forgedesk-e2e/ws"]',
      ANTHROPIC_API_KEY: "",
    },
  },
});
