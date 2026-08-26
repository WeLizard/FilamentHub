/** API Client для интеграции с бэкендом */

import axios from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';
import type { BrandAnalytics } from '../types/api';
import type { AdminAchievementOverview } from '../types/api';
import type { AccessibleBrand, AdminUserListResponse, AuthMethods, Brand, BrandUsage, BrandCountryCell, BrandRepresentative, BrandRepresentativeInvite, BrandRequest, BrandRequestStatus, BrandTeamInvite, BrandTeamRole, BrandTeamWorkspace, Filament, FilamentAdditive, FilamentPropertyClaim, FilamentLine, FilamentImportPreviewResult, FilamentImportResult, FilamentListResponse, FilamentPalettePayload, BrandInvitePublic, BrandInviteAdmin, BrandInviteAcceptResult, BrandInviteBatchPreview, BrandInviteBatchSendResult, FilamentAvailability, CountryAvailability, FilamentCountryCell, FilamentVisualSettings, FilamentReview, FilamentRatingStats, Notification, NotificationListResponse, Preset, RecommendedPreset, RecommendedForPrinterResponse, Printer, PrinterProfile, PrintProfile, PrinterRequest, User, Token, RefreshTokenRequest, RefreshTokenResponse, ListResponse, AccountDeletionStats, UserSavedPreset, CalculatorEstimateRequest, CalculatorEstimateResponse, CalculatorProfileResponse, CalculatorProfileUpdate, Feedback, FeedbackDetail, FeedbackListResponse, FeedbackType, PluginDownloadsResponse, WikiCategory, WikiCategoryListResponse, WikiArticle, WikiArticleListResponse, WikiArticleTranslation, WikiFeedbackStats, WikiFeedbackCreate, WikiFeedback, WikiGuideProgressResponse, WikiLanguage, WikiMediaAsset, WikiReviewVerdict, WikiRevision, WikiRevisionListResponse, WikiPublicRevisionListResponse, WikiRevisionStatus, WikiSpace, WikiSpaceKey, EmailThreadDetail, EmailThreadListResponse, EmailThreadStatus, EmailMessage, EmailSenderProfile, EmailLanguage, NotificationCampaignAudience, NotificationCampaignHistoryResponse, NotificationCampaignPreview, NotificationCampaignSendResult, LegalAcceptancePayload, LegalDocument, LegalDocumentType, LegalPack, LegalRequirements, RegistrationPayload, SpoolUsageEvent, OrcaSliceReport, OrcaPresetScope, OrcaSchemaObservation, OrcaSchemaObservationListResponse, OrcaSchemaObservationStatus, UnreadCommunicationsCount } from '../types/api';
import { getCsrfToken, getRefreshToken, getToken, isCookieAuthMode, isJwtAuthMode, isOrcaEmbedded, removeToken, setRefreshToken, setToken, shouldPersistTokensLocally } from '../utils/auth';
import { isPluginEmbed, reportPluginSessionToPlugin } from '../utils/pluginBridge';
import { downloadBlob } from '../utils/download';
import { currentRequestLanguage } from '../utils/requestLanguage';

const API_BASE_URL = '/api/v1';
const COOKIE_AUTH_MODE = isCookieAuthMode();
const JWT_AUTH_MODE = isJwtAuthMode();
const CSRF_HEADER_NAME = import.meta.env.VITE_AUTH_CSRF_HEADER_NAME || 'X-CSRF-Token';
const canUseCookieSession = (): boolean => COOKIE_AUTH_MODE && !isOrcaEmbedded();

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: canUseCookieSession(),
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Уведомить C++ (OrcaSlicer) о logout — очистить токен в AppConfig */
const notifyCppLogout = () => {
  try {
    if (typeof window !== 'undefined' && window.wx?.postMessage) {
      window.wx.postMessage(JSON.stringify({ command: 'logout' }));
    }
  } catch {
    // Не в контексте OrcaSlicer — игнорируем
  }
};

// Добавляем токен в запросы
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token && JWT_AUTH_MODE) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const method = (config.method || 'GET').toUpperCase();
  const hasBearer = Boolean(config.headers?.Authorization);
  if (canUseCookieSession() && !hasBearer && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }

  return config;
});

interface RetryableAxiosConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

// Переменная для предотвращения множественных запросов refresh
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
  config: RetryableAxiosConfig;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      if (token) {
        prom.config.headers.Authorization = `Bearer ${token}`;
      }
      prom.resolve(api(prom.config));
    }
  });
  
  failedQueue = [];
};

const AUTH_REFRESH_LOCK_NAME = 'filamenthub-auth-refresh';
let refreshRequestPromise: Promise<RefreshTokenResponse> | null = null;
let localAuthOperationTail: Promise<void> = Promise.resolve();

export class StaleRefreshResponseError extends Error {
  constructor() {
    super('Refresh response belongs to a replaced local session');
    this.name = 'StaleRefreshResponseError';
  }
}

async function withCrossTabRefreshLock<T>(operation: () => Promise<T>): Promise<T> {
  if (typeof navigator === 'undefined' || !navigator.locks?.request) {
    return operation();
  }
  return navigator.locks.request(AUTH_REFRESH_LOCK_NAME, operation);
}

function withAuthSessionLock<T>(operation: () => Promise<T>): Promise<T> {
  const result = localAuthOperationTail.then(
    () => withCrossTabRefreshLock(operation),
    () => withCrossTabRefreshLock(operation),
  );
  localAuthOperationTail = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

async function performSessionRefresh(
  requestedRefreshToken?: string | null,
): Promise<RefreshTokenResponse> {
  const cookieSessionAvailable = canUseCookieSession();
  const persistedRefreshToken = getRefreshToken();
  // Re-read storage only after acquiring the cross-tab lock.  Another tab may
  // have rotated the family while this caller was waiting.
  const refreshToken = persistedRefreshToken || requestedRefreshToken || null;
  if (!refreshToken && !cookieSessionAvailable) {
    throw new Error('No refresh token available');
  }

  const refreshPayload = refreshToken
    ? ({ refresh_token: refreshToken } as RefreshTokenRequest)
    : undefined;
  const response = await axios.post<RefreshTokenResponse>(
    `${API_BASE_URL}/auth/refresh`,
    refreshPayload,
    {
      baseURL: '',
      withCredentials: cookieSessionAvailable,
      headers: cookieSessionAvailable
        ? (() => {
            const csrfToken = getCsrfToken();
            return csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : {};
          })()
        : undefined,
    },
  );

  const { access_token, refresh_token: rotatedRefreshToken } = response.data;
  if (!access_token) {
    throw new Error('No access token received from refresh endpoint');
  }

  if (JWT_AUTH_MODE && shouldPersistTokensLocally()) {
    const currentRefreshToken = getRefreshToken();
    const responseStillCurrent =
      currentRefreshToken === refreshToken ||
      (Boolean(rotatedRefreshToken) && currentRefreshToken === rotatedRefreshToken);

    // Compare-and-swap prevents a delayed response from overwriting a newer
    // generation written by another tab.  It also avoids restoring tokens
    // after logout removed the local session while this request was in flight.
    if (!responseStillCurrent) {
      throw new StaleRefreshResponseError();
    }
    if (rotatedRefreshToken && currentRefreshToken !== rotatedRefreshToken) {
      setRefreshToken(rotatedRefreshToken);
    }
    setToken(access_token);
  }

  return response.data;
}

/** One refresh request per page and, where supported, one at a time per browser profile. */
export async function refreshAuthSession(
  requestedRefreshToken?: string | null,
): Promise<RefreshTokenResponse> {
  if (refreshRequestPromise) {
    return refreshRequestPromise;
  }

  refreshRequestPromise = withAuthSessionLock(() =>
    performSessionRefresh(requestedRefreshToken),
  );
  try {
    return await refreshRequestPromise;
  } finally {
    refreshRequestPromise = null;
  }
}

// Обработка ошибок ответа
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Network error — no response received (internet down, server unreachable, DNS failure)
    if (!error.response) {
      const isTimeout = error.code === 'ECONNABORTED' || error.code === 'ERR_CANCELED';
      const code = isTimeout ? 'ERR_REQUEST_TIMEOUT' : 'ERR_NETWORK';
      // Inject structured error so translateApiError can handle it uniformly
      error.response = {
        status: 0,
        statusText: 'Network Error',
        headers: {},
        config: error.config,
        data: { detail: { code } },
      };
      return Promise.reject(error);
    }

    // Проверяем на maintenance mode (503)
    if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
      // Dispatch custom event для AuthContext
      window.dispatchEvent(new CustomEvent('maintenanceMode', {
        detail: {
          enabled: true,
          message: error.response?.data?.message || 'Site is temporarily unavailable. Maintenance in progress.',
        },
      }));
    }
    
    const originalRequest = error.config as RetryableAxiosConfig | undefined;
    if (!originalRequest) return Promise.reject(error);
    
    // Если токен истек или невалидный (401), пытаемся обновить
    // НО: не обрабатываем ошибки авторизации (login/register) - они должны обрабатываться в компонентах
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/login') ||
                            originalRequest?.url?.includes('/auth/register') ||
                            originalRequest?.url?.includes('/auth/refresh') ||
                            originalRequest?.url?.includes('/auth/logout') ||
                            originalRequest?.url?.includes('/auth/oauth/');
    
    // Для /auth/me: если токена нет, это нормально (пользователь не авторизован)
    // Не показываем ошибку в консоли и не пытаемся обновить токен
    const isMeEndpoint = originalRequest?.url?.includes('/auth/me');
    const hasToken = Boolean(getToken());
    const cookieSessionAvailable = canUseCookieSession();
    
    if (isMeEndpoint && !hasToken && !cookieSessionAvailable) {
      // Токена нет - это нормально, просто возвращаем ошибку без логирования
      return Promise.reject(error);
    }
    
    const shouldTryRefreshForMe = isMeEndpoint && (hasToken || cookieSessionAvailable);

    // Не обрабатываем повторно запросы, которые уже были повторены
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint && (!isMeEndpoint || shouldTryRefreshForMe)) {
      if (isRefreshing) {
        // Если уже обновляем токен, ждем результата
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject, config: originalRequest });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = getRefreshToken();
      
      if (!refreshToken && !cookieSessionAvailable) {
        // Нет refresh token, удаляем токены и перенаправляем
        // Только если это не запрос авторизации и не админ панель
        removeToken();
        // Уведомляем C++ о logout (401 без refresh token)
        notifyCppLogout();
        const isAdminPage = window.location.pathname.includes('/admin');
        if (!isMeEndpoint && !window.location.pathname.includes('/auth') && !isAdminPage) {
          window.location.reload();
        }
        processQueue(error, null);
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        const { access_token } = await refreshAuthSession(refreshToken);
        
        if (!access_token) {
          throw new Error('No access token received from refresh endpoint');
        }

        if (JWT_AUTH_MODE && shouldPersistTokensLocally()) {
          // Обновляем заголовок оригинального запроса
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          if (isPluginEmbed()) {
            try {
              const pluginSession = await axios.post<{ plugin_token: string }>(
                `${API_BASE_URL}/auth/plugin-session`,
                {},
                {
                  baseURL: '',
                  headers: { Authorization: `Bearer ${access_token}` },
                },
              );
              reportPluginSessionToPlugin(pluginSession.data.plugin_token);
            } catch {
              // Browser auth remains valid; plugin actions will request sign-in.
            }
          }
        } else if (originalRequest.headers?.Authorization) {
          delete originalRequest.headers.Authorization;
        }
        
        // Обрабатываем очередь запросов
        processQueue(null, JWT_AUTH_MODE && shouldPersistTokensLocally() ? access_token : null);
        isRefreshing = false;
        
        // Повторяем оригинальный запрос
        return api(originalRequest);
      } catch (refreshError: unknown) {
        if (refreshError instanceof StaleRefreshResponseError) {
          processQueue(refreshError, null);
          isRefreshing = false;
          return Promise.reject(refreshError);
        }
        const currentRefreshToken = getRefreshToken();
        const newerLocalSession = Boolean(
          JWT_AUTH_MODE &&
          shouldPersistTokensLocally() &&
          refreshToken &&
          currentRefreshToken &&
          currentRefreshToken !== refreshToken,
        );
        if (newerLocalSession && getToken()) {
          const currentAccessToken = getToken();
          originalRequest.headers.Authorization = `Bearer ${currentAccessToken}`;
          processQueue(null, currentAccessToken);
          isRefreshing = false;
          return api(originalRequest);
        }

        // Refresh token невалидный, удаляем только ту локальную сессию,
        // которая действительно делала этот запрос.
        removeToken();
        // Уведомляем C++ о logout (refresh failed)
        notifyCppLogout();
        processQueue(refreshError, null);
        isRefreshing = false;
        
        // Не перезагружаем страницу если мы в админке или на странице авторизации
        // И не делаем reload для /auth/me, иначе возникает вечный цикл на гостевой сессии.
        const isAdminPage = window.location.pathname.includes('/admin');
        if (!isMeEndpoint && !window.location.pathname.includes('/auth') && !isAdminPage) {
          window.location.reload();
        }
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: async (data: RegistrationPayload) => {
    const response = await api.post<Token>('/auth/register', data);
    return response.data;
  },

  login: async (data: { email: string; password: string }) => {
    const response = await api.post<Token>('/auth/login', data);
    return response.data;
  },

  createPluginSession: async (): Promise<{ plugin_token: string; expires_in: number; token_type: string }> => {
    const response = await api.post('/auth/plugin-session', {});
    return response.data;
  },

  refresh: async (refreshToken?: string | null) => {
    return refreshAuthSession(refreshToken);
  },

  logout: async (refreshToken?: string | null) => {
    await withAuthSessionLock(async () => {
      const cookieSessionAvailable = canUseCookieSession();
      const currentRefreshToken = getRefreshToken() || refreshToken || null;
      const accessToken = getToken();
      const headers: Record<string, string> = {};
      if (accessToken && JWT_AUTH_MODE) {
        headers.Authorization = `Bearer ${accessToken}`;
      } else if (cookieSessionAvailable) {
        const csrfToken = getCsrfToken();
        if (csrfToken) headers[CSRF_HEADER_NAME] = csrfToken;
      }
      try {
        await axios.post(
          `${API_BASE_URL}/auth/logout`,
          currentRefreshToken ? { refresh_token: currentRefreshToken } : undefined,
          {
            baseURL: '',
            withCredentials: cookieSessionAvailable,
            headers,
          },
        );
      } finally {
        // Keep local removal inside the same lock so another tab cannot begin
        // a refresh between the server response and the logout UI update.
        removeToken();
      }
    });
  },

  getAuthMethods: async (): Promise<AuthMethods> => {
    const response = await api.get<AuthMethods>('/auth/methods');
    return response.data;
  },

  getOAuthUrl: async (provider: string) => {
    const response = await api.get<{ url: string; state: string }>(`/auth/oauth/${provider}/url`);
    return response.data;
  },

  oauthCallback: async (provider: string, code: string, state: string) => {
    const response = await api.post<Token>(`/auth/oauth/${provider}/callback`, { code, state });
    return response.data;
  },

  me: async () => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  getLegalRequirements: async (pack?: LegalPack | null): Promise<LegalRequirements> => {
    const response = await api.get<LegalRequirements>('/auth/legal-requirements', {
      params: pack ? { pack } : undefined,
    });
    return response.data;
  },

  getLegalDocument: async (
    documentType: LegalDocumentType,
    language: string,
    options?: { pack?: LegalPack | null; edition?: string | null },
  ): Promise<LegalDocument> => {
    const response = await api.get<LegalDocument>(`/auth/legal-documents/${documentType}`, {
      params: {
        language,
        ...(options?.pack ? { pack: options.pack } : {}),
        ...(options?.edition ? { edition: options.edition } : {}),
      },
    });
    return response.data;
  },

  acceptLegalDocuments: async (data: LegalAcceptancePayload): Promise<User> => {
    const response = await api.post<User>('/auth/legal-acceptance', data);
    return response.data;
  },

  getMaintenanceStatus: async (): Promise<{ maintenance_mode: boolean; message: string | null }> => {
    const response = await axios.get<{ maintenance_mode?: boolean; maintenance_message?: string | null }>(
      '/health',
      { baseURL: '' }
    );
    return {
      maintenance_mode: Boolean(response.data.maintenance_mode),
      message: response.data.maintenance_message ?? null,
    };
  },

  updateProfile: async (data: Partial<{ username: string; full_name: string | null; country: string | null; password: string; printer_id: number | null; recommend_physical_printer_id: number | null; recommend_printer_profile_id: number | null }>) => {
    const response = await api.patch<User>('/auth/me', data);
    return response.data;
  },

  getPreferences: async () => {
    const response = await api.get<import('../types/api').UserPreferences>('/auth/me/preferences');
    return response.data;
  },

  updatePreferences: async (data: import('../types/api').UserPreferences) => {
    const response = await api.patch<import('../types/api').UserPreferences>('/auth/me/preferences', data);
    return response.data;
  },

  getAccessibleBrands: async (): Promise<AccessibleBrand[]> => {
    const response = await api.get<AccessibleBrand[]>('/auth/me/brands');
    return response.data;
  },

  setActiveBrand: async (
    workspace: { brandId: number | null; organizationId?: number | null },
  ): Promise<User> => {
    const response = await api.put<User>('/auth/me/active-brand', {
      brand_id: workspace.brandId,
      organization_id: workspace.organizationId ?? null,
    });
    return response.data;
  },

  uploadAvatar: async (file: File): Promise<User> => {
    const form = new FormData();
    form.append('file', file);
    const response = await api.post<User>('/auth/me/avatar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  generateApiKey: async () => {
    const response = await api.post<{ api_key: string }>('/auth/api-key');
    return response.data;
  },

  getDeletionStats: async (): Promise<AccountDeletionStats> => {
    const response = await api.get<AccountDeletionStats>('/auth/deletion-stats');
    return response.data;
  },

  getPresetsStats: async (): Promise<{ total_presets: number; synced_presets: number }> => {
    const response = await api.get<{ total_presets: number; synced_presets: number }>('/auth/me/presets-stats');
    return response.data;
  },

  deleteAccount: async (data: { 
    delete_reviews: boolean; 
    release_brand_representation: boolean;
    password_confirm: string;
  }) => {
    await api.delete('/auth/me', {
      data,
    });
  },

  forgotPassword: async (email: string) => {
    const response = await api.post<{ message: string }>('/auth/forgot-password', {
      email,
      language: currentRequestLanguage(),
    });
    return response.data;
  },

  resetPassword: async (token: string, newPassword: string) => {
    const response = await api.post<{ message: string }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    });
    return response.data;
  },

  updateSettings: async (data: {
    allow_filament_presets_import?: boolean;
    allow_filament_presets_export?: boolean;
    allow_printer_profiles_import?: boolean;
    allow_printer_profiles_export?: boolean;
    allow_print_profiles_import?: boolean;
    allow_print_profiles_export?: boolean;
    auto_import_local_presets?: boolean;
    sync_printer_endpoints?: boolean;
  }) => {
    const response = await api.patch<User>('/auth/me/settings', data);
    return response.data;
  },

  updatePassword: async (data: {
    current_password?: string;
    new_password: string;
  }) => {
    const response = await api.patch<User>('/auth/me/password', data);
    return response.data;
  },

  updateEmail: async (data: {
    new_email: string;
  }) => {
    const response = await api.patch<{ message: string }>('/auth/me/email', {
      ...data,
      language: currentRequestLanguage(),
    });
    return response.data;
  },

  verifyEmail: async (token: string) => {
    const response = await api.post<{ message: string }>('/auth/verify-email', { token });
    return response.data;
  },

  rejectRegistration: async (token: string) => {
    const response = await api.post<{ message: string }>(`/auth/reject-registration?token=${encodeURIComponent(token)}`);
    return response.data;
  },

  resendVerification: async () => {
    const response = await api.post<{ message: string }>('/auth/resend-verification');
    return response.data;
  },

  confirmEmailChange: async (token: string) => {
    const response = await api.post<{ message: string }>(`/auth/confirm-email-change?token=${encodeURIComponent(token)}`);
    return response.data;
  },

  updateUsername: async (data: {
    new_username: string;
  }) => {
    const response = await api.patch<User>('/auth/me/username', data);
    return response.data;
  },
};

