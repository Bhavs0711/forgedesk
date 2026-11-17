import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import NewProjectModal from "../components/NewProjectModal";
import { api, ApiError } from "../lib/api";

// Mock the API module
vi.mock("../lib/api", () => ({
  api: {
    createProject: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

const wrap = (ui: React.ReactNode) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
};

describe("NewProjectModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("submits the form and calls the API with the right fields", async () => {
    vi.mocked(api.createProject).mockResolvedValueOnce({
      id: 5, name: "demo", path: "/tmp/demo", description: "", specification: "spec",
      test_command: "pytest", initialized: false, created_at: "2026-01-01T00:00:00",
    });

    wrap(<NewProjectModal onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Directory"), { target: { value: "/tmp/demo" } });
    fireEvent.change(screen.getByLabelText("Specification"), { target: { value: "spec" } });
    fireEvent.change(screen.getByLabelText("Test command"), { target: { value: "pytest" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(api.createProject).toHaveBeenCalledWith({
        name: "demo", path: "/tmp/demo", description: "", specification: "spec",
        test_command: "pytest", import_existing: false,
      });
    });
  });

  it("shows the create button in a pending state while submitting", async () => {
    let resolveCreate: (v: unknown) => void = () => {};
    vi.mocked(api.createProject).mockReturnValueOnce(
      new Promise((res) => { resolveCreate = res as (v: unknown) => void; }),
    );

    wrap(<NewProjectModal onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Directory"), { target: { value: "/tmp/demo" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => expect(screen.getByText("Creating…")).toBeInTheDocument());
    resolveCreate({ id: 1, name: "demo", path: "/tmp/demo", description: "", specification: "", test_command: "", initialized: false, created_at: "" });
  });

  it("displays an error message when the API rejects", async () => {
    vi.mocked(api.createProject).mockRejectedValueOnce(new ApiError(400, "directory already exists"));

    wrap(<NewProjectModal onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Directory"), { target: { value: "/tmp/demo" } });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("directory already exists");
    });
  });

  it("cancels without creating when the cancel button is clicked", () => {
    let closed = false;
    wrap(<NewProjectModal onClose={() => { closed = true; }} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(closed).toBe(true);
    expect(api.createProject).not.toHaveBeenCalled();
  });
});
