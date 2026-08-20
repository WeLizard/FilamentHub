/** Простая система toast-уведомлений для FilamentHub */

import { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
  replaceKey?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface ToastProps {
  toast: Toast;
  onClose: (id: string) => void;
}

const ToastItem: React.FC<ToastProps> = ({ toast, onClose }) => {
  const { t } = useTranslation();
  useEffect(() => {
    if (toast.duration !== 0) {
      const timer = setTimeout(() => {
        onClose(toast.id);
      }, toast.duration || 5000);
      return () => clearTimeout(timer);
    }
  }, [toast.id, toast.duration, onClose]);

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-400" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
      case 'info':
        return <Info className="w-4 h-4 text-blue-400" />;
    }
  };

  const getBgColor = () => {
    switch (toast.type) {
      case 'success':
        return 'bg-green-900/90 border-green-500';
      case 'error':
        return 'bg-red-900/90 border-red-500';
      case 'warning':
        return 'bg-yellow-900/90 border-yellow-500';
      case 'info':
        return 'bg-blue-900/90 border-blue-500';
    }
  };

  return (
    <div
      className={`${getBgColor()} border rounded-lg shadow-lg p-3 mb-2 flex items-start space-x-2 min-w-[220px] max-w-[360px] transition-all duration-300`}
      style={{
        animation: 'slideIn 0.3s ease-out',
      }}
    >
      <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
      <div className="flex-1 text-xs text-white">
        <div>{toast.message}</div>
        {toast.action && (
          <button
            type="button"
            onClick={() => {
              toast.action?.onClick();
              onClose(toast.id);
            }}
            className="mt-2 rounded-md border border-white/25 bg-white/10 px-2.5 py-1 text-xs font-semibold text-white transition-colors hover:bg-white/20"
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        onClick={() => onClose(toast.id)}
        className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
        aria-label={t('toast.close_button_aria_label')}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

let toastIdCounter = 0;
const toasts: Toast[] = [];
let listeners: Array<(toasts: Toast[]) => void> = [];

// Дедупликация на всю сессию: одинаковые сообщения показываются только 1 раз
const shownMessages = new Set<string>();

// Логирование (включается в режиме разработчика)
const isDeveloperMode = () => {
  try {
    return localStorage.getItem('developerMode') === 'true' || 
           (typeof window !== 'undefined' && window.filamenthub?.developerMode);
  } catch {
    return false;
  }
};

const logToast = (action: string, message: string, type: string, extra?: string) => {
  if (isDeveloperMode()) {
    const timestamp = new Date().toISOString().split('T')[1].slice(0, 12);
    console.log(`[Toast ${timestamp}] ${action}: type=${type}, msg="${message.slice(0, 50)}..."${extra ? `, ${extra}` : ''}`);
  }
};

const notifyListeners = () => {
  listeners.forEach((listener) => listener([...toasts]));
};

export const toast = {
  show: (
    message: string,
    type: ToastType = 'info',
    duration?: number,
    replaceKey?: string,
    action?: Toast['action'],
  ) => {
    // A keyed toast replaces the previous one on the same channel and always
    // shows (no session dedup) — repeated actions like Sync must report each run.
    if (replaceKey) {
      for (let i = toasts.length - 1; i >= 0; i--) {
        if (toasts[i].replaceKey === replaceKey) toasts.splice(i, 1);
      }
    } else {
      const dedupKey = `${type}:${message}`;
      if (shownMessages.has(dedupKey)) {
        logToast('SKIP (duplicate)', message, type, `already shown in session`);
        return null;
      }
      shownMessages.add(dedupKey);
    }
    logToast('SHOW', message, type, `total unique: ${shownMessages.size}`);

    const id = `toast-${++toastIdCounter}`;
    const toastItem: Toast = { id, message, type, duration, replaceKey, action };
    toasts.push(toastItem);
    notifyListeners();
    return id;
  },
  success: (message: string, duration?: number, replaceKey?: string, action?: Toast['action']) => (
    toast.show(message, 'success', duration, replaceKey, action)
  ),
  error: (message: string, duration?: number, replaceKey?: string) => toast.show(message, 'error', duration, replaceKey),
  warning: (message: string, duration?: number, replaceKey?: string) => toast.show(message, 'warning', duration, replaceKey),
  info: (message: string, duration?: number, replaceKey?: string) => toast.show(message, 'info', duration, replaceKey),
  remove: (id: string) => {
    const index = toasts.findIndex((t) => t.id === id);
    if (index !== -1) {
      toasts.splice(index, 1);
      notifyListeners();
    }
  },
  clear: () => {
    toasts.length = 0;
    notifyListeners();
  },
  // Сбросить дедупликацию (вызывать при логауте или смене пользователя)
  resetDedup: () => {
    const count = shownMessages.size;
    shownMessages.clear();
    logToast('RESET', 'Deduplication cleared', 'info', `cleared ${count} entries`);
  },
  // Получить статистику (для отладки)
  getStats: () => ({
    uniqueMessages: shownMessages.size,
    activeToasts: toasts.length,
  }),
};

export const ToastContainer: React.FC = () => {
  const [currentToasts, setCurrentToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const listener = (newToasts: Toast[]) => {
      setCurrentToasts(newToasts);
    };
    listeners.push(listener);
    setCurrentToasts([...toasts]);

    return () => {
      listeners = listeners.filter((l) => l !== listener);
    };
  }, []);

  if (currentToasts.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-4 right-4 z-[99999] flex flex-col items-end">
      {currentToasts.map((toastItem) => (
        <ToastItem key={toastItem.id} toast={toastItem} onClose={(id) => toast.remove(id)} />
      ))}
    </div>
  );
};

