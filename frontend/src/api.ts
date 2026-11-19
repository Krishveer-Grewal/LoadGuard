async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => req<T>(path),
  post: <T>(path: string, body?: unknown) =>
    req<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body: unknown) =>
    req<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  del: (path: string) => req<void>(path, { method: "DELETE" }),
  form: <T>(path: string, form: FormData) => req<T>(path, { method: "POST", body: form }),
};

export const frameUrl = (tid: string, opts: { annotated?: boolean; layers?: string; t?: number } = {}) => {
  const p = new URLSearchParams();
  if (opts.layers !== undefined) p.set("layers", opts.layers);
  else p.set("annotated", opts.annotated === false ? "0" : "1");
  p.set("t", String(opts.t ?? Date.now()));
  return `/api/trailers/${tid}/frame.jpg?${p}`;
};

export const streamUrl = (tid: string, annotated: boolean) =>
  `/api/trailers/${tid}/stream.mjpg?annotated=${annotated ? 1 : 0}&fps=6`;