export const brandTeamAPI = {
  get: async (brandId: number): Promise<BrandTeamWorkspace> => {
    const response = await api.get<BrandTeamWorkspace>(`/brands/${brandId}/team`);
    return response.data;
  },

  invite: async (brandId: number, payload: {
    email: string;
    role: BrandTeamRole;
    all_brands: boolean;
    send_email: boolean;
  }): Promise<BrandTeamInvite> => {
    const response = await api.post<BrandTeamInvite>(`/brands/${brandId}/team/invites`, payload);
    return response.data;
  },

  revokeInvite: async (brandId: number, inviteId: number): Promise<void> => {
    await api.delete(`/brands/${brandId}/team/invites/${inviteId}`);
  },

  updateMember: async (brandId: number, membershipId: number, payload: {
    role: BrandTeamRole;
    all_brands: boolean;
    brand_ids: number[];
  }): Promise<void> => {
    await api.patch(`/brands/${brandId}/team/members/${membershipId}`, payload);
  },

  removeMember: async (brandId: number, membershipId: number): Promise<void> => {
    await api.delete(`/brands/${brandId}/team/members/${membershipId}`);
  },

  transferOwnership: async (brandId: number, targetMembershipId: number): Promise<void> => {
    await api.post(`/brands/${brandId}/team/transfer`, {
      target_membership_id: targetMembershipId,
    });
  },

  decideJoinRequest: async (
    brandId: number,
    requestId: number,
    status: 'approved' | 'rejected',
    rejectionReason?: string,
  ): Promise<void> => {
    await api.patch(`/brands/${brandId}/team/join-requests/${requestId}`, {
      status,
      rejection_reason: rejectionReason,
    });
  },
};

export const brandRepresentativesAPI = {
  list: async (brandId: number): Promise<BrandRepresentative[]> => {
    const response = await api.get<BrandRepresentative[]>(`/brands/${brandId}/representatives`);
    return response.data;
  },

  invite: async (brandId: number, payload: {
    email: string;
    country: string;
    send_email: boolean;
  }): Promise<BrandRepresentativeInvite> => {
    const response = await api.post<BrandRepresentativeInvite>(
      `/brands/${brandId}/representatives/invites`,
      payload,
    );
    return response.data;
  },

  revoke: async (brandId: number, grantId: number): Promise<void> => {
    await api.delete(`/brands/${brandId}/representatives/${grantId}`);
  },
};

