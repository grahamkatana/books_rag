import { fetchJobStatus } from "../api/client";

// Plain polling, not a socket -- a delete job finishes in well under a
// second (one Qdrant filter-delete, two file removals, one DB row), so
// there's no real progress to stream, just a pending-or-done
// transition. See the backend's own admin_jobs.py for the full
// reasoning; this just consumes that same endpoint.
export async function pollJobUntilDone(taskId, { intervalMs = 600, timeoutMs = 30000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await fetchJobStatus(taskId);
    if (status.state === "SUCCESS") return status;
    if (status.state === "FAILURE") throw new Error(status.error || "The job failed");
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Timed out waiting for the job to finish");
}
