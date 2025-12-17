export function apiBaseUrl() {
  // In Next.js, NEXT_PUBLIC_* values are inlined at build time for client code.
  // To support *runtime* configuration in prebuilt images, we also read a value
  // injected by `app/layout.js` onto `window.__API_BASE_URL__`.
  if (typeof window !== "undefined") {
    const v = window.__API_BASE_URL__;
    if (typeof v === "string" && v.trim().length > 0) return v.trim();
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

export class ApiError extends Error {
  constructor(message, { status, detail, raw } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.raw = raw;
  }
}

async function safeReadBody(res) {
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }
  try {
    return await res.text();
  } catch {
    return null;
  }
}

export async function fetchJson(path, init = {}) {
  const controller = new AbortController();
  const timeoutMs = init.timeoutMs ?? 15000;
  const t = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      signal: init.signal ?? controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(init && init.headers ? init.headers : {})
      },
      cache: "no-store"
    });

    if (!res.ok) {
      const body = await safeReadBody(res);
      const detail =
        body && typeof body === "object" && "detail" in body ? body.detail : null;
      const msg =
        typeof detail === "string"
          ? detail
          : `${res.status} ${res.statusText || "Request failed"}`;
      throw new ApiError(msg, { status: res.status, detail, raw: body });
    }

    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return await res.json();
    return await res.text();
  } catch (e) {
    if (e && e.name === "AbortError") {
      throw new ApiError("请求超时，请检查 API 服务是否正常", { status: 0 });
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}