// Brands API
export const brandsAPI = {
  myTerritories: async (brandId: number) => {
    const response = await api.get<{
      brand_id: number;
      is_admin: boolean;
      common_managed_by: string | null;
      can_edit_common: boolean;
      can_edit_filament_common: boolean;
      territories: {
        country: string | null;
        manage_brand_country: boolean;
        manage_filament_country: boolean;
        create_filaments: boolean;
      }[];
    }>(`/brands/${brandId}/my-territories`);
    return response.data;
  },

  countryCells: async (brandId: number) => {
    const response = await api.get<BrandCountryCell[]>(`/brands/${brandId}/country-cells`);
    return response.data;
  },

  createCountryCell: async (brandId: number, data: Partial<BrandCountryCell> & { country: string }) => {
    const response = await api.post<BrandCountryCell>(`/brands/${brandId}/country-cells`, data);
    return response.data;
  },

  updateCountryCell: async (brandId: number, country: string, data: Partial<BrandCountryCell>) => {
    const response = await api.patch<BrandCountryCell>(
      `/brands/${brandId}/country-cells/${country}`,
      data,
    );
    return response.data;
  },
  list: async (params?: { page?: number; size?: number; active_only?: boolean; search?: string }) => {
    const response = await api.get<ListResponse<Brand>>('/brands/', { params });
    return response.data;
  },

  get: async (identifier: number | string, includeEmployeesCount?: boolean, country?: string) => {
    const response = await api.get<Brand>(`/brands/${encodeURIComponent(String(identifier))}`, {
      params: {
        ...(includeEmployeesCount ? { include_employees_count: true } : {}),
        // Страна обязана быть в адресе: общий кеш каталога ключуется вместе со
        // строкой запроса, иначе прогретый ответ отдаст чужие данные.
        ...(country ? { country } : {}),
      },
    });
    return response.data;
  },

  suggestSlug: async (name: string): Promise<string> => {
    const response = await api.get<{ slug: string }>('/brands/slug-suggestion', { params: { name } });
    return response.data.slug;
  },

  create: async (data: { name: string; slug?: string; description?: string; website?: string; logo_url?: string }) => {
    const response = await api.post<Brand>('/brands/', data);
    return response.data;
  },

  backfillQr: async (brandId: number) => {
    const response = await api.post<{ assigned: number }>(`/brands/${brandId}/backfill-qr`);
    return response.data;
  },

  update: async (id: number, data: { name?: string; description?: string | null; website?: string | null; logo_url?: string | null; logo_bg?: string | null; social_media_urls?: string[] | null; shop_links?: { platform: string; url: string }[] | null; price_hidden?: boolean; currency?: string }) => {
    const response = await api.patch<Brand>(`/brands/${id}`, data);
    return response.data;
  },

  uploadLogo: async (id: number, file: File): Promise<Brand> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Brand>(`/brands/${id}/logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getUsage: async (id: number): Promise<BrandUsage> => {
    const response = await api.get<BrandUsage>(`/brands/${id}/usage`);
    return response.data;
  },

  getAnalytics: async (id: number): Promise<BrandAnalytics> => {
    const response = await api.get<BrandAnalytics>(`/brands/${id}/analytics`);
    return response.data;
  },
};

// Filaments API
export interface CurrencyRef {
  code: string;
  symbol: string;
  decimals: number;
  rounding_step: number;
  countries: string[];
}

export const currenciesAPI = {
  list: async (): Promise<CurrencyRef[]> => {
    const { data } = await api.get<CurrencyRef[]>('/currencies');
    return data;
  },
};

export const filamentsAPI = {
  countryCells: async (filamentId: number) => {
    const response = await api.get<FilamentCountryCell[]>(`/filaments/${filamentId}/country-cells`);
    return response.data;
  },

  createCountryCell: async (
    filamentId: number,
    data: Partial<FilamentCountryCell> & { country: string },
  ) => {
    const response = await api.post<FilamentCountryCell>(
      `/filaments/${filamentId}/country-cells`,
      data,
    );
    return response.data;
  },

  updateCountryCell: async (
    filamentId: number,
    country: string,
    data: Partial<FilamentCountryCell>,
  ) => {
    const response = await api.patch<FilamentCountryCell>(
      `/filaments/${filamentId}/country-cells/${country}`,
      data,
    );
    return response.data;
  },

  deleteCountryCell: async (filamentId: number, country: string) => {
    await api.delete(`/filaments/${filamentId}/country-cells/${country}`);
  },

  requestCommonEdit: async (filamentId: number, message: string) => {
    const response = await api.post<{ recipients: number }>(
      `/filaments/${filamentId}/common-edit-request`,
      { message },
    );
    return response.data;
  },

  getMaterialTypes: async (): Promise<string[]> => {
    const response = await api.get<string[]>('/filaments/material-types');
    return response.data;
  },
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    brand_id?: number;
    material_type?: string;
    printer_id?: number;
    search?: string;
    country?: string;
    color_group?: import('../types/api').FilamentColorGroup;
    multicolor?: boolean;
  }) => {
    const response = await api.get<FilamentListResponse>('/filaments/', { params });
    return response.data;
  },

  get: async (id: number, country?: string) => {
    const response = await api.get<Filament>(`/filaments/${id}`, {
      params: country ? { country } : undefined,
    });
    return response.data;
  },

  getBySlug: async (brandSlug: string, filamentSlug: string, country?: string) => {
    const response = await api.get<Filament>(
      `/filaments/by-slug/${encodeURIComponent(brandSlug)}/${encodeURIComponent(filamentSlug)}`,
      { params: country ? { country } : undefined },
    );
    return response.data;
  },

  getPresets: async (
    id: number,
    params?: {
      page?: number;
      size?: number;
      is_official?: boolean;
      sort?: 'best' | 'new';
      printer_id?: number;
    },
  ) => {
    const response = await api.get<ListResponse<Preset>>(`/filaments/${id}/presets`, { params });
    return response.data;
  },

  create: async (data: {
    brand_id: number;
    name: string;
    material_type: string;
    visual_settings?: FilamentVisualSettings | null;
    additives?: FilamentAdditive[];
    property_claims?: FilamentPropertyClaim[];
    color_name?: string;
    color_hex?: string;
    color_group?: import('../types/api').FilamentColorGroup | null;
    color_group_source?: import('../types/api').FilamentColorGroupSource;
    ral_code?: string | null;
    diameter?: number;
    density?: number;
    drying_required?: boolean | null;
    drying_temperature_c?: number | null;
    drying_duration_hours?: number | null;
    enclosure_requirement?: import('../types/api').FilamentEnclosureRequirement | null;
    chamber_temperature_c?: number | null;
    bed_adhesives?: string[];
    post_processing_chemicals?: import('../types/api').FilamentChemicalGuidance[];
    price_per_kg?: number;
    spool_weight?: number;
    empty_spool_weight_g?: number;
    recommended_nozzle_temp_min?: number;
    recommended_nozzle_temp_max?: number;
    recommended_bed_temp_min?: number;
    recommended_bed_temp_max?: number;
    required_nozzle_hrc?: number;
    description?: string;
    availability?: FilamentAvailability;
    price_display_unit?: 'per_kg' | 'per_spool';
    line_id?: number | null;
    country_cell?: {
      country: string;
      availability: CountryAvailability;
      price: number | null;
      currency: string | null;
      price_display_unit: 'per_kg' | 'per_spool' | null;
      product_url?: string | null;
      purchase_links?: { platform: string; url: string }[] | null;
      market_note?: string | null;
      market_color_name?: string | null;
    };
  }, confirmSimilar = false) => {
    const response = await api.post<Filament>('/filaments/', data, {
      params: confirmSimilar ? { confirm_similar: true } : undefined,
    });
    return response.data;
  },

  update: async (id: number, data: Partial<{
    name?: string;
    material_type?: string;
    color_name?: string;
    color_hex?: string;
    color_group?: import('../types/api').FilamentColorGroup | null;
    color_group_source?: import('../types/api').FilamentColorGroupSource;
    ral_code?: string | null;
    visual_settings?: FilamentVisualSettings | null;
    additives?: FilamentAdditive[];
    property_claims?: FilamentPropertyClaim[];
    diameter?: number;
    density?: number;
    drying_required?: boolean | null;
    drying_temperature_c?: number | null;
    drying_duration_hours?: number | null;
    enclosure_requirement?: import('../types/api').FilamentEnclosureRequirement | null;
    chamber_temperature_c?: number | null;
    bed_adhesives?: string[];
    post_processing_chemicals?: import('../types/api').FilamentChemicalGuidance[];
    price_per_kg?: number;
    spool_weight?: number;
    empty_spool_weight_g?: number;
    recommended_nozzle_temp_min?: number;
    recommended_nozzle_temp_max?: number;
    recommended_bed_temp_min?: number;
    recommended_bed_temp_max?: number;
    required_nozzle_hrc?: number;
    description?: string;
    active?: boolean;
    availability?: FilamentAvailability;
    price_display_unit?: 'per_kg' | 'per_spool';
    line_id?: number | null;
  }>) => {
    const response = await api.patch<Filament>(`/filaments/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/filaments/${id}`);
  },

  // Reviews
  getReviews: async (id: number, params?: { page?: number; size?: number; active_only?: boolean }) => {
    const response = await api.get<ListResponse<FilamentReview>>(`/filament-reviews/filament/${id}`, { params });
    return response.data;
  },

  getRatingStats: async (id: number) => {
    const response = await api.get<FilamentRatingStats>(`/filament-reviews/filament/${id}/stats`);
    return response.data;
  },
};

// Filament Lines API (группировка вариантов-цвета бренда)
export const filamentLinesAPI = {
  list: async (brandId: number): Promise<FilamentLine[]> => {
    const response = await api.get<FilamentLine[]>('/filament-lines', { params: { brand_id: brandId } });
    return response.data;
  },
  create: async (brandId: number, name: string): Promise<FilamentLine> => {
    const response = await api.post<FilamentLine>('/filament-lines', { name }, { params: { brand_id: brandId } });
    return response.data;
  },
  update: async (id: number, name: string): Promise<FilamentLine> => {
    const response = await api.patch<FilamentLine>(`/filament-lines/${id}`, { name });
    return response.data;
  },
  remove: async (id: number): Promise<void> => {
    await api.delete(`/filament-lines/${id}`);
  },
  createVariants: async (lineId: number, payload: FilamentPalettePayload): Promise<FilamentImportResult> => {
    const response = await api.post<FilamentImportResult>(`/filament-lines/${lineId}/variants`, payload);
    return response.data;
  },
};

// Brand invitations API (admin issues, brands accept)
export const brandInvitesAPI = {
  getByToken: async (token: string): Promise<BrandInvitePublic> => {
    const response = await api.get<BrandInvitePublic>(`/brand-invites/${token}`);
    return response.data;
  },
  accept: async (token: string): Promise<BrandInviteAcceptResult> => {
    const response = await api.post<BrandInviteAcceptResult>(`/brand-invites/${token}/accept`, {});
    return response.data;
  },

  adminCreate: async (payload: {
    email: string;
    target_type: 'new' | 'existing';
    brand_id?: number | null;
    brand_name?: string | null;
    country?: string | null;
    member_role?: 'owner' | 'editor';
    sender_profile?: 'partnerships' | 'pr' | 'transactional';
    language?: EmailLanguage;
    expires_days?: number;
  }): Promise<BrandInviteAdmin> => {
    const response = await api.post<BrandInviteAdmin>('/admin/brand-invites', payload);
    return response.data;
  },
  adminPreviewBatch: async (payload: {
    recipients: string;
    target_type: 'new' | 'existing';
    brand_id?: number | null;
    brand_name?: string | null;
    country?: string | null;
    member_role?: 'owner' | 'editor';
    sender_profile?: 'partnerships' | 'pr' | 'transactional';
    expires_days?: number;
  }): Promise<BrandInviteBatchPreview> => {
    const response = await api.post<BrandInviteBatchPreview>('/admin/brand-invites/batch/preview', payload);
    return response.data;
  },
  adminCreateBatch: async (payload: {
    emails: string[];
    confirmation_token: string;
    target_type: 'new' | 'existing';
    brand_id?: number | null;
    brand_name?: string | null;
    country?: string | null;
    member_role?: 'owner' | 'editor';
    sender_profile?: 'partnerships' | 'pr' | 'transactional';
    language?: EmailLanguage;
    expires_days?: number;
  }): Promise<BrandInviteBatchSendResult> => {
    const response = await api.post<BrandInviteBatchSendResult>('/admin/brand-invites/batch', payload);
    return response.data;
  },
  adminList: async (params: { limit?: number; offset?: number } = {}): Promise<BrandInviteAdmin[]> => {
    const response = await api.get<BrandInviteAdmin[]>('/admin/brand-invites', { params });
    return response.data;
  },
  adminDelete: async (id: number): Promise<void> => {
    await api.delete(`/admin/brand-invites/${id}`);
  },
};

// Filament CSV import API
export const filamentImportAPI = {
  templateUrl: (country?: string | null) => (
    `/api/v1/filament-import/template${country ? `?country=${encodeURIComponent(country)}` : ''}`
  ),
  previewCsv: async (
    brandId: number,
    file: File,
    country?: string | null,
  ): Promise<FilamentImportPreviewResult> => {
    const form = new FormData();
    form.append('file', file);
    const response = await api.post<FilamentImportPreviewResult>('/filament-import/preview', form, {
      params: { brand_id: brandId, ...(country ? { country } : {}) },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  importCsv: async (
    brandId: number,
    file: File,
    confirmationToken: string,
    country?: string | null,
  ): Promise<FilamentImportResult> => {
    const form = new FormData();
    form.append('file', file);
    form.append('confirmation_token', confirmationToken);
    const response = await api.post<FilamentImportResult>('/filament-import', form, {
      params: { brand_id: brandId, ...(country ? { country } : {}) },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};

// Filament Reviews API
export const filamentReviewsAPI = {
  list: async (filamentId: number, params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    order_by?: 'created_at' | 'rating' | 'updated_at';
    order_desc?: boolean;
  }) => {
    const response = await api.get<ListResponse<FilamentReview>>(`/filament-reviews/filament/${filamentId}`, { params });
    return response.data;
  },

  get: async (reviewId: number) => {
    const response = await api.get<FilamentReview>(`/filament-reviews/${reviewId}`);
    return response.data;
  },

  getAvailablePresets: async (filamentId: number) => {
    const response = await api.get<{ items: Preset[]; total: number }>(`/filament-reviews/available-presets/${filamentId}`);
    return response.data;
  },

  create: async (data: {
    filament_id: number;
    preset_id?: number | null;
    success: boolean;
    rating: number; // 1.0 - 5.0
    comment?: string | null;
    printer_model?: string | null;
  }) => {
    const response = await api.post<FilamentReview>('/filament-reviews/', data);
    return response.data;
  },

  update: async (reviewId: number, data: Partial<{
    success?: boolean;
    rating?: number;
    comment?: string | null;
    printer_model?: string | null;
    active?: boolean;
  }>) => {
    const response = await api.patch<FilamentReview>(`/filament-reviews/${reviewId}`, data);
    return response.data;
  },

  delete: async (reviewId: number) => {
    await api.delete(`/filament-reviews/${reviewId}`);
  },

  getStats: async (filamentId: number) => {
    const response = await api.get<FilamentRatingStats>(`/filament-reviews/filament/${filamentId}/stats`);
    return response.data;
  },

  getMyReviews: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
  }) => {
    const response = await api.get<ListResponse<FilamentReview>>('/filament-reviews/my', { params });
    return response.data;
  },
};

// QR Code API
export interface QrScanResponse {
  filament: Filament;
  /** Legacy compatibility field. Recognition never saves a preset. */
  preset_added: boolean;
  preset: Preset | null;
  /** null means the scan was anonymous or no official preset exists. */
  preset_saved: boolean | null;
  /** Present only when the authenticated user already saved this preset. */
  preset_sync_enabled: boolean | null;
}

export const qrAPI = {
  // Получить QR-код изображение (URL)
  getQRCodeURL: (filamentId: number, size: number = 300, branded = false): string => {
    const suffix = branded ? '&branded=true' : '';
    return `${API_BASE_URL}/qr/filaments/${filamentId}/qr-code?size=${size}${suffix}`;
  },

  // Скачать QR-код для печати. Вектор уходит в типографию, растр — на этикетку.
  downloadQRCode: async (
    filamentId: number,
    size: number = 600,
    options: { branded?: boolean; format?: 'png' | 'svg' } = {},
  ): Promise<void> => {
    const { branded = false, format = 'png' } = options;
    const response = await api.get(`/qr/filaments/${filamentId}/qr-code/download`, {
      params: { size, format, ...(branded ? { branded: true } : {}) },
      responseType: 'blob',
    });

    const mark = branded ? '-branded' : '';
    const name = format === 'svg'
      ? `qr-code-${filamentId}${mark}.svg`
      : `qr-code-${filamentId}-${size}x${size}${mark}.png`;
    downloadBlob(response.data, name);
  },

  // Регистрация сканирования QR-кода
  scan: async (shortCode: string): Promise<QrScanResponse> => {
    const response = await api.post(`/qr/${shortCode}/scan`);
    return response.data;
  },

  // Получить пресет по QR-коду
  getPreset: async (shortCode: string): Promise<any> => {
    const response = await api.get(`/qr/${shortCode}/preset`);
    return response.data;
  },
};

// Presets API
export const presetsAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    filament_id?: number;
    printer_id?: number;
    is_official?: boolean;
    user_id?: number;
    search?: string;
    ids?: string;
  }) => {
    const response = await api.get<ListResponse<Preset>>('/presets/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Preset>(`/presets/${id}`);
    return response.data;
  },

  getDraftAnalysis: async (id: number) => {
    const response = await api.get<import('../types/api').PresetDraftAnalysis>(
      `/presets/${id}/draft-analysis`,
    );
    return response.data;
  },

  getDraftQueue: async (limit = 100) => {
    const response = await api.get<import('../types/api').PresetDraftQueue>(
      '/presets/draft-analyses',
      { params: { limit } },
    );
    return response.data;
  },

  recordDraftEvent: async (
    event_type: 'review_opened' | 'important_field_confirmed' | 'filament_matched_or_created' | 'duplicate_prevented',
  ) => {
    await api.post('/presets/draft-events', { event_type });
  },

  getRecommended: async (filament_id: number) => {
    const response = await api.get<RecommendedPreset>(`/presets/recommended/${filament_id}`);
    return response.data;
  },

  getRecommendedForPrinter: async (printer_id: number, filament_id?: number, limit = 20) => {
    const response = await api.get<RecommendedForPrinterResponse>('/presets/recommended-for-printer', {
      params: { printer_id, filament_id, limit },
    });
    return response.data;
  },

  // Recommendations resolved through the printer→configuration chain. The
  // backend derives the catalog model from the configuration; a physical
  // printer, if given, must belong to the user and be linked to the config.
  getRecommendedForConfiguration: async (params: {
    printer_profile_id: number;
    physical_printer_id?: number | null;
    filament_id?: number;
    limit?: number;
  }) => {
    const response = await api.get<RecommendedForPrinterResponse>(
      '/presets/recommended-for-configuration',
      {
        params: {
          printer_profile_id: params.printer_profile_id,
          physical_printer_id: params.physical_printer_id ?? undefined,
          filament_id: params.filament_id,
          limit: params.limit ?? 20,
        },
      },
    );
    return response.data;
  },

  update: async (id: number, data: Partial<{
    name?: string;
    description?: string;
    is_official?: boolean;
    filament_id?: number | null; // Может быть null для черновиков
    extruder_temp?: number;
    bed_temp?: number;
    flow_rate?: number;
    fan_speed?: number;
    retraction_length?: number;
    retraction_speed?: number;
    orcaslicer_settings?: Record<string, unknown> | null;
    rating?: number;
    active?: boolean;
    // УДАЛЕНО: sync_enabled - теперь управляется через user_saved_presets.sync
  }>) => {
    const response = await api.patch<Preset>(`/presets/${id}`, data);
    return response.data;
  },

  create: async (data: {
    filament_id?: number | null; // Может быть null для черновиков
    name: string;
    description?: string;
    is_official: boolean;
    extruder_temp: number;
    bed_temp: number;
    flow_rate?: number;
    fan_speed?: number;
    retraction_length?: number;
    retraction_speed?: number;
    orcaslicer_settings?: Record<string, any> | null; // Расширенные параметры OrcaSlicer
    printer_ids?: number[]; // Список ID принтеров, для которых подходит этот пресет
  }) => {
    const response = await api.post<Preset>('/presets/', data);
    return response.data;
  },

  createOfficial: async (data: {
    filament_id: number;
    source_preset_id?: number | null;
    name: string;
    description?: string;
    is_official: true;
    extruder_temp: number;
    bed_temp: number;
    flow_rate?: number;
    fan_speed?: number;
    retraction_length?: number;
    retraction_speed?: number;
    orcaslicer_settings?: Record<string, any> | null;
    printer_ids?: number[];
  }) => {
    const response = await api.post<Preset>('/presets/official', data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/presets/${id}`);
  },

  activate: async (id: number, filament_id: number) => {
    const response = await api.post<Preset>(`/presets/${id}/activate`, { filament_id });
    return response.data;
  },

  exportOrcaSlicer: async (id: number): Promise<{ data: unknown; contentDisposition?: string }> => {
    const response = await api.get<unknown>(`/presets/${id}/export/orcaslicer.json`, {
      responseType: 'json',
    });
    return {
      data: response.data,
      contentDisposition: response.headers['content-disposition'] || response.headers['Content-Disposition'],
    };
  },
};

export const achievementsAPI = {
  getMine: async () => {
    const response = await api.get<import('../types/api').AchievementOverview>('/achievements/me');
    return response.data;
  },
  evaluateMine: async () => {
    const response = await api.post<import('../types/api').AchievementOverview>('/achievements/me/evaluate');
    return response.data;
  },
};

// Saved Presets API
export const savedPresetsAPI = {
  list: async () => {
    const response = await api.get<{ items: UserSavedPreset[]; total: number }>('/saved-presets/');
    return response.data;
  },

  save: async (preset_id: number, sync = true) => {
    const response = await api.post<UserSavedPreset>('/saved-presets/', { preset_id, sync });
    return response.data;
  },

  unsave: async (preset_id: number) => {
    await api.delete(`/saved-presets/${preset_id}`);
  },

  toggleSync: async (preset_id: number, sync: boolean) => {
    const response = await api.patch<UserSavedPreset>(`/saved-presets/${preset_id}/sync?sync=${sync}`);
    return response.data;
  },

  updateScope: async (preset_id: number, target_printer_profile_ids: number[]) => {
    const response = await api.patch<UserSavedPreset>(`/saved-presets/${preset_id}/scope`, {
      target_printer_profile_ids,
    });
    return response.data;
  },
};

// Preset Version History API
export type PresetVersionAuthor = {
  id: number;
  username: string | null;
};

export type PresetVersionListItem = {
  id: number;
  version_number: number;
  label: string;
  label_description: string | null;
  change_source: string;
  restored_from_version_id: number | null;
  squash_count: number;
  created_at: string;
  updated_at: string;
  created_by: PresetVersionAuthor | null;
};

