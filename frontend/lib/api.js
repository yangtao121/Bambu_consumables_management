export function apiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

export async function fetchJson(path, init) {
  // #region agent log
  fetch('http://127.0.0.1:7242/ingest/4ce5cedd-1b32-4497-a199-8b8693bfebf9',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/lib/api.js:fetchJson:pre',message:'fetchJson request',data:{baseUrl:apiBaseUrl(),path,method:(init&&init.method)||'GET'},timestamp:Date.now(),sessionId:'debug-session',runId:(process.env.NEXT_PUBLIC_DEBUG_RUN_ID||'run1'),hypothesisId:'E'})}).catch(()=>{});
  // #endregion
  const res = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init && init.headers ? init.headers : {})
    },
    cache: "no-store"
  });
  // #region agent log
  fetch('http://127.0.0.1:7242/ingest/4ce5cedd-1b32-4497-a199-8b8693bfebf9',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'frontend/lib/api.js:fetchJson:post',message:'fetchJson response',data:{path,status:res.status,ok:res.ok},timestamp:Date.now(),sessionId:'debug-session',runId:(process.env.NEXT_PUBLIC_DEBUG_RUN_ID||'run1'),hypothesisId:'E'})}).catch(()=>{});
  // #endregion
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  return await res.text();
}


