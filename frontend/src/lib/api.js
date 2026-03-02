const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || window.location.origin;

export const API_BASE = `${BACKEND_URL}/api`;

const wait = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

export async function apiRequest(path, options = {}, retryCount = 1) {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;

  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      const response = await fetch(url, { credentials: "include", ...options });
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

export async function checkApiHealth() {
  const response = await apiRequest("/health", { method: "GET" }, 0);
  if (!response.ok) {
    throw new Error("Serviço indisponível");
  }
  return response.json();
}