export type PresetVersionDetail = PresetVersionListItem & {
  snapshot_orcaslicer_settings: Record<string, any> | null;
  snapshot_structured: Record<string, any>;
};

export type PresetVersionDiffChange = {
  key: string;
  label: string;
  unit: string | null;
  old: string | null;
  new: string | null;
};

export type PresetVersionDiffUnmapped = {
  key: string;
  old: string | null;
  new: string | null;
};

export type PresetVersionDiff = {
  from_version: number;
  to_version: number;
  changes: PresetVersionDiffChange[];
  unmapped_changes: PresetVersionDiffUnmapped[];
};

export const presetVersionsAPI = {
  list: async (presetId: number, params?: { labeled_only?: boolean; limit?: number; offset?: number }) => {
    const response = await api.get<{ items: PresetVersionListItem[]; total: number }>(
      `/presets/${presetId}/versions`,
      { params },
    );
    return response.data;
  },

  get: async (presetId: number, versionId: number) => {
    const response = await api.get<PresetVersionDetail>(`/presets/${presetId}/versions/${versionId}`);
    return response.data;
  },

  diff: async (presetId: number, aId: number, bId: number) => {
    const response = await api.get<PresetVersionDiff>(`/presets/${presetId}/versions/${aId}/diff/${bId}`);
    return response.data;
  },

  setLabel: async (presetId: number, versionId: number, label: string, label_description: string | null) => {
    const response = await api.patch<PresetVersionListItem>(
      `/presets/${presetId}/versions/${versionId}`,
      { label, label_description },
    );
    return response.data;
  },

  restore: async (presetId: number, versionId: number) => {
    const response = await api.post<{
      restored_into_version_id: number;
      restored_into_version_number: number;
      restored_from_version_id: number;
    }>(`/presets/${presetId}/versions/${versionId}/restore`);
    return response.data;
  },
};

// Printer Profiles API
type CreatePrinterProfilePayload = {
  name: string;
  slug: string;
  description?: string | null;
  printer_id?: number | null;
  owner_user_id?: number | null;
  vendor?: string | null;
  is_official?: boolean;
  active?: boolean;
  printable_area?: Record<string, number> | string[] | null;
  printable_height_mm?: number | null;
  nozzle_diameters?: number[] | null;
  orcaslicer_settings?: Record<string, any> | null;
  extra_metadata?: Record<string, any> | null;
  start_gcode?: string | null;
  end_gcode?: string | null;
  notes?: string | null;
};

export const printerProfilesAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    is_official?: boolean;
    printer_id?: number;
    owner_user_id?: number;
    search?: string;
  }) => {
    const response = await api.get<ListResponse<PrinterProfile>>('/printer-profiles/', { params });
    return response.data;
  },

  // Fetch all of a user's own configurations across pages (no 100-row truncation).
  listAllOwned: async (ownerUserId: number): Promise<PrinterProfile[]> => {
    const size = 100;
    const first = await printerProfilesAPI.list({
      owner_user_id: ownerUserId, page: 1, size, active_only: false,
    });
    const items = [...first.items];
    for (let page = 2; page <= first.pages; page += 1) {
      const next = await printerProfilesAPI.list({
        owner_user_id: ownerUserId, page, size, active_only: false,
      });
      items.push(...next.items);
    }
    return items;
  },

  get: async (id: number) => {
    const response = await api.get<PrinterProfile>(`/printer-profiles/${id}`);
    return response.data;
  },

  create: async (data: CreatePrinterProfilePayload) => {
    const response = await api.post<PrinterProfile>('/printer-profiles/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<CreatePrinterProfilePayload>) => {
    const response = await api.patch<PrinterProfile>(`/printer-profiles/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/printer-profiles/${id}`);
  },

  exportOrcaSlicer: async (id: number): Promise<Blob> => {
    const response = await api.get<Blob>(`/printer-profiles/${id}/export/orcaslicer.json`, {
      responseType: 'blob',
    });
    return response.data;
  },

  listAllForPrinter: async (printerId: number): Promise<PrinterProfile[]> => {
    const size = 100;
    const first = await printerProfilesAPI.list({
      printer_id: printerId,
      page: 1,
      size,
      active_only: true,
    });
    const items = [...first.items];
    for (let page = 2; page <= first.pages; page += 1) {
      const next = await printerProfilesAPI.list({
        printer_id: printerId,
        page,
        size,
        active_only: true,
      });
      items.push(...next.items);
    }
    return items;
  },
};

// Print Profiles API
type CreatePrintProfilePayload = {
  name: string;
  slug: string;
  description?: string | null;
  category?: string | null;
  owner_user_id?: number | null;
  is_official?: boolean;
  active?: boolean;
  source?: string;
  vendor?: string | null;
  setting_id?: string | null;
  quality_tier?: string | null;
  default_nozzle?: string | null;
  layer_height_mm?: number | null;
  printer_profile_ids?: number[] | null;
  compatible_printers?: string[] | null;
  compatible_filaments?: string[] | null;
  orcaslicer_settings?: Record<string, any>;
  extra_metadata?: Record<string, any> | null;
  notes?: string | null;
};

export const printProfilesAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    is_official?: boolean;
    owner_user_id?: number;
    printer_profile_ids?: number[];
    search?: string;
    category?: string;
  }) => {
    const response = await api.get<ListResponse<PrintProfile>>('/print-profiles/', {
      params,
      paramsSerializer: { indexes: null },
    });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<PrintProfile>(`/print-profiles/${id}`);
    return response.data;
  },

  create: async (data: CreatePrintProfilePayload) => {
    const response = await api.post<PrintProfile>('/print-profiles/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<CreatePrintProfilePayload>) => {
    const response = await api.patch<PrintProfile>(`/print-profiles/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/print-profiles/${id}`);
  },

  exportOrcaSlicer: async (id: number): Promise<Blob> => {
    const response = await api.get<Blob>(`/print-profiles/${id}/export/orcaslicer.json`, {
      responseType: 'blob',
    });
    return response.data;
  },

  listAllOwned: async (ownerUserId: number): Promise<PrintProfile[]> => {
    const size = 100;
    const first = await printProfilesAPI.list({
      owner_user_id: ownerUserId, page: 1, size, active_only: false,
    });
    const items = [...first.items];
    for (let page = 2; page <= first.pages; page += 1) {
      const next = await printProfilesAPI.list({
        owner_user_id: ownerUserId, page, size, active_only: false,
      });
      items.push(...next.items);
    }
    return items;
  },

  listAllForConfigurations: async (printerProfileIds: number[]): Promise<PrintProfile[]> => {
    const ids = Array.from(new Set(printerProfileIds)).sort((left, right) => left - right);
    if (ids.length === 0) return [];
    const size = 100;
    const first = await printProfilesAPI.list({
      printer_profile_ids: ids,
      page: 1,
      size,
      active_only: true,
    });
    const items = [...first.items];
    for (let page = 2; page <= first.pages; page += 1) {
      const next = await printProfilesAPI.list({
        printer_profile_ids: ids,
        page,
        size,
        active_only: true,
      });
      items.push(...next.items);
    }
    return items.filter((profile) => {
      const instantiation = profile.orcaslicer_settings?.instantiation;
      return instantiation !== false && instantiation !== 'false';
    });
  },

};

// Printers API
export const printersAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    manufacturer?: string;
    search?: string;
    ids?: number[];
  }, signal?: AbortSignal) => {
    const response = await api.get<ListResponse<Printer>>('/printers/', {
      params,
      signal,
      // FastAPI reads a repeated query parameter, not the bracketed form axios
      // produces for arrays by default.
      paramsSerializer: { indexes: null },
    });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Printer>(`/printers/${id}`);
    return response.data;
  },

};

