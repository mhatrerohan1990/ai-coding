import type { Decision, Label } from "./types";

// Evidence ids whose label opposes the final status. Computed from labels only.
export function computeConflicts(
  status: Decision["status"],
  labels: Record<string, Label>,
): string[] {
  const ids = Object.keys(labels);
  const pass = ids.filter((id) => labels[id] === "indicates_pass");
  const fail = ids.filter((id) => labels[id] === "indicates_fail");

  if (status === "pass") return fail;
  if (status === "fail") return pass;
  return pass.length > 0 && fail.length > 0 ? [...pass, ...fail] : [];
}
