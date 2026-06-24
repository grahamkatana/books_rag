const API_BASE = "/api/v1";
const TOKEN_KEY = "book_rag_admin_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class UnauthorizedError extends Error {}
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      // FormData bodies need the browser to set their own
      // multipart/form-data Content-Type (with the correct boundary)
      // itself -- forcing application/json here would silently break
      // every file upload, since the server would try to parse a
      // multipart body as JSON.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (res.status === 401) {
    clearToken();
    throw new UnauthorizedError("Session expired, please log in again");
  }
  if (res.status === 403) {
    throw new ApiError("Admin access required", 403);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.message || `Request failed (${res.status})`, res.status);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function login(email, password) {
  const data = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setToken(data.access_token);
  return data;
}

export function logout() {
  clearToken();
}

export function fetchMe() {
  return request("/auth/me");
}

export function fetchUsers() {
  return request("/admin/users/");
}

export function createUser({ email, password, is_admin }) {
  return request("/admin/users/", {
    method: "POST",
    body: JSON.stringify({ email, password, is_admin }),
  });
}

export function updateUser(id, fields) {
  // fields is a partial object -- only include keys you actually want to change
  return request(`/admin/users/${id}`, {
    method: "PUT",
    body: JSON.stringify(fields),
  });
}

export function deleteUser(id) {
  return request(`/admin/users/${id}`, { method: "DELETE" });
}

export function fetchBooks() {
  return request("/admin/books/");
}

export function updateBook(id, fields) {
  return request(`/admin/books/${id}`, {
    method: "PUT",
    body: JSON.stringify(fields),
  });
}

export function fetchPapers() {
  return request("/admin/papers/");
}

export function updatePaper(id, fields) {
  return request(`/admin/papers/${id}`, {
    method: "PUT",
    body: JSON.stringify(fields),
  });
}

// Both deletes enqueue a background job and return immediately with a
// task_id -- they don't delete anything themselves, and the deletion
// itself (Qdrant vectors, chunk file, DB row) isn't done by the time
// this call resolves. Poll fetchJobStatus(task_id) to find out when it
// actually finishes.
export function deleteBook(id, { deletePdf = false } = {}) {
  return request(`/admin/books/${id}?delete_pdf=${deletePdf}`, { method: "DELETE" });
}

export function deletePaper(id, { deletePdf = false } = {}) {
  return request(`/admin/papers/${id}?delete_pdf=${deletePdf}`, { method: "DELETE" });
}

export function fetchJobStatus(taskId) {
  return request(`/admin/jobs/${taskId}`);
}

// Both uploads send the raw File as multipart/form-data and, like
// deleteBook/deletePaper, only enqueue a job -- they return as soon as
// the file is saved and the pipeline task is queued, not once
// ingestion actually finishes. Poll fetchJobStatus(task_id) for that.
export function uploadBook(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/admin/books/upload", { method: "POST", body: formData });
}

export function uploadPaper(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/admin/papers/upload", { method: "POST", body: formData });
}

// Enqueues both the books and papers pipelines at once -- powers the
// sidebar's Ingest button. Returns two separate task_ids (they're two
// independent jobs); poll each one separately.
export function triggerIngest({ force = false } = {}) {
  return request(`/admin/ingest/?force=${force}`, { method: "POST" });
}

export function fetchChats() {
  return request("/admin/chats/");
}

export function fetchChat(id) {
  return request(`/admin/chats/${id}`);
}

export function deleteChat(id) {
  return request(`/admin/chats/${id}`, { method: "DELETE" });
}