// Calculator API
// Brand Requests API
export const brandRequestsAPI = {
  create: async (data: {
    request_type: 'join' | 'create' | 'representative';
    claim_scope?: 'catalog_only' | 'brand' | 'representative';
    country?: string;
    organization_name?: string;
    brand_id?: number;
    new_brand_name?: string;
    new_brand_slug?: string;
    new_brand_description?: string;
    new_brand_website?: string;
    message?: string;
    company_email?: string;
    company_website?: string;
    social_media_urls?: string[];
    proof_text: string;
    proof_files?: string[];
  }) => {
    const response = await api.post<BrandRequest>('/brand-requests/', data);
    return response.data;
  },

  getMy: async () => {
    const response = await api.get<BrandRequest[]>('/brand-requests/my');
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<BrandRequest>(`/brand-requests/${id}`);
    return response.data;
  },

  cancel: async (id: number) => {
    await api.delete(`/brand-requests/${id}`);
  },

  verifySite: async (requestId: number) => {
    const response = await api.post<BrandRequest>(`/brand-requests/${requestId}/verify-site`);
    return response.data;
  },

  uploadFile: async (requestId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<BrandRequest>(`/brand-requests/${requestId}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  deleteFile: async (requestId: number, filePath: string) => {
    const response = await api.delete<BrandRequest>(`/brand-requests/${requestId}/files/${encodeURIComponent(filePath)}`);
    return response.data;
  },
};

/** Verification proof files (brand/printer requests) — served via authed endpoints, not public /uploads */
export const proofFilesAPI = {
  // filePath format: "brand_requests/{id}/{file}" or "printer_requests/{id}/{file}"
  getObjectUrl: async (filePath: string): Promise<string> => {
    return URL.createObjectURL(await proofFilesAPI._fetchProof(filePath));
  },

  _fetchProof: async (filePath: string): Promise<Blob> => {
    const match = filePath.replace(/^\/+/, '').match(/^(brand_requests|printer_requests)\/(\d+)\/([^/]+)$/);
    if (!match) {
      throw new Error(`Invalid proof file path: ${filePath}`);
    }
    const resource = match[1] === 'brand_requests' ? 'brand-requests' : 'printer-requests';
    const response = await api.get<Blob>(`/${resource}/${match[2]}/proof/${encodeURIComponent(match[3])}`, {
      responseType: 'blob',
    });
    return response.data;
  },

  download: async (filePath: string, fileName: string): Promise<void> => {
    downloadBlob(await proofFilesAPI._fetchProof(filePath), fileName);
  },
};

export const calculatorAPI = {
  startTrial: async (): Promise<User> => {
    const response = await api.post<User>('/calculator/start-trial');
    return response.data;
  },

  estimate: async (data: CalculatorEstimateRequest) => {
    const response = await api.post<CalculatorEstimateResponse>('/calculator/estimate', data);
    return response.data;
  },

  preflight: async (data: import('../types/api').CalculatorPreflightRequest) => {
    const response = await api.post<import('../types/api').CalculatorPreflightResponse>('/calculator/preflight', data);
    return response.data;
  },

  parseGcode: async (file: File, plateIndex?: number) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<import('../types/api').CalculatorGcodeParseResponse>('/calculator/parse-gcode', formData, {
      params: plateIndex != null ? { plate_index: plateIndex } : undefined,
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  listHistory: async (params?: { page?: number; size?: number }) => {
    const response = await api.get<import('../types/api').CalculatorHistoryListResponse>('/calculator/history', { params });
    return response.data;
  },

  saveHistory: async (data: import('../types/api').CalculatorHistoryEntryCreate) => {
    const response = await api.post<import('../types/api').CalculatorHistoryEntry>('/calculator/history', data);
    return response.data;
  },

  deleteHistory: async (entryId: number) => {
    await api.delete(`/calculator/history/${entryId}`);
  },

  getProfile: async () => {
    const response = await api.get<CalculatorProfileResponse>('/calculator/profile');
    return response.data;
  },

  updateProfile: async (data: CalculatorProfileUpdate) => {
    const response = await api.put<CalculatorProfileResponse>('/calculator/profile', data);
    return response.data;
  },

  resetProfileDefaults: async () => {
    const response = await api.post<CalculatorProfileResponse>('/calculator/profile/reset-defaults');
    return response.data;
  },

  shareQuote: async (data: import('../types/api').SharedQuoteCreate) => {
    const response = await api.post<import('../types/api').SharedQuoteResponse>('/calculator/quote/share', data);
    return response.data;
  },

  downloadQuotePdf: async (data: import('../types/api').SharedQuoteCreate) => {
    const response = await api.post('/calculator/quote/pdf', data, {
      responseType: 'blob',
    });
    downloadBlob(response.data as Blob, `${data.title || 'quote'}.pdf`);
  },
};

export const crmAPI = {
  getSummary: async () => {
    const response = await api.get<import('../types/api').CrmWorkspaceSummary>('/crm/summary');
    return response.data;
  },

  listCustomers: async (params?: { search?: string; include_archived?: boolean; page?: number; size?: number }) => {
    const response = await api.get<{ items: import('../types/api').CrmCustomer[]; total: number }>('/crm/customers', { params });
    return response.data;
  },

  createCustomer: async (data: import('../types/api').CrmCustomerCreate) => {
    const response = await api.post<import('../types/api').CrmCustomer>('/crm/customers', data);
    return response.data;
  },

  updateCustomer: async (customerId: number, data: import('../types/api').CrmCustomerUpdate) => {
    const response = await api.patch<import('../types/api').CrmCustomer>(`/crm/customers/${customerId}`, data);
    return response.data;
  },

  listQuotes: async (params?: { status?: import('../types/api').CrmQuoteStatus; search?: string; page?: number; size?: number }) => {
    const response = await api.get<{ items: import('../types/api').CrmQuote[]; total: number }>('/crm/quotes', { params });
    return response.data;
  },

  getQuote: async (quoteId: number) => {
    const response = await api.get<import('../types/api').CrmQuoteDetail>(`/crm/quotes/${quoteId}`);
    return response.data;
  },

  createQuote: async (data: import('../types/api').CrmQuoteCreate) => {
    const response = await api.post<import('../types/api').CrmQuoteDetail>('/crm/quotes', data);
    return response.data;
  },

  updateQuote: async (quoteId: number, data: { title?: string; customer_id?: number | null; valid_until?: string | null }) => {
    const response = await api.patch<import('../types/api').CrmQuoteDetail>(`/crm/quotes/${quoteId}`, data);
    return response.data;
  },

  createQuoteVersion: async (quoteId: number, data: import('../types/api').CrmQuoteVersionPayload) => {
    const response = await api.post<import('../types/api').CrmQuoteDetail>(`/crm/quotes/${quoteId}/versions`, data);
    return response.data;
  },

  updateQuoteStatus: async (quoteId: number, status: import('../types/api').CrmQuoteStatus) => {
    const response = await api.post<import('../types/api').CrmQuoteDetail>(`/crm/quotes/${quoteId}/status`, { status });
    return response.data;
  },

  shareQuote: async (quoteId: number) => {
    const response = await api.post<import('../types/api').SharedQuoteResponse>(`/crm/quotes/${quoteId}/share`);
    return response.data;
  },

  createOrder: async (data: import('../types/api').CrmOrderCreate) => {
    const { data: response } = await api.post<import('../types/api').CrmOrder>('/crm/orders', data);
    return response;
  },
  listOrders: async (params?: { status?: import('../types/api').CrmOrderStatus; search?: string; page?: number; size?: number }) => {
    const response = await api.get<{ items: import('../types/api').CrmOrder[]; total: number }>('/crm/orders', { params });
    return response.data;
  },

  updateOrder: async (orderId: number, data: { status?: import('../types/api').CrmOrderStatus; due_date?: string | null; note?: string | null }) => {
    const response = await api.patch<import('../types/api').CrmOrder>(`/crm/orders/${orderId}`, data);
    return response.data;
  },

  replaceOrderReservations: async (
    orderId: number,
    items: import('../types/api').CrmOrderSpoolReservationCreate[],
  ) => {
    const response = await api.put<import('../types/api').CrmOrder>(
      `/crm/orders/${orderId}/reservations`,
      { items },
    );
    return response.data;
  },
};

// ==================== Admin API ====================

export interface AdminMaintenanceInfo {
  enabled: boolean;
  message: string | null;
}

export interface AdminCalculatorSettings {
  paywall_enforced: boolean;
  trial_days: number | null;
  profile_defaults: import('../types/api').CalculatorProfileDefaults;
  counts?: { trialing: number; active: number };
}

export const adminAPI = {
  getMaintenance: async (): Promise<AdminMaintenanceInfo> => {
    const response = await api.get<AdminMaintenanceInfo>('/admin/maintenance');
    return response.data;
  },

  updateMaintenance: async (
    enabled: boolean,
    message: string | null,
  ): Promise<AdminMaintenanceInfo> => {
    const response = await api.post<{ maintenance_mode: AdminMaintenanceInfo }>('/admin/maintenance', {
      enabled,
      message,
    });
    return response.data.maintenance_mode;
  },

  listOrcaSchemaObservations: async (params?: {
    page?: number;
    size?: number;
    status?: OrcaSchemaObservationStatus;
    scope?: OrcaPresetScope;
    search?: string;
  }): Promise<OrcaSchemaObservationListResponse> => {
    const response = await api.get<OrcaSchemaObservationListResponse>(
      '/admin/orca-schema-observations',
      { params },
    );
    return response.data;
  },

  updateOrcaSchemaObservation: async (
    observationId: number,
    status: OrcaSchemaObservationStatus,
  ): Promise<OrcaSchemaObservation> => {
    const response = await api.patch<OrcaSchemaObservation>(
      `/admin/orca-schema-observations/${observationId}`,
      { status },
    );
    return response.data;
  },

  // Printer catalog: data sources (OrcaSlicer is one source; PrusaSlicer/Cura/Bambu may follow)
  getCatalogSourceOrcaInfo: async (): Promise<{
    bundle: {
      exists: boolean;
      path: string;
      size_mb: number | null;
      vendor_count: number | null;
      source: {
        repository: string;
        ref: string;
        commit: string;
        profiles_commit?: string;
        commit_date: string;
        profiles_tree?: string | null;
      } | null;
    };
    catalog: { printers_total: number; printers_system: number };
  }> => {
    const response = await api.get('/admin/catalog/sources/orca/info');
    return response.data;
  },

  importCatalogSourceOrca: async (): Promise<{
    summary: Record<string, number>;
    catalog: { printers_total: number; printers_system: number };
  }> => {
    const response = await api.post('/admin/catalog/sources/orca/import');
    return response.data;
  },

  // Brand Requests
  listBrandRequests: async (params?: { page?: number; size?: number; status?: BrandRequestStatus }): Promise<ListResponse<BrandRequest>> => {
    const response = await api.get<ListResponse<BrandRequest>>('/admin/brand-requests', { params });
    return response.data;
  },
  
  getBrandRequest: async (id: number): Promise<BrandRequest> => {
    const response = await api.get<BrandRequest>(`/admin/brand-requests/${id}`);
    return response.data;
  },
  
  deleteBrandRequest: async (id: number): Promise<void> => {
    await api.delete(`/admin/brand-requests/${id}`);
  },
  
  updateBrandRequest: async (id: number, data: { status: BrandRequestStatus; rejection_reason?: string }): Promise<BrandRequest> => {
    const response = await api.patch<BrandRequest>(`/admin/brand-requests/${id}`, data);
    return response.data;
  },

  // Brands
  listBrands: async (params?: { 
    page?: number; 
    size?: number; 
    verified?: boolean | null;
    active_only?: boolean;
    search?: string;
  }): Promise<{ items: Brand[]; total: number; page: number; size: number; pages: number }> => {
    const response = await api.get<{ items: Brand[]; total: number; page: number; size: number; pages: number }>('/admin/brands', { params });
    return response.data;
  },

  updateBrand: async (id: number, data: {
    name?: string;
    description?: string | null;
    website?: string | null;
    logo_url?: string | null;
    logo_bg?: string | null;
    verified?: boolean;
    active?: boolean;
  }): Promise<Brand> => {
    const response = await api.patch<Brand>(`/admin/brands/${id}`, data);
    return response.data;
  },

  renameBrandSlug: async (
    id: number,
    data: { slug: string; expected_current_slug: string },
  ): Promise<Brand> => {
    const response = await api.post<Brand>(`/admin/brands/${id}/slug`, data);
    return response.data;
  },

  uploadBrandLogo: async (brandId: number, file: File): Promise<Brand> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Brand>(`/admin/brands/${brandId}/logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // Printers
  createPrinter: async (data: {
    name: string;
    manufacturer: string;
    model: string;
    slug: string;
    model_id?: string;
    family?: string;
    technology?: string;
    vendor?: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    nozzle_options?: number[];
    max_extruder_temp?: number;
    max_bed_temp?: number;
    default_materials?: string[];
    extra_metadata?: Record<string, any>;
    image_url?: string;
  }): Promise<Printer> => {
    const response = await api.post<Printer>('/admin/printers', data);
    return response.data;
  },

  updatePrinter: async (id: number, data: {
    name?: string;
    manufacturer?: string;
    model?: string;
    slug?: string;
    model_id?: string;
    family?: string;
    technology?: string;
    vendor?: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    nozzle_options?: number[];
    max_extruder_temp?: number;
    max_bed_temp?: number;
    default_materials?: string[];
    extra_metadata?: Record<string, any>;
    image_url?: string;
    active?: boolean;
  }): Promise<Printer> => {
    const response = await api.patch<Printer>(`/admin/printers/${id}`, data);
    return response.data;
  },

  deletePrinter: async (id: number): Promise<void> => {
    await api.delete(`/admin/printers/${id}`);
  },

  // Printer Requests
  listPrinterRequests: async (params?: { 
    page?: number; 
    size?: number; 
    status?: 'pending' | 'approved' | 'rejected';
  }): Promise<{ items: PrinterRequest[]; total: number }> => {
    const response = await api.get<{ items: PrinterRequest[]; total: number }>('/admin/printer-requests', { params });
    return response.data;
  },

  getPrinterRequest: async (id: number): Promise<PrinterRequest> => {
    const response = await api.get<PrinterRequest>(`/admin/printer-requests/${id}`);
    return response.data;
  },

  updatePrinterRequest: async (id: number, data: { 
    status: 'pending' | 'approved' | 'rejected'; 
    rejection_reason?: string;
  }): Promise<PrinterRequest> => {
    const response = await api.patch<PrinterRequest>(`/admin/printer-requests/${id}`, data);
    return response.data;
  },

  verifyBrand: async (brandId: number): Promise<Brand> => {
    const response = await api.post<Brand>(`/admin/brands/${brandId}/verify`);
    return response.data;
  },
  
  unverifyBrand: async (brandId: number): Promise<Brand> => {
    const response = await api.post<Brand>(`/admin/brands/${brandId}/unverify`);
    return response.data;
  },

  // Presets
  listPendingPresets: async (params?: { page?: number; size?: number }): Promise<Preset[]> => {
    const response = await api.get<Preset[]>('/admin/presets/pending', { params });
    return response.data;
  },

  countPendingPresets: async (): Promise<{ pending_count: number }> => {
    const response = await api.get<{ pending_count: number }>('/admin/presets/pending/count');
    return response.data;
  },

  countUnreadCommunications: async (): Promise<UnreadCommunicationsCount> => {
    const response = await api.get<UnreadCommunicationsCount>('/admin/communications/unread/count');
    return response.data;
  },
  
  approvePreset: async (presetId: number): Promise<Preset> => {
    const response = await api.post<Preset>(`/admin/presets/${presetId}/approve`);
    return response.data;
  },
  
  rejectPreset: async (presetId: number, reason: string): Promise<Preset> => {
    const response = await api.post<Preset>(`/admin/presets/${presetId}/reject`, null, {
      params: { reason },
    });
    return response.data;
  },

  enrichDraftPresets: async (): Promise<{ total: number; enriched: number; skipped: number; errors: number }> => {
    const response = await api.post<{ total: number; enriched: number; skipped: number; errors: number }>(
      '/admin/presets/enrich-all',
    );
    return response.data;
  },

  // Users
  listUsers: async (params?: { page?: number; size?: number; role?: string; active_only?: boolean; with_brand?: boolean; search?: string }): Promise<AdminUserListResponse> => {
    const response = await api.get<AdminUserListResponse>('/admin/users', { params });
    return response.data;
  },
  
  activateUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/activate`);
    return response.data;
  },
  
  previewUserDeletion: async (userId: number): Promise<AccountDeletionStats> => {
    const response = await api.get<AccountDeletionStats>(`/admin/users/${userId}/deletion-preview`);
    return response.data;
  },

  deleteUserAccount: async (userId: number, deleteReviews: boolean): Promise<{ deleted: boolean }> => {
    const response = await api.delete<{ deleted: boolean }>(`/admin/users/${userId}`, {
      data: { delete_reviews: deleteReviews },
    });
    return response.data;
  },

  deactivateUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/deactivate`);
    return response.data;
  },
  
  promoteToAdmin: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/promote-admin`);
    return response.data;
  },

  demoteToUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/demote-to-user`);
    return response.data;
  },

  linkUserToBrand: async (userId: number, brandId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/link-brand?brand_id=${brandId}`, {});
    return response.data;
  },

  unlinkUserFromBrand: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/unlink-brand`);
    return response.data;
  },

  getUserAchievements: async (userId: number): Promise<AdminAchievementOverview> => {
    const response = await api.get<AdminAchievementOverview>(`/admin/users/${userId}/achievements`);
    return response.data;
  },

  grantUserAchievement: async (
    userId: number,
    code: string,
    reason: string,
  ): Promise<AdminAchievementOverview> => {
    const response = await api.post<AdminAchievementOverview>(
      `/admin/users/${userId}/achievements`,
      { code, reason },
    );
    return response.data;
  },

  revokeUserAchievement: async (
    userId: number,
    code: string,
    reason: string,
  ): Promise<AdminAchievementOverview> => {
    const response = await api.post<AdminAchievementOverview>(
      `/admin/users/${userId}/achievements/${code}/revoke`,
      { reason },
    );
    return response.data;
  },

  // Calculator Pro / subscriptions
  setUserProAccess: async (userId: number, grant: boolean): Promise<User> => {
    const response = await api.patch<User>(`/admin/users/${userId}/pro-access`, { grant });
    return response.data;
  },

  getCalculatorSettings: async (): Promise<AdminCalculatorSettings> => {
    const response = await api.get<AdminCalculatorSettings>('/admin/calculator-settings');
    return response.data;
  },

  updateCalculatorSettings: async (
    paywallEnforced: boolean,
    trialDays: number | null,
  ): Promise<AdminCalculatorSettings> => {
    const response = await api.post<AdminCalculatorSettings>(
      '/admin/calculator-settings',
      {
        paywall_enforced: paywallEnforced,
        trial_days: trialDays,
      },
    );
    return response.data;
  },

  updateCalculatorProfileDefaults: async (
    profileDefaults: import('../types/api').CalculatorProfileDefaults,
  ): Promise<import('../types/api').CalculatorProfileDefaults> => {
    const response = await api.put<import('../types/api').CalculatorProfileDefaults>(
      '/admin/calculator-profile-defaults',
      profileDefaults,
    );
    return response.data;
  },

  getCalculatorCountryDefaults: async (
  ): Promise<import('../types/api').CalculatorCountryDefaultsMap> => {
    const response = await api.get<import('../types/api').CalculatorCountryDefaultsMap>(
      '/admin/calculator-country-defaults',
    );
    return response.data;
  },

  updateCalculatorCountryDefaults: async (
    countryDefaults: import('../types/api').CalculatorCountryDefaultsMap,
  ): Promise<import('../types/api').CalculatorCountryDefaultsMap> => {
    const response = await api.put<import('../types/api').CalculatorCountryDefaultsMap>(
      '/admin/calculator-country-defaults',
      countryDefaults,
    );
    return response.data;
  },

  // Notifications
  sendNotification: async (data: {
    user_ids: number[];
    title: string;
    message: string;
    link?: string | null;
  }): Promise<{ success: boolean; message: string; count: number; sent_to: number[] }> => {
    const response = await api.post('/admin/notifications/send', data);
    return response.data;
  },

  // Stats
  getStats: async (refresh?: boolean): Promise<{
    users: {
      total: number; brands: number; admins: number;
      registered_24h: number; registered_7d: number; registered_30d: number;
      active_24h: number; active_7d: number;
    };
    brands: { total: number; verified: number; pending_verification: number };
    presets: { total: number; pending_moderation: number; approved: number; rejected: number };
    content: {
      filaments: number; printers: number; printer_profiles: number;
      reviews_total: number; reviews_7d: number; wiki_articles: number;
    };
    hardware: {
      devices: number; spools: number;
      gate_slots: number; gate_slots_assigned: number;
      sync_devices: number; sync_devices_active_7d: number;
    };
    calculator: {
      available: boolean;
      estimates_24h?: number; estimates_7d?: number; estimates_30d?: number;
      users_24h?: number; users_7d?: number; users_30d?: number;
      methods_30d?: Record<string, number>;
      profiles: number; saved_total: number; saved_30d: number; saved_by_users: number;
      quotes: number; quotes_30d: number;
    };
    feed_systems: {
      total: number; active: number;
      by_kind: Record<string, number>; by_provider: Record<string, number>;
      slots: number; printers_with_system: number;
      devices_happy_hare: number; devices_reporting_feed: number;
      devices_seen_7d: number; devices_seen_30d: number;
    };
    notifications: { unread: number };
  }> => {
    const response = await api.get('/admin/stats', refresh ? { params: { refresh: true } } : undefined);
    return response.data;
  },

  getSetting: async (key: string): Promise<{ key: string; value: string | null }> => {
    const response = await api.get(`/admin/settings/${key}`);
    return response.data;
  },

  setSetting: async (key: string, value: string): Promise<{ key: string; value: string }> => {
    const response = await api.put(`/admin/settings/${key}`, { value });
    return response.data;
  },

  getDockerStats: async (): Promise<{
    containers: Array<{
      name: string; cpu: string; mem_usage: string; mem_perc: string;
      net_io: string; block_io: string; pids: string;
      restart_count: number; status: string;
    }>;
    error?: string;
  }> => {
    const response = await api.get('/admin/docker-stats');
    return response.data;
  },

  // Database Management
  getMigrationHistory: async (): Promise<{
    current_revision: string | null;
    heads: string[];
    migrations: Array<{
      revision: string;
      down_revision: string | null;
      branch_labels: string | null;
      is_head: boolean;
      is_applied: boolean;
      applied_at: string | null;
      description: string | null;
    }>;
  }> => {
    const response = await api.get('/admin/database/migrations');
    return response.data;
  },

  checkDatabaseIntegrity: async (): Promise<{
    is_valid: boolean;
    missing_tables: string[];
    message: string;
  }> => {
    const response = await api.get('/admin/database/integrity');
    return response.data;
  },

  recreateTables: async (): Promise<{
    success: boolean;
    message: string;
    created_tables: string[];
  }> => {
    const response = await api.post('/admin/database/recreate-tables');
    return response.data;
  },

  applyMigration: async (data: { revision: string }): Promise<{
    success: boolean;
    message: string;
    current_revision: string | null;
    validation_errors?: string[] | null;
  }> => {
    const response = await api.post('/admin/database/migrations/apply', data, {
      timeout: 180000, // 3 минуты для применения миграций
    });
    return response.data;
  },

  downgradeMigration: async (data: { revision: string }): Promise<{
    success: boolean;
    message: string;
    current_revision: string | null;
  }> => {
    const response = await api.post('/admin/database/migrations/downgrade', data, {
      timeout: 180000, // 3 минуты для отката миграций
    });
    return response.data;
  },

  getDatabaseStats: async (): Promise<{
    database_name: string;
    database_size: string;
    database_size_bytes: number;
    table_stats: Array<{
      schema: string;
      table: string;
      size: string;
      size_bytes: number;
      column_count: number;
      row_count: number;
    }>;
  }> => {
    const response = await api.get('/admin/database/stats');
    return response.data;
  },

  exportDatabase: async (data: {
    format: string;
    include_data: boolean;
    tables?: string[];
  }): Promise<{
    success: boolean;
    filename: string | null;
    download_url: string | null;
    size: number | null;
    message: string;
  }> => {
    const response = await api.post('/admin/database/export', data);
    return response.data;
  },

  listDatabaseDumps: async (): Promise<{
    dumps: Array<{
      filename: string;
      size: number;
      created_at: string;
      modified_at: string;
      format: string;
    }>;
  }> => {
    const response = await api.get('/admin/database/dumps');
    return response.data;
  },

  deleteDatabaseDump: async (filename: string): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.delete(`/admin/database/dumps/${filename}`);
    return response.data;
  },

  importDatabase: async (
    file: File,
    format: string,
    clean: boolean,
    create?: boolean
  ): Promise<{
    success: boolean;
    message: string;
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/database/import', formData, {
      params: {
        format,
        clean,
        create: create || false,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 600000, // 10 минут таймаут для больших файлов
    });
    return response.data;
  },

  getTableStructure: async (tableName: string, schemaName: string = 'public'): Promise<{
    table_name: string;
    schema_name: string;
    columns: Array<{
      column_name: string;
      data_type: string;
      is_nullable: boolean;
      column_default: string | null;
      character_maximum_length: number | null;
    }>;
    indexes: Array<{ name: string; definition: string }>;
    constraints: Array<{ name: string; type: string }>;
  }> => {
    const response = await api.get(`/admin/database/tables/${tableName}/structure`, {
      params: { schema_name: schemaName },
    });
    return response.data;
  },

  getTableData: async (
    tableName: string,
    params?: {
      schema_name?: string;
      page?: number;
      size?: number;
      order_by?: string;
      order_desc?: boolean;
      search?: string;
    }
  ): Promise<{
    table_name: string;
    schema_name: string;
    columns: string[];
    rows: Array<Record<string, any>>;
    total: number;
    page: number;
    size: number;
    pages: number;
    primary_key_columns: string[];
  }> => {
    const response = await api.get(`/admin/database/tables/${tableName}/data`, { params });
    return response.data;
  },

  updateTableData: async (
    tableName: string,
    data: {
      primary_key: Record<string, any>;
      data: Record<string, any>;
    },
    schemaName?: string
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.patch(`/admin/database/tables/${tableName}/data`, data, {
      params: { schema_name: schemaName || 'public' },
    });
    return response.data;
  },

  deleteTableData: async (
    tableName: string,
    primaryKey: Record<string, any>,
    schemaName?: string
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.delete(`/admin/database/tables/${tableName}/data`, {
      data: primaryKey,
      params: { schema_name: schemaName || 'public' },
    });
    return response.data;
  },

  // Wiki Sync & Export
  syncWiki: async (): Promise<{
    success: boolean;
    message: string;
    created: number;
    updated: number;
    skipped: number;
    errors: number;
    details: Array<{
      file: string;
      status: string;
      title?: string;
      slug?: string;
      category?: string;
      reason?: string;
    }>;
  }> => {
    const response = await api.post('/admin/wiki/sync');
    return response.data;
  },

  exportWiki: async (): Promise<{
    success: boolean;
    message: string;
    exported: number;
    errors: number;
    details: Array<{
      file: string;
      status: string;
      title?: string;
      reason?: string;
    }>;
  }> => {
    const response = await api.post('/admin/wiki/export');
    return response.data;
  },

  exportArticle: async (id: number): Promise<void> => {
    const response = await api.get(`/admin/wiki/export/${id}`, {
      responseType: 'blob',
    });
    const contentDisposition = response.headers['content-disposition'];
    const filename = contentDisposition
      ? contentDisposition.split('filename=')[1]?.replace(/"/g, '')
      : `article-${id}.md`;
    downloadBlob(response.data, filename);
  },
};

