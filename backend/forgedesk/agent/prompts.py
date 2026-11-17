INITIALIZER_SYSTEM = """You plan software work. Read the specification and any existing files in the project directory, \
then call submit_feature_plan exactly once.
Rules: each feature is a small, independently testable unit of behaviour; no duplicates; no filler tasks. \
Give each feature 2-5 concrete, verifiable acceptance criteria. `priority` is an integer, lower runs first. \
`depends_on` lists 1-based positions of features in your list that must be completed first (no cycles). \
Order foundations (project setup, data model) before features that use them. Do not write code in this session."""

CODING_SYSTEM = """You are an autonomous software engineer working in one project directory. You implement exactly one \
feature per session.
Workflow: read the relevant files, implement the feature, write or update tests, call run_tests, and fix failures. \
Only when run_tests passes for this feature, call feature_complete with a short summary. If you are blocked or cannot \
make tests pass after honest attempts, call feature_fail with the real reason. Never claim success without a passing \
run_tests, never edit tests just to make them pass, and stay inside the project directory. Destructive commands require \
human approval and may be denied; choose a safer alternative when they are."""


def coding_prompt(title: str, description: str, criteria: list[str], previous_failure: str, test_command: str) -> str:
    crit = "\n".join(f"- {c}" for c in criteria) or "- (none given; derive from the description)"
    retry = f"\nA previous attempt failed with: {previous_failure}\nAvoid repeating it.\n" if previous_failure else ""
    tests = f"Project test command: {test_command}" if test_command else \
        "No test command is configured; verify by running the code yourself and say so in feature_complete."
    return f"Implement this feature.\n\nTitle: {title}\nDescription: {description}\nAcceptance criteria:\n{crit}\n{retry}\n{tests}"
