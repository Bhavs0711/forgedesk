import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import FeatureBoard, { groupByStatus } from "../components/FeatureBoard";
import { ProgressBar } from "../components/ui";
import type { Feature } from "../lib/types";

const feat = (id: number, status: Feature["status"], extra: Partial<Feature> = {}): Feature => ({
  id, project_id: 1, title: `Feature ${id}`, description: "", acceptance_criteria: [], priority: 100, sequence: id, status,
  attempts: 0, failure_reason: "", seconds_spent: 0, completed_at: null, depends_on: [], ...extra,
});
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("FeatureBoard", () => {
  it("groups features by status", () => {
    const g = groupByStatus([feat(1, "pending"), feat(2, "completed"), feat(3, "completed")]);
    expect(g.completed).toHaveLength(2);
    expect(g.pending).toHaveLength(1);
    expect(g.failed).toHaveLength(0);
  });
  it("shows an empty state instead of fake data", () => {
    wrap(<FeatureBoard features={[]} projectId={1} />);
    expect(screen.getByText("No features yet")).toBeInTheDocument();
  });
  it("renders columns, failure reasons and dependencies", () => {
    wrap(<FeatureBoard projectId={1} features={[feat(1, "failed", { failure_reason: "tests never passed", attempts: 3 }), feat(2, "blocked", { depends_on: [1] })]} />);
    const failed = screen.getByRole("region", { name: "failed features" });
    expect(within(failed).getByText("tests never passed")).toBeInTheDocument();
    expect(within(failed).getByText("3 attempts")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Feature 2"));
    expect(screen.getByText(/Needs: Feature 1/)).toBeInTheDocument();
  });
  it("does not offer manual control of in-progress features", () => {
    wrap(<FeatureBoard projectId={1} features={[feat(1, "in_progress")]} />);
    fireEvent.click(screen.getByText("Feature 1"));
    expect(screen.queryByLabelText(/Set status of/)).toBeNull();
  });
});

describe("ProgressBar", () => {
  it("exposes progress accessibly", () => {
    render(<ProgressBar progress={{ pending: 1, in_progress: 0, completed: 1, failed: 0, blocked: 0, total: 2, percent: 50 }} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  });
});