// Notifications API
export const notificationsAPI = {
  // Получить список уведомлений
  list: async (params?: { page?: number; size?: number; unread_only?: boolean }): Promise<NotificationListResponse> => {
    const response = await api.get('/notifications/', { params });
    return response.data;
  },

  // Получить количество непрочитанных уведомлений
  getUnreadCount: async (): Promise<{ unread_count: number }> => {
    const response = await api.get('/notifications/unread-count');
    return response.data;
  },

  // Отметить уведомление как прочитанное
  markAsRead: async (notificationId: number): Promise<Notification> => {
    const response = await api.patch(`/notifications/${notificationId}/read`);
    return response.data;
  },

  // Отметить все уведомления как прочитанные
  markAllAsRead: async (): Promise<{ marked_count: number }> => {
    const response = await api.post('/notifications/mark-all-read');
    return response.data;
  },

  // Удалить уведомление
  delete: async (notificationId: number): Promise<{ message: string }> => {
    const response = await api.delete(`/notifications/${notificationId}`);
    return response.data;
  },

  deleteAll: async (readOnly?: boolean): Promise<{ deleted_count: number; message: string }> => {
    const response = await api.delete('/notifications/all', {
      params: readOnly ? { read_only: true } : undefined,
    });
    return response.data;
  },
};

// OrcaSlicer Deleted Presets API
export const orcaslicerDeletedPresetsAPI = {
  // Сообщить об удалённых пресетах
  reportDeletedPresets: async (data: {
    deleted_presets: Array<{
      preset_id: number;
      preset_name: string;
      bundle_preset_name?: string | null;
    }>;
  }): Promise<{
    message: string;
    notification_id?: number | null;
    preset_count?: number | null;
    created_count?: number | null;
    saved_count?: number | null;
    rule?: string | null;
  }> => {
    const response = await api.post('/orcaslicer/deleted-presets', data);
    return response.data;
  },

  // Обработать действие пользователя для удалённого пресета
  handleAction: async (
    notificationId: number,
    data: {
      action: 'restore' | 'delete' | 'skip';
      preset_ids?: number[] | null;
      apply_to_all?: boolean;
      save_rule?: boolean;
    }
  ): Promise<{
    message: string;
    action: string;
    processed_count: number;
    total_count: number;
  }> => {
    const response = await api.post(`/orcaslicer/deleted-presets/${notificationId}/action`, data);
    return response.data;
  },

  // Автоматически обработать удалённые уведомления
  autoProcess: async (): Promise<{
    message: string;
    processed_count: number;
    notifications_processed: number;
  }> => {
    const response = await api.post('/orcaslicer/deleted-presets/auto-process');
    return response.data;
  },
};

// Feedback API
export const feedbackAPI = {
  // Создать обратную связь (требуется авторизация)
  create: async (data: {
    type: FeedbackType;
    subject: string;
    message: string;
    email?: string | null;
    // Source context
    source?: string | null;
    source_url?: string | null;
    source_id?: number | null;
  }): Promise<Feedback> => {
    const response = await api.post<Feedback>('/feedback/', data);
    return response.data;
  },

  // Получить список своей обратной связи
  listMy: async (params?: { page?: number; size?: number }): Promise<FeedbackListResponse> => {
    const response = await api.get<FeedbackListResponse>('/feedback/my/list', { params });
    return response.data;
  },

  get: async (feedbackId: number): Promise<FeedbackDetail> => {
    const response = await api.get<FeedbackDetail>(`/feedback/${feedbackId}`);
    return response.data;
  },

  reply: async (
    feedbackId: number,
    data: { message: string; idempotency_key: string },
  ): Promise<FeedbackDetail> => {
    const response = await api.post<FeedbackDetail>(`/feedback/${feedbackId}/messages`, data);
    return response.data;
  },
};

// Admin Feedback API (только для админов)
export const adminFeedbackAPI = {
  // Получить список всей обратной связи
  list: async (params?: {
    page?: number;
    size?: number;
    status?: string;
    type?: FeedbackType;
    source?: string;
  }): Promise<FeedbackListResponse> => {
    const response = await api.get<FeedbackListResponse>('/feedback/', { params });
    return response.data;
  },

  // Получить обратную связь по ID
  get: async (feedbackId: number): Promise<FeedbackDetail> => {
    const response = await api.get<FeedbackDetail>(`/feedback/${feedbackId}`);
    return response.data;
  },

  // Обновить обратную связь (ответить, изменить статус)
  update: async (feedbackId: number, data: {
    status?: string;
    admin_response?: string | null;
    reply_idempotency_key?: string | null;
  }): Promise<FeedbackDetail> => {
    const response = await api.patch<FeedbackDetail>(`/feedback/${feedbackId}`, data);
    return response.data;
  },

  // Удалить обратную связь
  delete: async (feedbackId: number): Promise<{ success: boolean }> => {
    const response = await api.delete(`/feedback/${feedbackId}`);
    return response.data;
  },
};

// Admin Notifications API (только для админов)
export const adminNotificationsAPI = {
  preview: async (data: {
    audience: NotificationCampaignAudience;
    user_ids?: number[];
    title: string;
    message: string;
    link?: string | null;
  }): Promise<NotificationCampaignPreview> => {
    const response = await api.post<NotificationCampaignPreview>(
      '/admin/communications/broadcasts/preview',
      data,
    );
    return response.data;
  },

  confirm: async (confirmationToken: string): Promise<NotificationCampaignSendResult> => {
    const response = await api.post<NotificationCampaignSendResult>(
      '/admin/communications/broadcasts/confirm',
      { confirmation_token: confirmationToken },
    );
    return response.data;
  },

  cancel: async (campaignId: string): Promise<void> => {
    await api.delete(`/admin/communications/broadcasts/${campaignId}`);
  },

  history: async (params?: { page?: number; size?: number }): Promise<NotificationCampaignHistoryResponse> => {
    const response = await api.get<NotificationCampaignHistoryResponse>(
      '/admin/communications/broadcasts',
      { params },
    );
    return response.data;
  },
};

