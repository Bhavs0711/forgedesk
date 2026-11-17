import { expect, test } from "@playwright/test";

test("create a project, manage features, and see honest agent errors", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("No projects yet")).toBeVisible();

  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill("e2e-demo");
  await page.getByLabel("Directory").fill("/tmp/forgedesk-e2e/ws/e2e-demo");
  await page.getByLabel("Specification").fill("A tiny CLI that prints hello.");
  await page.getByLabel("Test command").fill("echo ok");
  await page.getByRole("button", { name: "Create" }).click();

  await expect(page.getByRole("heading", { name: "e2e-demo" })).toBeVisible();
  await expect(page.getByText("No features yet")).toBeVisible();

  await page.getByLabel("New feature title").fill("Print greeting");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  const pending = page.getByRole("region", { name: "pending features" });
  await expect(pending.getByText("Print greeting")).toBeVisible();

  await pending.getByText("Print greeting").click();
  await page.getByLabel("Set status of Print greeting").selectOption("completed");
  await expect(page.getByRole("region", { name: "completed features" }).getByText("Print greeting")).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");

  await page.getByRole("tab", { name: "Test results" }).click();
  await page.getByRole("button", { name: "Run regression suite" }).click();
  await expect(page.getByRole("button", { name: /^PASS/ })).toBeVisible();

  await page.getByRole("link", { name: "Agent monitor" }).click();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("alert")).toContainText("ANTHROPIC_API_KEY");
});

test("settings never display the API key", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByText("not configured")).toBeVisible();
  await expect(page.locator("body")).not.toContainText("sk-ant");
});
