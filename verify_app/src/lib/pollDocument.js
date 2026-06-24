import { fetchDocument } from "../api/client";

// Polls the document's OWN status field, not a generic job -- the
// pipeline already writes "done" or "failed" directly onto
// VerificationDocument as it progresses, so there's no separate task
// state to reconcile against; this just reads the same row the rest
// of the UI already renders from.
export async function pollDocumentUntilDone(documentId, { intervalMs = 2000, timeoutMs = 15 * 60 * 1000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const doc = await fetchDocument(documentId);
    if (doc.status === "done" || doc.status === "failed") return doc;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Timed out waiting for verification to finish");
}
