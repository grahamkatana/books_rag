const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export class UnauthorizedError extends ApiError {
  constructor(message) {
    super(message, 401);
  }
}

function readToken() {
  return localStorage.getItem("token");
}

function writeToken(token) {
  localStorage.setItem("token", token);
}

export function getToken() {
  return readToken();
}

export function clearToken() {
  localStorage.removeItem("token");
}

function authHeaders() {
  const token = readToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      // Same reasoning as the admin app's client: a FormData body needs
      // the browser to set its own multipart boundary header, which a
      // forced application/json content-type would silently break.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (res.status === 401) {
    clearToken();
    throw new UnauthorizedError("Session expired, please log in again");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.message || `Request failed (${res.status})`, res.status);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.message || "Login failed", res.status);
  }
  const data = await res.json();
  writeToken(data.access_token);
  return data;
}

export function logout() {
  clearToken();
}

export function fetchMe() {
  return request("/auth/me");
}

export function fetchDocuments() {
  return request("/verification/");
}

export function fetchDocument(id) {
  return request(`/verification/${id}`);
}

// Enqueues the pipeline and returns immediately with a task_id -- the
// actual result (claims, verdicts, evidence) shows up on the document
// itself, fetched via fetchDocument(), not through this response or
// the generic job-status endpoint. See app/api/v1/verification.py's
// own docstring for why.
export function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/verification/", { method: "POST", body: formData });
}

export function deleteDocument(id) {
  return request(`/verification/${id}`, { method: "DELETE" });
}

// Completion for this one is detectable the exact same way the original
// upload's pipeline is -- the document's own status reaches "done" or
// "failed" again, so pollDocumentUntilDone (already used for upload)
// works here unchanged, no new polling logic needed.
export function rerunDocument(id, { fromExtraction = true } = {}) {
  return request(`/verification/${id}/rerun?from_extraction=${fromExtraction}`, { method: "POST" });
}

// Different from rerun: this never changes the document's own status
// (it's reviewing already-settled verdicts, not running the pipeline),
// so it returns the specific claim_ids it will touch instead --
// pollClaimsCrossChecked (lib/pollDocument.js) watches for those.
export function crossCheckDocument(id, { verdicts = null } = {}) {
  const params = verdicts ? verdicts.map((v) => `verdicts=${v}`).join("&") : "";
  return request(`/verification/${id}/cross-check${params ? `?${params}` : ""}`, { method: "POST" });
}
