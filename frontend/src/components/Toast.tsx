/** Простая система toast-уведомлений для FilamentHub */

import { useEffect, useState } from 'react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastProps {
  toast: Toast;
  onClose: (id: string) => void;
}

const ToastItem: React.FC<ToastProps> = ({ toast, onClose }) => {
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
        return <CheckCircle className="w-5 h-5 text-green-400" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-400" />;
      case 'warning':
        return <AlertTriangle className="w-5 h-5 text-yellow-400" />;
      case 'info':
        return <Info className="w-5 h-5 text-blue-400" />;
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
      className={`${getBgColor()} border rounded-lg shadow-lg p-4 mb-3 flex items-start space-x-3 min-w-[300px] max-w-[500px] transition-all duration-300`}
      style={{
        animation: 'slideIn 0.3s ease-out',
      }}
    >
      <div className="flex-shrink-0 mt-0.5">{getIcon()}</div>
      <div className="flex-1 text-sm text-white">{toast.message}</div>
      <button
        onClick={() => onClose(toast.id)}
        className="flex-shrink-0 text-gray-400 hover:text-white transition-colors"
        aria-label="Закрыть"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

let toastIdCounter = 0;
const toasts: Toast[] = [];
let listeners: Array<(toasts: Toast[]) => void> = [];

const notifyListeners = () => {
  listeners.forEach((listener) => listener([...toasts]));
};

export const toast = {
  show: (message: string, type: ToastType = 'info', duration?: number) => {
    const id = `toast-${++toastIdCounter}`;
    const toast: Toast = { id, message, type, duration };
    toasts.push(toast);
    notifyListeners();
    return id;
  },
  success: (message: string, duration?: number) => toast.show(message, 'success', duration),
  error: (message: string, duration?: number) => toast.show(message, 'error', duration),
  warning: (message: string, duration?: number) => toast.show(message, 'warning', duration),
  info: (message: string, duration?: number) => toast.show(message, 'info', duration),
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
      {currentToasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={toast.remove} />
      ))}
    </div>
  );
};

