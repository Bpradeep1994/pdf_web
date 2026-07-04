import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import Cookies from "js-cookie";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const api: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = Cookies.get("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshToken = Cookies.get("refresh_token");
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_URL}/api/v1/auth/refresh`, {
            refresh_token: refreshToken,
          });
          Cookies.set("access_token",  data.access_token,  { expires: 1 / 48, secure: true, sameSite: "lax" });
          Cookies.set("refresh_token", data.refresh_token, { expires: 7,       secure: true, sameSite: "lax" });
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          Cookies.remove("access_token");
          Cookies.remove("refresh_token");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register:  (body: { email: string; password: string; full_name: string }) =>
    api.post("/auth/register", body),
  login:     (body: { email: string; password: string }) =>
    api.post("/auth/login", body),
  logout:    (refresh_token: string) =>
    api.post("/auth/logout", { refresh_token }),
  me:        () => api.get("/auth/me"),
  refresh:   (refresh_token: string) =>
    api.post("/auth/refresh", { refresh_token }),
  resetPasswordRequest: (email: string) =>
    api.post("/auth/password-reset", { email }),
  resetPasswordConfirm: (token: string, password: string) =>
    api.post("/auth/password-reset/confirm", { token, password }),
  verifyEmail: (token: string) => api.post("/auth/verify-email", { token }),
  resendVerification: () => api.post("/auth/resend-verification"),
  setupMfa:  () => api.post("/auth/mfa/setup"),
  verifyMfa: (code: string) => api.post("/auth/mfa/verify", { code }),
};

// ── Documents ─────────────────────────────────────────────────────────────────
export const documentsApi = {
  list:     (page = 1, pageSize = 20) =>
    api.get("/documents", { params: { page, page_size: pageSize } }),
  usage:    () => api.get("/documents/usage"),
  get:      (id: string) => api.get(`/documents/${id}`),
  upload:   (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/documents", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e) => onProgress?.(Math.round((e.loaded * 100) / (e.total ?? 1))),
    });
  },
  delete:   (id: string) => api.delete(`/documents/${id}`),
  download: (id: string) => api.get(`/documents/${id}/download`),
  renderPage: (id: string, page: number, zoom = 1.5) =>
    `${API_URL}/api/v1/documents/${id}/pages/${page}?zoom=${zoom}`,
  extractText: (id: string, page?: number) =>
    api.get(`/documents/${id}/text`, { params: { page } }),
  tables: (id: string, page = 1) => api.get(`/documents/${id}/tables`, { params: { page } }),
  textSpans: (id: string, page = 1) => api.get(`/documents/${id}/text-spans`, { params: { page } }),
  editText:    (id: string, body: object) => api.post(`/documents/${id}/edit/text`, body),
  replaceText: (id: string, body: object) => api.post(`/documents/${id}/edit/replace`, body),
  highlight:   (id: string, body: object) => api.post(`/documents/${id}/edit/highlight`, body),
  redact:      (id: string, body: object) => api.post(`/documents/${id}/edit/redact`, body),
  merge:       (ids: string[]) => api.post("/documents/merge", { document_ids: ids }),
  split:       (id: string, ranges?: number[][]) => api.post(`/documents/${id}/split`, { ranges }),
  compress:    (id: string, quality: "low" | "medium" | "high" = "medium") =>
    api.post(`/documents/${id}/compress`, { quality }),
  addShape:    (id: string, body: object) => api.post(`/documents/${id}/edit/shape`, body),
  addImage:    (id: string, body: object) => api.post(`/documents/${id}/edit/image`, body),
  watermark:   (id: string, body: { text: string; opacity?: number; size?: number; rotate?: number }) =>
    api.post(`/documents/${id}/edit/watermark`, body),
  update:      (id: string, body: { original_name?: string; folder_id?: string | null }) => api.patch(`/documents/${id}`, body),
  // page tools
  addPage:        (id: string, after?: number) => api.post(`/documents/${id}/pages/add`, { after }),
  rotatePages:    (id: string, pages: number[], degrees = 90) => api.post(`/documents/${id}/pages/rotate`, { pages, degrees }),
  deletePages:    (id: string, pages: number[]) => api.post(`/documents/${id}/pages/delete`, { pages }),
  reorderPages:   (id: string, order: number[]) => api.post(`/documents/${id}/pages/reorder`, { order }),
  duplicatePages: (id: string, pages: number[]) => api.post(`/documents/${id}/pages/duplicate`, { pages }),
  extractPages:   (id: string, pages: number[]) => api.post(`/documents/${id}/pages/extract`, { pages }),
  // comments
  comments:       (id: string) => api.get(`/documents/${id}/comments`),
  addComment:     (id: string, body: object) => api.post(`/documents/${id}/comments`, body),
  updateComment:  (id: string, cid: string, body: object) => api.patch(`/documents/${id}/comments/${cid}`, body),
  deleteComment:  (id: string, cid: string) => api.delete(`/documents/${id}/comments/${cid}`),
  share:       (id: string, body: object) => api.post(`/documents/${id}/share`, body),
  versions:    (id: string) => api.get(`/documents/${id}/versions`),
  restoreVersion: (id: string, version: number) =>
    api.post(`/documents/${id}/versions/${version}/restore`),
  undo:        (id: string) => api.post(`/documents/${id}/undo`),
  redo:        (id: string) => api.post(`/documents/${id}/redo`),
};

// ── Projects / Team Workspaces ────────────────────────────────────────────────────
export const projectsApi = {
  list:    () => api.get("/projects"),
  create:  (body: { name: string; description?: string }) => api.post("/projects", body),
  get:     (id: string) => api.get(`/projects/${id}`),
  remove:  (id: string) => api.delete(`/projects/${id}`),
  addMember:    (id: string, body: { user_id: string; role?: string }) => api.post(`/projects/${id}/members`, body),
  removeMember: (id: string, userId: string) => api.delete(`/projects/${id}/members/${userId}`),
  addDocument:    (id: string, document_id: string) => api.post(`/projects/${id}/documents`, { document_id }),
  removeDocument: (id: string, documentId: string) => api.delete(`/projects/${id}/documents/${documentId}`),
};

// ── Notifications ─────────────────────────────────────────────────────────────────
export const notificationsApi = {
  list:        (unreadOnly = false) => api.get("/notifications", { params: { unread_only: unreadOnly } }),
  unreadCount: () => api.get("/notifications/unread-count"),
  markRead:    (id: string) => api.post(`/notifications/${id}/read`),
  markAllRead: () => api.post("/notifications/read-all"),
};

// ── Folders ─────────────────────────────────────────────────────────────────────
export const foldersApi = {
  list:      (parentId?: string) => api.get("/folders", { params: { parent_id: parentId } }),
  create:    (name: string, parentId?: string) => api.post("/folders", { name, parent_id: parentId }),
  rename:    (id: string, name: string) => api.patch(`/folders/${id}`, { name }),
  remove:    (id: string) => api.delete(`/folders/${id}`),
  documents: (id: string) => api.get(`/folders/${id}/documents`),
};

// ── Enterprise API keys ───────────────────────────────────────────────────────────
export const keysApi = {
  list:   () => api.get("/keys"),
  create: (name: string) => api.post("/keys", { name }),
  revoke: (id: string) => api.delete(`/keys/${id}`),
};

// ── Billing ─────────────────────────────────────────────────────────────────────
export const billingApi = {
  plans:        () => api.get("/billing/plans"),
  subscription: () => api.get("/billing/subscription"),
  invoices:     () => api.get("/billing/invoices"),
  checkout:     (plan: string, interval = "monthly") => api.post("/billing/checkout", { plan, interval }),
  devActivate:  (body: { plan: string; interval?: string; provider?: string; method?: string; card_brand?: string }) =>
    api.post("/billing/dev-activate", body),
  sendOtp:      (phone?: string) => api.post("/billing/send-otp", { phone }),
  verifyOtp:    (body: { otp: string; plan: string; interval?: string; provider?: string; method?: string; card_brand?: string }) =>
    api.post("/billing/verify-otp", body),
  changePlan:   (plan: string) => api.post("/billing/change-plan", { plan }),
  cancel:       () => api.post("/billing/cancel"),
  resume:       () => api.post("/billing/resume"),
  refund:       (payment_id: string, reason?: string) => api.post("/billing/refund", { payment_id, reason }),
  providers:    () => api.get("/billing/providers"),
  paymentMethods: () => api.get("/billing/payment-methods"),
  payments:     () => api.get("/billing/payments"),
  portal:       () => api.post("/billing/portal"),
};

// ── Admin (Super Admin panel) ─────────────────────────────────────────────────────
export const adminApi = {
  stats:     () => api.get("/admin/stats"),
  kpis:      () => api.get("/admin/kpis"),
  users:     (page = 1, pageSize = 20, search?: string) =>
    api.get("/admin/users", { params: { page, page_size: pageSize, search } }),
  updateUser: (id: string, body: { role?: string; is_active?: boolean; admin_level?: string; status?: string; full_name?: string }) =>
    api.patch(`/admin/users/${id}`, body),
  deleteUser: (id: string) => api.delete(`/admin/users/${id}`),
  resetUserPassword: (id: string) => api.post(`/admin/users/${id}/reset-password`),
  auditLogs: (page = 1, pageSize = 50, action?: string) =>
    api.get("/admin/audit-logs", { params: { page, page_size: pageSize, action } }),
  documents: (page = 1, search?: string) =>
    api.get("/admin/documents", { params: { page, search } }),
  revenue:       () => api.get("/admin/revenue"),
  subscriptions: (page = 1) => api.get("/admin/subscriptions", { params: { page } }),
  invoices:      (page = 1) => api.get("/admin/invoices", { params: { page } }),
  analytics:     () => api.get("/admin/analytics"),
  tickets:       (status?: string, page = 1) =>
    api.get("/admin/support-tickets", { params: { status, page } }),
  updateTicket:  (id: string, body: { status?: string; priority?: string; response?: string }) =>
    api.patch(`/admin/support-tickets/${id}`, body),
  settings:      () => api.get("/admin/settings"),
  putSetting:    (key: string, value: object) => api.put("/admin/settings", { key, value }),
};

// ── Analytics (pageview tracking → admin KPIs) ────────────────────────────────────
export const analyticsApi = {
  track: (body: { event_type?: string; source?: string; country?: string; path?: string }) =>
    api.post("/analytics/track", body),
};

// ── Support tickets (user-facing) ───────────────────────────────────────────────
export const supportApi = {
  create: (body: { subject: string; message: string; priority?: string }) => api.post("/support/tickets", body),
  list:   () => api.get("/support/tickets"),
};

// ── E-Signature ─────────────────────────────────────────────────────────────────
export const signatureApi = {
  // self-sign: stamp a signature image onto your own document
  apply: (body: { document_id: string; signature_base64: string; page?: number; x: number; y: number; width?: number; height?: number }) =>
    api.post("/signatures/apply", body),
  createRequest: (body: { document_id: string; title?: string; message?: string; fields: object[] }) =>
    api.post("/signatures/requests", body),
  listRequests:  () => api.get("/signatures/requests"),
  getRequest:    (id: string) => api.get(`/signatures/requests/${id}`),
  signField:     (reqId: string, body: { field_id: string; signature_base64: string }) =>
    api.post(`/signatures/requests/${reqId}/sign`, body),
};

// ── OCR ───────────────────────────────────────────────────────────────────────
export const ocrApi = {
  process: (document_id: string, s3_key: string, language = "en") =>
    api.post("/ocr/process", { document_id, s3_key, language }),
  status:  (document_id: string) => api.get(`/ocr/status/${document_id}`),
};

// ── Conversion ────────────────────────────────────────────────────────────────
export const conversionApi = {
  convert: (body: { s3_key: string; source_format: string; target_format: string; document_id: string }) =>
    api.post("/convert/convert", body),
  // Direct file conversion (Office/Image → PDF) — no document store involved.
  convertFile: (file: File, target_format = "pdf") => {
    const form = new FormData();
    form.append("file", file);
    form.append("target_format", target_format);
    return api.post("/convert/file", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  protect: (file: File, password: string) => {
    const form = new FormData(); form.append("file", file); form.append("password", password);
    return api.post("/convert/protect", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  unlock: (file: File, password: string) => {
    const form = new FormData(); form.append("file", file); form.append("password", password);
    return api.post("/convert/unlock", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  scan: (filesList: File[]) => {
    const form = new FormData(); filesList.forEach((f) => form.append("files", f));
    return api.post("/convert/scan", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  translateFile: (file: File, target: string, source = "auto") => {
    const form = new FormData();
    form.append("file", file); form.append("target_lang", target); form.append("source_lang", source);
    return api.post("/convert/translate-file", form, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 });
  },
  translateLanguages: () => api.get("/convert/translate-languages"),
  formats: () => api.get("/convert/formats"),
};

export default api;
