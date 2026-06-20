const API_BASE = "/api/v1";
const TOKEN_KEY = "book_rag_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Thrown when a request comes back 401 -- callers (App.jsx) catch this
 * specifically to clear the stored token and drop back to the login
 * screen, rather than just showing a generic error. */
export class UnauthorizedError extends Error {}

async function authedFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (res.status === 401) {
    clearToken();
    throw new UnauthorizedError("Session expired, please log in again");
  }
  return res;
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message || "Login failed");
  }
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export function logout() {
  clearToken();
}

export async function fetchMe() {
  const res = await authedFetch(`${API_BASE}/auth/me`);
  if (!res.ok) throw new Error("Failed to load current user");
  return res.json();
}

export async function fetchChats() {
  const res = await authedFetch(`${API_BASE}/chats/`);
  if (!res.ok) throw new Error("Failed to load chats");
  return res.json();
}

export async function fetchChat(chatId) {
  const res = await authedFetch(`${API_BASE}/chats/${chatId}`);
  if (!res.ok) throw new Error("Failed to load chat");
  return res.json();
}

export async function deleteChat(chatId) {
  const res = await authedFetch(`${API_BASE}/chats/${chatId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete chat");
}

export async function fetchBooks() {
  const res = await authedFetch(`${API_BASE}/books/`);
  if (!res.ok) throw new Error("Failed to load books");
  return res.json();
}

export async function fetchBook(bookId) {
  const res = await authedFetch(`${API_BASE}/books/${bookId}`);
  if (!res.ok) throw new Error("Failed to load book");
  return res.json();
}

/**
 * Streams an answer via Server-Sent Events. Can't use the browser's
 * built-in EventSource here since it only supports GET requests, and
 * this endpoint is a POST (it needs a JSON body and an auth header).
 * Reading the raw fetch() response stream by hand instead.
 */
export async function streamAsk(payload, { onChatId, onDelta, onDone, onError }) {
  try {
    const res = await fetch(`${API_BASE}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      clearToken();
      throw new UnauthorizedError("Session expired, please log in again");
    }
    if (!res.ok || !res.body) {
      throw new Error(`Request failed: ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line.
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        const eventMatch = rawEvent.match(/^event: (.+)$/m);
        const dataMatch = rawEvent.match(/^data: (.+)$/m);
        if (!eventMatch || !dataMatch) continue;

        const eventType = eventMatch[1].trim();
        const data = JSON.parse(dataMatch[1]);

        if (eventType === "chat_id") onChatId?.(data.chat_id);
        else if (eventType === "delta") onDelta?.(data.text);
        else if (eventType === "done") onDone?.(data);
        else if (eventType === "error") onError?.(new Error(data.message));
      }
    }
  } catch (err) {
    onError?.(err);
  }
}
