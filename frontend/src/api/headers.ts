// Headers sent on every API request.
//
// `ngrok-skip-browser-warning` bypasses ngrok's free-tier interstitial warning
// page, which ngrok otherwise injects for browser User-Agent requests (including
// fetch/XHR) and which would replace our JSON/SSE responses with HTML. Harmless
// locally and same-origin (via the Vite `/api` proxy), so it never triggers CORS.
export const API_HEADERS: Record<string, string> = {
  "ngrok-skip-browser-warning": "true",
};
