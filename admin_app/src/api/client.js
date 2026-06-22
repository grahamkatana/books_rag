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
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
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
// No deleteBook on purpose -- the API doesn't offer it either. A Book
// row has real Qdrant vectors and a chunk file nothing currently cleans
// up; deleting just the row would leave those orphaned and still
// searchable with no Book left to resolve their citation against.

export function fetchPapers() {
  return request("/admin/papers/");
}

export function updatePaper(id, fields) {
  return request(`/admin/papers/${id}`, {
    method: "PUT",
    body: JSON.stringify(fields),
  });
}
// No deletePaper either, for the exact same reason as books: a Paper
// row has real Qdrant vectors and a chunk file nothing currently cleans
// up.

export function fetchChats() {
  return request("/admin/chats/");
}

export function fetchChat(id) {
  return request(`/admin/chats/${id}`);
}

export function deleteChat(id) {
  return request(`/admin/chats/${id}`, { method: "DELETE" });
}
