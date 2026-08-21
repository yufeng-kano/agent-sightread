/**
 * The single typed client for the backend (docs/project-structure.md § Boundaries).
 *
 * Every URL is relative: production routes `/api/*` and `/v1/*` to FastAPI through Caddy,
 * development through the nitro dev proxy, so the session cookie is always same-origin.
 * Mutations carry `X-Requested-With` — the CSRF pairing the control plane enforces
 * (docs/api.md).
 */

// --- error envelope --------------------------------------------------------

export type ApiErrorType =
  | 'invalid_request'
  | 'auth'
  | 'rate_limit'
  | 'payment'
  | 'upstream'
  | 'internal'

/** `status` is 0 when the request never reached the server (offline, DNS, aborted). */
export class ApiRequestError extends Error {
  readonly status: number
  readonly type: ApiErrorType

  constructor(status: number, type: ApiErrorType, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
    this.type = type
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }

  get isOffline(): boolean {
    return this.status === 0
  }
}

// --- response shapes (mirror apps/api/src/sightread/routes) -----------------

export interface User {
  id: number
  email: string
  name: string | null
  created_at: string
}

export interface UserSettings {
  default_model: string | null
  default_profile: string | null
  /** Custom transcription prompt; null means the shipped default. */
  system_prompt: string | null
}

export interface OpenRouterKeyState {
  present: boolean
  masked: string | null
  updated_at: string | null
}

export interface MeResponse {
  user: User
  settings: UserSettings
  /** What "default" means right now — the shipped prompt the backend runs without a custom one. */
  defaults: { system_prompt: string }
  openrouter_key: OpenRouterKeyState
}

export interface ApiKeySummary {
  id: number
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
}

/** `key` is the plaintext, returned exactly once by `POST /api/keys` (docs/auth.md). */
export interface CreatedApiKey {
  id: number
  name: string
  prefix: string
  created_at: string
  key: string
}

export interface UsageTotals {
  prompt_tokens: number
  completion_tokens: number
  cost: number
}

export interface UsageDay extends UsageTotals {
  date: string
}

export interface UsageModel extends UsageTotals {
  model: string
}

export interface UsageResponse {
  days: number
  per_day: UsageDay[]
  per_model: UsageModel[]
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface JobSummary {
  job_id: string
  status: JobStatus
  filename: string
  kind: string
  model: string
  profile: string | null
  page_count: number | null
  pages_done: number
  error: string | null
  created_at: string
  finished_at: string | null
}

export interface ResultPage {
  page: number
  width_pt: number
  height_pt: number
  method: 'vision'
  error: string | null
}

export interface ResultFigure {
  id: string
  page: number
  bbox: [number, number, number, number]
  caption: string | null
}

export interface ResultPageError {
  page: number
  reason: string
}

export interface ResultMeta {
  /** Absent on results stored before the pipeline started writing it. */
  job_id?: string
  model: string
  profile: string | null
  bbox_format: string
  pipeline_version: number
  sha256: string
  cached: boolean
}

export interface JobResult {
  markdown: string
  pages: ResultPage[]
  figures: ResultFigure[]
  errors: ResultPageError[]
  meta: ResultMeta
}

export interface ModelEntry {
  id: string
  name: string | null
  context_length: number | null
  pricing: Record<string, string> | null
  /** True when a preset profile currently resolves to this model. */
  recommended: boolean
}

export interface ProfileEntry {
  id: string
  name: string
  description: string
  model: string | null
  bbox_format: string
  profile_version: number
  available: boolean
}

// --- transport -------------------------------------------------------------

const CSRF_HEADER = 'X-Requested-With'

function toApiError(status: number, statusText: string, payload: unknown): ApiRequestError {
  const envelope =
    payload && typeof payload === 'object' && 'error' in payload
      ? (payload as { error?: { type?: ApiErrorType; message?: string } }).error
      : undefined
  return new ApiRequestError(
    status,
    envelope?.type ?? 'internal',
    envelope?.message ?? statusText ?? 'Request failed',
  )
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (method !== 'GET') {
    headers[CSRF_HEADER] = 'fetch'
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    throw new ApiRequestError(0, 'internal', cause instanceof Error ? cause.message : 'Network error')
  }

  const text = response.status === 204 ? '' : await response.text()
  let payload: unknown = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      // A non-JSON body means something in front of the API answered (proxy, error page).
      throw new ApiRequestError(response.status, 'internal', response.statusText || 'Invalid response')
    }
  }

  if (!response.ok) {
    throw toApiError(response.status, response.statusText, payload)
  }
  // 204 answers (logout, revoke, delete) carry nothing to hand back.
  return (text ? payload : undefined) as T
}

// --- control plane ---------------------------------------------------------

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>('GET', '/api/me')
}

export function logout(): Promise<void> {
  return request<undefined>('POST', '/api/auth/logout')
}

export function devLogin(): Promise<{ user: { id: number; email: string } }> {
  return request('POST', '/api/auth/dev-login')
}

/**
 * Whether `POST /api/auth/dev-login` exists on this backend (local + AUTH_DEV_MODE only).
 *
 * The probe deliberately omits the `X-Requested-With` header: the route's CSRF guard then
 * rejects it with 403 before any session is created, so probing cannot sign anyone in.
 * Only a 404 — the route was never registered — hides the button.
 */
export async function isDevLoginAvailable(): Promise<boolean> {
  try {
    const response = await fetch('/api/auth/dev-login', { method: 'POST', credentials: 'include' })
    return response.status !== 404
  } catch {
    return false
  }
}

export function listKeys(): Promise<{ keys: ApiKeySummary[] }> {
  return request('GET', '/api/keys')
}

export function createKey(name: string): Promise<CreatedApiKey> {
  return request('POST', '/api/keys', { name })
}

export function revokeKey(id: number): Promise<void> {
  return request<undefined>('DELETE', `/api/keys/${id}`)
}

export function getOpenRouterKey(): Promise<OpenRouterKeyState> {
  return request('GET', '/api/openrouter-key')
}

export function putOpenRouterKey(key: string): Promise<OpenRouterKeyState> {
  return request('PUT', '/api/openrouter-key', { key })
}

export function deleteOpenRouterKey(): Promise<void> {
  return request<undefined>('DELETE', '/api/openrouter-key')
}

/** Partial update: only the fields present in the body change (docs/api.md). */
export function putSettings(settings: Partial<UserSettings>): Promise<UserSettings> {
  return request('PUT', '/api/settings', settings)
}

export function getUsage(days: number): Promise<UsageResponse> {
  return request('GET', `/api/usage?days=${days}`)
}

export function listJobs(limit: number): Promise<{ jobs: JobSummary[] }> {
  return request('GET', `/api/jobs?limit=${limit}`)
}

export function getJobResult(jobId: string): Promise<JobResult> {
  return request('GET', `/api/jobs/${jobId}/result`)
}

// --- data plane reads the web app is allowed to make (docs/web.md) ---------

export function listModels(): Promise<{ data: ModelEntry[] }> {
  return request('GET', '/v1/models')
}

export function listProfiles(): Promise<{ data: ProfileEntry[] }> {
  return request('GET', '/v1/profiles')
}