export const adminCommunicationsAPI = {
  listEmailThreads: async (params?: {
    page?: number;
    size?: number;
    status?: EmailThreadStatus;
  }): Promise<EmailThreadListResponse> => {
    const response = await api.get<EmailThreadListResponse>('/admin/communications/email-threads', { params });
    return response.data;
  },

  createEmailThread: async (data: {
    to: string;
    participant_name?: string;
    subject: string;
    body: string;
    html_body?: string;
    sender_profile: EmailSenderProfile;
    language: EmailLanguage;
    idempotency_key: string;
    attachments?: File[];
  }): Promise<EmailThreadDetail> => {
    const form = new FormData();
    form.append('to', data.to);
    if (data.participant_name) form.append('participant_name', data.participant_name);
    form.append('subject', data.subject);
    form.append('body', data.body);
    if (data.html_body) form.append('html_body', data.html_body);
    form.append('sender_profile', data.sender_profile);
    form.append('language', data.language);
    form.append('idempotency_key', data.idempotency_key);
    data.attachments?.forEach((file) => form.append('attachments', file, file.name));
    const response = await api.post<EmailThreadDetail>('/admin/communications/email-threads', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  getEmailThread: async (threadId: number): Promise<EmailThreadDetail> => {
    const response = await api.get<EmailThreadDetail>(`/admin/communications/email-threads/${threadId}`);
    return response.data;
  },

  markEmailThreadRead: async (threadId: number, throughMessageId: number): Promise<EmailThreadDetail> => {
    const response = await api.post<EmailThreadDetail>(
      `/admin/communications/email-threads/${threadId}/read`,
      { through_message_id: throughMessageId },
    );
    return response.data;
  },

  updateEmailThread: async (threadId: number, status: EmailThreadStatus): Promise<EmailThreadDetail> => {
    const response = await api.patch<EmailThreadDetail>(`/admin/communications/email-threads/${threadId}`, { status });
    return response.data;
  },

  deleteEmailThread: async (threadId: number): Promise<void> => {
    await api.delete(`/admin/communications/email-threads/${threadId}`);
  },

  replyToEmailThread: async (threadId: number, data: {
    body: string;
    html_body?: string;
    sender_profile?: EmailSenderProfile;
    idempotency_key: string;
    attachments?: File[];
  }): Promise<EmailMessage> => {
    const form = new FormData();
    form.append('body', data.body);
    if (data.html_body) form.append('html_body', data.html_body);
    if (data.sender_profile) form.append('sender_profile', data.sender_profile);
    form.append('idempotency_key', data.idempotency_key);
    data.attachments?.forEach((file) => form.append('attachments', file, file.name));
    const response = await api.post<EmailMessage>(
      `/admin/communications/email-threads/${threadId}/reply`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },

  downloadEmailAttachment: async (
    threadId: number,
    messageId: number,
    attachmentIndex: number,
  ): Promise<Blob> => {
    const response = await api.get(
      `/admin/communications/email-threads/${threadId}/messages/${messageId}/attachments/${attachmentIndex}`,
      { responseType: 'blob' },
    );
    return response.data;
  },
};

// Downloads API
export const downloadsAPI = {
  getPluginDownloads: async (signal?: AbortSignal): Promise<PluginDownloadsResponse> => {
    const response = await api.get('/downloads/plugins', { signal });
    return response.data;
  },
};

// Wiki API
export const wikiAPI = {
  getGuideProgress: async (): Promise<WikiGuideProgressResponse> => {
    const response = await api.get<WikiGuideProgressResponse>('/wiki/progress');
    return response.data;
  },

  mergeGuideProgress: async (guideIds: string[]): Promise<WikiGuideProgressResponse> => {
    const response = await api.put<WikiGuideProgressResponse>('/wiki/progress', {
      guide_ids: guideIds,
    });
    return response.data;
  },

  // Categories
  listCategories: async (params?: { page?: number; page_size?: number; space?: WikiSpaceKey; language?: WikiLanguage }): Promise<WikiCategoryListResponse> => {
    const response = await api.get('/wiki/categories', { params });
    return response.data;
  },
  
  getCategory: async (slug: string): Promise<WikiCategory> => {
    const response = await api.get(`/wiki/categories/${slug}`);
    return response.data;
  },
  
  // Articles
  listArticles: async (params?: {
    page?: number;
    page_size?: number;
    category_slug?: string;
    search?: string;
    published_only?: boolean;
    space?: WikiSpaceKey;
    language?: WikiLanguage;
  }): Promise<WikiArticleListResponse> => {
    const response = await api.get('/wiki/articles', { params });
    return response.data;
  },
  
  getArticle: async (slug: string): Promise<WikiArticle> => {
    const response = await api.get(`/wiki/articles/${slug}`);
    return response.data;
  },

  getArticleTranslation: async (slug: string, language: WikiLanguage): Promise<WikiArticleTranslation> => {
    const response = await api.get(`/wiki/articles/${slug}/translation/${language}`);
    return response.data;
  },

  recordArticleView: async (slug: string): Promise<void> => {
    await api.post(`/wiki/articles/${slug}/view`);
  },
  
  searchArticles: async (q: string, params?: { page?: number; page_size?: number; space?: WikiSpaceKey; language?: WikiLanguage }): Promise<WikiArticleListResponse> => {
    const response = await api.get('/wiki/search', { params: { q, ...params } });
    return response.data;
  },

  // Feedback
  getFeedbackStats: async (articleSlug: string): Promise<WikiFeedbackStats> => {
    const response = await api.get(`/wiki/articles/${articleSlug}/feedback/stats`);
    return response.data;
  },

  createFeedback: async (articleSlug: string, data: WikiFeedbackCreate): Promise<WikiFeedback> => {
    const response = await api.post(`/wiki/articles/${articleSlug}/feedback`, data);
    return response.data;
  },

  removeHelpfulMark: async (articleSlug: string): Promise<void> => {
    await api.delete(`/wiki/articles/${articleSlug}/feedback/helpful`);
  },

  listFeedback: async (articleSlug: string, params?: { page?: number; page_size?: number }): Promise<WikiFeedback[]> => {
    const response = await api.get(`/wiki/articles/${articleSlug}/feedback`, { params });
    return response.data;
  },

  listSpaces: async (): Promise<WikiSpace[]> => {
    const response = await api.get('/wiki/spaces');
    return response.data;
  },

  uploadMedia: async (file: File): Promise<{
    id: string;
    url: string;
    mime_type: 'image/webp';
    width: number;
    height: number;
    size_bytes: number;
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/wiki/author/media', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  listStagedMedia: async (): Promise<WikiMediaAsset[]> => {
    const response = await api.get('/wiki/author/media');
    return response.data;
  },

  deleteStagedMedia: async (publicId: string): Promise<void> => {
    await api.delete(`/wiki/author/media/${publicId}`);
  },

  getMediaBlob: async (url: string): Promise<Blob> => {
    const endpoint = url.startsWith(API_BASE_URL) ? url.slice(API_BASE_URL.length) : url;
    const response = await api.get(endpoint, { responseType: 'blob' });
    return response.data;
  },

  createAuthoredArticle: async (data: {
    category_id: number;
    space_key?: WikiSpaceKey;
    language?: WikiLanguage;
    title: string;
    slug?: string | null;
    content_key?: string | null;
    summary: string;
    content: string;
    tags?: string[] | null;
    edit_summary?: string | null;
    publish?: boolean;
  }): Promise<WikiRevision> => {
    const response = await api.post('/wiki/author/articles', data);
    return response.data;
  },

  createRevision: async (articleId: number, data: {
    title?: string;
    summary?: string;
    content?: string;
    tags?: string[] | null;
    edit_summary?: string | null;
  }): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/author/articles/${articleId}/revisions`, data);
    return response.data;
  },

  updateRevision: async (revisionId: number, data: {
    title?: string;
    summary?: string;
    content?: string;
    tags?: string[] | null;
    edit_summary?: string | null;
  }): Promise<WikiRevision> => {
    const response = await api.patch(`/wiki/author/revisions/${revisionId}`, data);
    return response.data;
  },

  submitRevision: async (revisionId: number, editSummary?: string | null): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/author/revisions/${revisionId}/submit`, {
      edit_summary: editSummary ?? null,
    });
    return response.data;
  },

  withdrawRevision: async (revisionId: number): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/author/revisions/${revisionId}/withdraw`);
    return response.data;
  },

  retryRevision: async (revisionId: number): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/author/revisions/${revisionId}/retry`);
    return response.data;
  },

  listReviewableRevisions: async (params?: { page?: number; page_size?: number }): Promise<WikiRevisionListResponse> => {
    const response = await api.get('/wiki/revisions/reviewable', { params });
    return response.data;
  },

  reviewRevision: async (revisionId: number, data: {
    verdict: WikiReviewVerdict;
    comment?: string | null;
    evidence_url?: string | null;
  }): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/revisions/${revisionId}/reviews`, data);
    return response.data;
  },

  listOwnRevisions: async (params?: {
    status?: WikiRevisionStatus;
    page?: number;
    page_size?: number;
  }): Promise<WikiRevisionListResponse> => {
    const response = await api.get('/wiki/author/revisions', { params });
    return response.data;
  },

  listModerationRevisions: async (params?: {
    status?: WikiRevisionStatus;
    page?: number;
    page_size?: number;
  }): Promise<WikiRevisionListResponse> => {
    const response = await api.get('/wiki/moderation/revisions', { params });
    return response.data;
  },

  decideRevision: async (
    revisionId: number,
    data: { decision: 'publish' | 'reject'; review_note?: string | null },
  ): Promise<WikiRevision> => {
    const response = await api.post(`/wiki/moderation/revisions/${revisionId}/decision`, data);
    return response.data;
  },

  listRevisionHistory: async (
    articleSlug: string,
    params?: { page?: number; page_size?: number },
  ): Promise<WikiPublicRevisionListResponse> => {
    const response = await api.get(`/wiki/articles/${articleSlug}/history`, { params });
    return response.data;
  },

  // Admin CRUD
  createArticle: async (data: {
    category_id: number;
    title: string;
    slug: string;
    content_key?: string | null;
    summary: string;
    content: string;
    tags?: string[] | null;
    author?: string | null;
    published?: boolean;
    order?: number;
  }): Promise<WikiArticle> => {
    const response = await api.post<WikiArticle>('/wiki/articles', data);
    return response.data;
  },

  updateArticle: async (id: number, data: {
    category_id?: number;
    title?: string;
    slug?: string;
    summary?: string;
    content?: string;
    tags?: string[] | null;
    author?: string | null;
    published?: boolean;
    order?: number;
  }): Promise<WikiArticle> => {
    const response = await api.patch<WikiArticle>(`/wiki/articles/${id}`, data);
    return response.data;
  },

  deleteArticle: async (id: number): Promise<void> => {
    await api.delete(`/wiki/articles/${id}`);
  },

  createCategory: async (data: {
    name: string;
    slug: string;
    description: string;
    icon?: string | null;
    order?: number;
  }): Promise<WikiCategory> => {
    const response = await api.post<WikiCategory>('/wiki/categories', data);
    return response.data;
  },

  updateCategory: async (id: number, data: {
    name?: string;
    slug?: string;
    description?: string;
    icon?: string | null;
    order?: number;
  }): Promise<WikiCategory> => {
    const response = await api.patch<WikiCategory>(`/wiki/categories/${id}`, data);
    return response.data;
  },

  deleteCategory: async (id: number): Promise<void> => {
    await api.delete(`/wiki/categories/${id}`);
  },
};

// ── Spools API ───────────────────────────────────────────────────────────────

export type SpoolState = 'active' | 'shelf' | 'archived' | 'empty';

export interface SpoolFilamentInfo {
  id: number;
  name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  brand_name: string | null;
  price_per_kg: number | null;
  currency: string | null; // валюта бренда (для price_per_kg)
  required_nozzle_hrc: number | null;
}

export interface UserSpool {
  id: number;
  user_id: number;
  filament_id: number | null;
  filament: SpoolFilamentInfo | null;
  initial_weight_g: number;
  used_weight_g: number;
  remaining_weight_g: number;
  remaining_pct: number;
  price: number | null;
  currency: string | null;
  state: SpoolState;
  source: string;
  lot_nr: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  extra: Record<string, string> | null;
}

export interface SpoolCreatePayload {
  filament_id?: number | null;
  initial_weight_g: number;
  used_weight_g?: number;
  price?: number | null;
  currency?: string | null;
  state?: SpoolState;
  source?: string;
  lot_nr?: string | null;
  comment?: string | null;
}

export interface SpoolUpdatePayload {
  filament_id?: number | null;
  initial_weight_g?: number;
  used_weight_g?: number;
  price?: number | null;
  currency?: string | null;
  state?: SpoolState;
  lot_nr?: string | null;
  comment?: string | null;
}

export interface SpoolManagerFilamentMatch {
  id: number;
  name: string;
  brand_name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  reason: 'name' | 'color_hex' | 'color_name';
}

export interface SpoolManagerPreviewRow {
  row_number: number;
  fingerprint: string;
  status: 'ready' | 'already_imported' | 'invalid';
  spool_name: string;
  vendor: string | null;
  material: string | null;
  color_name: string | null;
  color_hex: string | null;
  serial_number: string | null;
  initial_weight_g: number | null;
  used_weight_g: number | null;
  remaining_weight_g: number | null;
  empty_spool_weight_g: number | null;
  price: number | null;
  currency: string | null;
  suggested_filament: SpoolManagerFilamentMatch | null;
  warnings: string[];
}

export interface SpoolManagerPreviewResponse {
  file_name: string;
  file_sha256: string;
  total_rows: number;
  importable_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  duplicate_rows: number;
  invalid_rows: number;
  rows: SpoolManagerPreviewRow[];
}

export interface SpoolManagerImportResponse {
  created: number;
  skipped_existing: number;
  skipped_unselected: number;
  invalid: number;
  created_spool_ids: number[];
  created_draft_ids: number[];
}

export type SpoolImportSemanticField =
  | 'spool_name'
  | 'vendor'
  | 'material'
  | 'color_name'
  | 'color_hex'
  | 'serial_number'
  | 'initial_weight'
  | 'used_weight'
  | 'remaining_weight'
  | 'empty_spool_weight'
  | 'price'
  | 'currency'
  | 'note'
  | 'density'
  | 'diameter'
  | 'diameter_tolerance'
  | 'flow_rate_compensation'
  | 'nozzle_temperature'
  | 'bed_temperature'
  | 'enclosure_temperature'
  | 'nozzle_temperature_offset'
  | 'bed_temperature_offset'
  | 'enclosure_temperature_offset'
  | 'total_length'
  | 'used_length'
  | 'first_use'
  | 'last_use'
  | 'purchased_from'
  | 'purchased_on';

export type SpoolImportUnit = 'g' | 'kg' | 'mm' | 'm';

export interface SpoolImportColumnMapping {
  fields: Partial<Record<SpoolImportSemanticField, string>>;
  units: Partial<Record<SpoolImportSemanticField, SpoolImportUnit>>;
}

export interface SpoolImportPreviewResponse extends SpoolManagerPreviewResponse {
  detected_format: 'octoprint_spoolmanager_csv' | 'custom_csv' | null;
  detected_label: string | null;
  mapping_required: boolean;
  available_columns: string[];
  sample_rows: Array<Record<string, string>>;
  suggested_mapping: SpoolImportColumnMapping | null;
  required_fields: SpoolImportSemanticField[];
}

export interface SpoolImportResponse extends SpoolManagerImportResponse {
  detected_format: 'octoprint_spoolmanager_csv' | 'custom_csv';
}

export const orcaSlicesAPI = {
  list: async (limit = 20): Promise<OrcaSliceReport[]> => {
    const response = await api.get<OrcaSliceReport[]>('/orcaslicer/slices', { params: { limit } });
    return response.data;
  },

  remove: async (sliceId: number): Promise<void> => {
    await api.delete(`/orcaslicer/slices/${sliceId}`);
  },
};

export const printJobsAPI = {
  list: async (params?: {
    physical_printer_id?: number;
    page?: number;
    size?: number;
  }): Promise<import('../types/api').PrintJobListResponse> => {
    const response = await api.get<import('../types/api').PrintJobListResponse>(
      '/print-jobs',
      { params },
    );
    return response.data;
  },

  create: async (
    payload: import('../types/api').PrintJobCreate,
  ): Promise<import('../types/api').PrintJob> => {
    const response = await api.post<import('../types/api').PrintJob>('/print-jobs', payload);
    return response.data;
  },

  transition: async (
    jobId: number,
    payload: {
      idempotency_key: string;
      status: import('../types/api').PrintJobStatus;
      note?: string | null;
    },
  ): Promise<import('../types/api').PrintJob> => {
    const response = await api.post<import('../types/api').PrintJob>(
      `/print-jobs/${jobId}/events`,
      payload,
    );
    return response.data;
  },
};

export const spoolsAPI = {
  list: async (): Promise<UserSpool[]> => {
    const response = await api.get<UserSpool[]>('/spools');
    return response.data;
  },

  listForFilament: async (filament_id: number): Promise<UserSpool[]> => {
    const response = await api.get<UserSpool[]>('/spools', { params: { filament_id } });
    return response.data;
  },

  usage: async (spoolId: number): Promise<SpoolUsageEvent[]> => {
    const response = await api.get<SpoolUsageEvent[]>(`/spools/${spoolId}/usage`);
    return response.data;
  },

  revertUsage: async (spoolId: number, eventId: number): Promise<SpoolUsageEvent> => {
    const response = await api.post<SpoolUsageEvent>(
      `/spools/${spoolId}/usage/${eventId}/revert`,
    );
    return response.data;
  },

  create: async (payload: SpoolCreatePayload): Promise<UserSpool> => {
    const response = await api.post<UserSpool>('/spools', payload);
    return response.data;
  },

  update: async (id: number, payload: SpoolUpdatePayload): Promise<UserSpool> => {
    const response = await api.patch<UserSpool>(`/spools/${id}`, payload);
    return response.data;
  },

  use: async (id: number, delta_weight_g: number): Promise<UserSpool> => {
    const response = await api.post<UserSpool>(`/spools/${id}/use`, { delta_weight_g });
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/spools/${id}`);
  },

  previewImport: async (
    file: File,
    mapping?: SpoolImportColumnMapping,
  ): Promise<SpoolImportPreviewResponse> => {
    const form = new FormData();
    form.append('file', file);
    if (mapping) form.append('mapping', JSON.stringify(mapping));
    const response = await api.post<SpoolImportPreviewResponse>(
      '/spools/import/preview',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },

  importFile: async (
    file: File,
    fingerprints: string[],
    mapping?: SpoolImportColumnMapping,
  ): Promise<SpoolImportResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('selected_fingerprints', JSON.stringify(fingerprints));
    if (mapping) form.append('mapping', JSON.stringify(mapping));
    const response = await api.post<SpoolImportResponse>(
      '/spools/import',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },

  previewSpoolManager: async (file: File): Promise<SpoolManagerPreviewResponse> => {
    const form = new FormData();
    form.append('file', file);
    const response = await api.post<SpoolManagerPreviewResponse>(
      '/spools/import/spoolmanager/preview',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },

  importSpoolManager: async (
    file: File,
    fingerprints: string[],
  ): Promise<SpoolManagerImportResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('selected_fingerprints', JSON.stringify(fingerprints));
    const response = await api.post<SpoolManagerImportResponse>(
      '/spools/import/spoolmanager',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
  },
};

// ── Devices API ──────────────────────────────────────────────────────────────

export interface UserPrinterDevice {
  id: number;
  logical_id: string;
  user_id: number;
  printer_id: number | null;
  name: string;
  device_fingerprint: string | null;
  supports_hh: boolean;
  gate_count: number | null;
  printer_hostname: string | null;
  has_api_key: boolean;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceCreateWithKeyResponse {
  device: UserPrinterDevice;
  api_key: string;
}

export interface DeviceRegenerateKeyResponse {
  api_key: string;
}

/** gate_status from Happy Hare: -1=unknown, 0=empty, 1=available, 2=available from buffer */
export interface GateState {
  id: number;
  gate_index: number;
  preset_id: number | null;
  spool_id: number | null;
  hh_material: string | null;
  hh_color_hex: string | null;
  hh_status: number | null;
  source: 'hh_snapshot' | 'manual_orca' | 'web_manual' | 'provider_report';
  source_ts: string;
  is_active: boolean;
  updated_at: string;
}

export interface DeviceStateResponse {
  device: UserPrinterDevice;
  gates: GateState[];
}

export interface DeviceRegisterPayload {
  device_fingerprint: string;
  name: string;
  printer_id?: number | null;
  supports_hh?: boolean;
  gate_count?: number | null;
}

export interface SlotAssignPayload {
  preset_id?: number | null;
  spool_id?: number | null;
}

export interface MaterialSlotAssignment {
  id: number;
  preset_id: number | null;
  spool_id: number | null;
  source: string;
  source_ts: string;
  active: boolean;
}

export interface LegacySlotProjection {
  gate_state_id: number;
  preset_id: number | null;
  spool_id: number | null;
  source: string;
  source_ts: string;
  is_active: boolean;
  hh_material: string | null;
  hh_color_hex: string | null;
  hh_status: number | null;
  updated_at: string;
}

export interface MaterialSlot {
  id: number;
  provider_index: number;
  label: string | null;
  kind: string;
  active: boolean;
  assignment: MaterialSlotAssignment | null;
  observation?: MaterialSlotObservation | null;
  legacy_projection: LegacySlotProjection | null;
}

export interface MaterialSlotObservation {
  source: string;
  observed_at: string;
  received_at: string;
  present: boolean | null;
  active_feed: boolean | null;
  material: string | null;
  color_hex: string | null;
  remaining_percent: number | null;
  remaining_grams: number | null;
}

export interface MaterialSystem {
  id: number;
  name: string;
  kind: string;
  provider: string;
  capabilities: string[];
  active: boolean;
  declared_slot_count: number | null;
  slots: MaterialSlot[];
}

export interface PhysicalPrinterConnector {
  id: number;
  material_system_id: number | null;
  provider: string;
  transport: string;
  source_instance_id?: string | null;
  capabilities: string[];
  active: boolean;
  last_seen_at: string | null;
  status_observation?: PhysicalPrinterStatusObservation | null;
}

export interface PhysicalPrinterStatusObservation {
  source: string;
  observed_at: string;
  received_at: string;
  state: string;
  progress_percent: number | null;
  remaining_seconds: number | null;
  current_layer: number | null;
  total_layers: number | null;
  job_name: string | null;
  nozzle_temperature: number | null;
  nozzle_target_temperature: number | null;
  bed_temperature: number | null;
  bed_target_temperature: number | null;
  chamber_temperature: number | null;
  wifi_signal: string | null;
  error_code: string | null;
}

export interface PhysicalPrinter {
  id: number;
  logical_id: string;
  printer_id: number | null;
  name: string;
  printer_profile_ids: number[];
  material_systems: MaterialSystem[];
  connectors: PhysicalPrinterConnector[];
  has_api_key: boolean;
  printer_hostname: string | null;
  reports_feed: boolean;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface OctoPrintToolSlotMapping {
  tool_index: number;
  slot_index: number;
}

export interface OctoPrintBridgeRoutingState {
  mode: 'manual' | 'tools';
  tool_slot_map: OctoPrintToolSlotMapping[];
  revision: number;
  applied_revision: number | null;
}

export interface OctoPrintBridgeStatus {
  configured: boolean;
  paired: boolean;
  pairing_expires_at: string | null;
  last_seen_at: string | null;
  active_slot_index: number | null;
  instance_id: string | null;
  plugin_version: string | null;
  octoprint_version: string | null;
  routing: OctoPrintBridgeRoutingState;
}

export interface OctoPrintPairingCode {
  pairing_code: string;
  expires_at: string;
}

export interface PrinterBridgeStatus {
  configured: boolean;
  paired: boolean;
  pairing_expires_at: string | null;
  last_seen_at: string | null;
  source_instance_id: string | null;
}

export interface PrinterBridgePairingCode {
  pairing_code: string;
  expires_at: string;
}

/** What a machine costs to run, and what the calculator will charge for it. */
export interface PrinterEconomics {
  printer_id: number;
  configured: boolean;
  purchase_cost: number | null;
  residual_value: number | null;
  useful_life_hours: number | null;
  average_power_watts: number | null;
  power_hotend_w: number | null;
  power_bed_w: number | null;
  power_steppers_w: number | null;
  power_electronics_w: number | null;
  maintenance_cost_per_hour: number | null;
  machine_hour_rate: number | null;
  economics_currency: string | null;
  depreciation_per_hour: number;
  electricity_per_hour: number;
  maintenance_per_hour: number;
  machine_cost_per_hour: number;
  effective_machine_hour_rate: number;
  rate_below_cost: boolean;
  calculator_printer_power_w: number;
  calculator_printing_rate_per_hour: number;
  calculator_amortization_rate_per_hour: number;
  calculator_electricity_cost_per_kwh: number;
  sources: Record<string, string>;
}

export interface PrinterEconomicsUpdate {
  purchase_cost?: number | null;
  residual_value?: number | null;
  useful_life_hours?: number | null;
  average_power_watts?: number | null;
  power_hotend_w?: number | null;
  power_bed_w?: number | null;
  power_steppers_w?: number | null;
  power_electronics_w?: number | null;
  maintenance_cost_per_hour?: number | null;
  machine_hour_rate?: number | null;
  economics_currency?: string | null;
}

/** Starting numbers for a machine nobody has measured yet. */
export interface PrinterEconomicsSuggestion {
  printer_id: number;
  machine_class: string;
  confidence: string;
  vendor: string | null;
  model_name: string | null;
  bed_max_mm: number | null;
  extruders: number;
  usage: string;
  average_power_watts: number;
  power_hotend_w: number;
  power_bed_w: number;
  power_steppers_w: number;
  power_electronics_w: number;
  useful_life_hours: number;
  maintenance_cost_per_hour: number;
  orca_time_cost: number | null;
}

// Safe display view of a connection binding. The printer is identified by
// physical_printer_id; the endpoint is a volatile label, never identity.
export interface PrinterConnectionBinding {
  physical_printer_id: number;
  connection_ref: string | null;
  provider: string | null;
  display_endpoint: string | null;
  endpoint_shared: boolean;
  last_seen_at: string;
}

/** What OrcaSlicer had selected at the last sync. */
export interface CurrentPrinterContext {
  printer_profile_id: number;
  physical_printer_id: number | null;
  preset_name: string | null;
  last_seen_at: string;
}

/** A machine the person installed in OrcaSlicer but has not registered here. */
export interface InstalledPrinterCandidate {
  model: string;
  printer_id: number | null;
  printer_profile_id: number | null;
  catalog_name: string | null;
  last_seen_at: string;
}

export interface DeviceUpdatePayload {
  name?: string | null;
  gate_count?: number | null;
  supports_hh?: boolean | null;
  printer_hostname?: string | null;
}

export const devicesAPI = {
  list: async (): Promise<UserPrinterDevice[]> => {
    const response = await api.get<UserPrinterDevice[]>('/devices');
    return response.data;
  },

  register: async (payload: DeviceRegisterPayload): Promise<UserPrinterDevice> => {
    const response = await api.post<UserPrinterDevice>('/devices/register-or-update', payload);
    return response.data;
  },

  update: async (id: number, payload: DeviceUpdatePayload): Promise<UserPrinterDevice> => {
    const response = await api.patch<UserPrinterDevice>(`/devices/${id}`, payload);
    return response.data;
  },

  getState: async (id: number): Promise<DeviceStateResponse> => {
    const response = await api.get<DeviceStateResponse>(`/devices/${id}/state`);
    return response.data;
  },

  createWithKey: async (
    name: string,
    printerId?: number,
    gateCount?: number,
  ): Promise<DeviceCreateWithKeyResponse> => {
    const response = await api.post<DeviceCreateWithKeyResponse>('/devices/create-with-key', {
      name,
      ...(printerId ? { printer_id: printerId } : {}),
      ...(gateCount ? { gate_count: gateCount } : {}),
    });
    return response.data;
  },

  regenerateKey: async (id: number): Promise<DeviceRegenerateKeyResponse> => {
    const response = await api.post<DeviceRegenerateKeyResponse>(`/devices/${id}/regenerate-key`);
    return response.data;
  },

  remove: async (id: number): Promise<void> => {
    await api.delete(`/devices/${id}`);
  },
};

export const physicalPrintersAPI = {
  list: async (): Promise<PhysicalPrinter[]> => {
    const response = await api.get<PhysicalPrinter[]>('/physical-printers');
    return response.data;
  },

  downloadOrcaBundle: async (physicalPrinterId: number): Promise<Blob> => {
    const response = await api.get<Blob>(
      `/physical-printers/${physicalPrinterId}/orcaslicer-bundle`,
      { params: { archive: true }, responseType: 'blob' },
    );
    return response.data;
  },

  economics: async (printerId: number): Promise<PrinterEconomics> => {
    const response = await api.get<PrinterEconomics>(`/physical-printers/${printerId}/economics`);
    return response.data;
  },

  updateEconomics: async (
    printerId: number,
    payload: PrinterEconomicsUpdate,
  ): Promise<PrinterEconomics> => {
    const response = await api.patch<PrinterEconomics>(
      `/physical-printers/${printerId}/economics`,
      payload,
    );
    return response.data;
  },

  economicsSuggestion: async (
    printerId: number,
    usage: string,
  ): Promise<PrinterEconomicsSuggestion> => {
    const response = await api.get<PrinterEconomicsSuggestion>(
      `/physical-printers/${printerId}/economics/suggestion`,
      { params: { usage } },
    );
    return response.data;
  },

  listBindings: async (): Promise<PrinterConnectionBinding[]> => {
    const response = await api.get<PrinterConnectionBinding[]>(
      '/orcaslicer/printer-connections/bindings',
    );
    return response.data;
  },

  /** The machine selected in OrcaSlicer as of the last sync, if any. */
  getCurrent: async (): Promise<CurrentPrinterContext | null> => {
    const response = await api.get<CurrentPrinterContext | null>(
      '/orcaslicer/printer-connections/current',
    );
    return response.data;
  },

  /** Printer models installed in the user's OrcaSlicer but not registered here. */
  listInstalledCandidates: async (): Promise<InstalledPrinterCandidate[]> => {
    const response = await api.get<InstalledPrinterCandidate[]>(
      '/orcaslicer/printer-connections/installed-candidates',
    );
    return response.data;
  },

  create: async (payload: {
    name: string;
    printer_id?: number | null;
    printer_profile_ids?: number[];
  }): Promise<PhysicalPrinter> => {
    const response = await api.post<PhysicalPrinter>('/physical-printers', payload);
    return response.data;
  },

  update: async (
    physicalPrinterId: number,
    payload: { name?: string; printer_id?: number | null },
  ): Promise<PhysicalPrinter> => {
    const response = await api.patch<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}`,
      payload,
    );
    return response.data;
  },

  remove: async (physicalPrinterId: number): Promise<void> => {
    await api.delete(`/physical-printers/${physicalPrinterId}`);
  },

  setConfigurations: async (
    physicalPrinterId: number,
    printerProfileIds: number[],
  ): Promise<PhysicalPrinter> => {
    const response = await api.put<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/configurations`,
      { printer_profile_ids: printerProfileIds },
    );
    return response.data;
  },

  assignSlot: async (
    physicalPrinterId: number,
    materialSlotId: number,
    payload: SlotAssignPayload,
  ): Promise<PhysicalPrinter> => {
    const response = await api.patch<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/material-slots/${materialSlotId}`,
      payload,
    );
    return response.data;
  },

  updateSystem: async (
    physicalPrinterId: number,
    materialSystemId: number,
    payload: { name?: string; slot_count?: number },
  ): Promise<PhysicalPrinter> => {
    const response = await api.patch<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/material-systems/${materialSystemId}`,
      payload,
    );
    return response.data;
  },

  createSystem: async (
    physicalPrinterId: number,
    payload: {
      name: string;
      kind: string;
      provider: string;
      capabilities: Array<'read' | 'write' | 'presence' | 'spool_identity' | 'consumption' | 'local_command'>;
      slot_count?: number;
    },
  ): Promise<PhysicalPrinter> => {
    const response = await api.post<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/material-systems`,
      payload,
    );
    return response.data;
  },

  deleteSystem: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<PhysicalPrinter> => {
    const response = await api.delete<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/material-systems/${materialSystemId}`,
    );
    return response.data;
  },

  clearSystem: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<PhysicalPrinter> => {
    const response = await api.post<PhysicalPrinter>(
      `/physical-printers/${physicalPrinterId}/material-systems/${materialSystemId}/clear`,
    );
    return response.data;
  },
};

