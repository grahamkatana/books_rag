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

// Cross-checking never touches the document's own status (see
// client.js's crossCheckDocument) -- it's reviewing already-settled
// verdicts, not running the pipeline. Instead, this polls until every
// claim in claimIds has picked up a cross_check, which is exactly the
// set of claims the cross-check endpoint said it would touch.
export async function pollClaimsCrossChecked(documentId, claimIds, { intervalMs = 2000, timeoutMs = 10 * 60 * 1000 } = {}) {
  const remaining = new Set(claimIds);
  const deadline = Date.now() + timeoutMs;
  let doc;
  while (Date.now() < deadline) {
    doc = await fetchDocument(documentId);
    for (const claim of doc.claims) {
      if (remaining.has(claim.id) && claim.verification?.cross_check) {
        remaining.delete(claim.id);
      }
    }
    if (remaining.size === 0) return doc;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Timed out waiting for cross-check to finish");
}
