// Backend base URL, injected at build time by Vite.
//
// VITE_BACKEND_URL is the canonical name. REACT_APP_BACKEND_URL is still read
// as a fallback so builds that predate the Vite migration keep working.
// Falls back to an empty string, which makes API calls relative to the origin
// the app is served from.
export const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL || import.meta.env.REACT_APP_BACKEND_URL || "";