export const octoprintBridgeAPI = {
  status: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<OctoPrintBridgeStatus> => {
    const response = await api.get<OctoPrintBridgeStatus>(
      `/octoprint-bridge/connections/${physicalPrinterId}/${materialSystemId}`,
    );
    return response.data;
  },

  issuePairingCode: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<OctoPrintPairingCode> => {
    const response = await api.post<OctoPrintPairingCode>(
      `/octoprint-bridge/connections/${physicalPrinterId}/${materialSystemId}/pairing-code`,
    );
    return response.data;
  },

  updateRouting: async (
    physicalPrinterId: number,
    materialSystemId: number,
    payload: {
      mode: 'manual' | 'tools';
      tool_slot_map: OctoPrintToolSlotMapping[];
      expected_revision: number;
    },
  ): Promise<OctoPrintBridgeRoutingState> => {
    const response = await api.put<OctoPrintBridgeRoutingState>(
      `/octoprint-bridge/connections/${physicalPrinterId}/${materialSystemId}/routing`,
      payload,
    );
    return response.data;
  },

  revoke: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<void> => {
    await api.delete(
      `/octoprint-bridge/connections/${physicalPrinterId}/${materialSystemId}`,
    );
  },
};

export const printerBridgeAPI = {
  status: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<PrinterBridgeStatus> => {
    const response = await api.get<PrinterBridgeStatus>(
      `/printer-bridge/connections/${physicalPrinterId}/${materialSystemId}`,
    );
    return response.data;
  },

  issuePairingCode: async (
    physicalPrinterId: number,
    materialSystemId: number,
  ): Promise<PrinterBridgePairingCode> => {
    const response = await api.post<PrinterBridgePairingCode>(
      `/printer-bridge/connections/${physicalPrinterId}/${materialSystemId}/pairing-code`,
    );
    return response.data;
  },
};

export default api;
