const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || window.location.origin;

export const API_BASE = `${BACKEND_URL}/api`;
const AUTH_TOKEN_KEY = "kp_session_token";

const wait = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

export function getAuthToken() {
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token) {
  if (!token) {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

function withAuthHeader(headers = {}) {
  const token = getAuthToken();
  if (!token) {
    return headers;
  }

  const normalizedHeaders = new Headers(headers);
  if (!normalizedHeaders.has("Authorization")) {
    normalizedHeaders.set("Authorization", `Bearer ${token}`);
  }

  return normalizedHeaders;
}

export async function authFetch(url, options = {}, retryCount = 1) {
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      const response = await fetch(url, {
        credentials: "include",
        ...options,
        headers: withAuthHeader(options.headers),
      });
      return response;
    } catch (error) {
      if (attempt === retryCount) {
        throw error;
      }
      await wait(250 * (attempt + 1));
    }
  }

  throw new Error("Network request failed");
}

export async function apiRequest(path, options = {}, retryCount = 1) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  return authFetch(url, options, retryCount);
}

export async function checkApiHealth() {
  const response = await apiRequest("/health", { method: "GET" }, 0);
  if (!response.ok) {
    throw new Error("Serviço indisponível");
  }
  return response.json();
}
