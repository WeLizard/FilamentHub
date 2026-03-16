/** Хук для обработки уведомлений от OrcaSlicer */

import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '../components/Toast';

// Логирование (включается в режиме разработчика)
const isDeveloperMode = () => {
  try {
    return localStorage.getItem('developerMode') === 'true' || 
           (typeof window !== 'undefined' && (window as any).filamenthub?.developerMode);
  } catch {
    return false;
  }
};

const logNotification = (action: string, data: any) => {
  if (isDeveloperMode()) {
    const timestamp = new Date().toISOString().split('T')[1].slice(0, 12);
    console.log(`[OrcaNotification ${timestamp}] ${action}:`, data);
  }
};

export const useOrcaSlicerNotifications = () => {
  const queryClient = useQueryClient();

  useEffect(() => {
    // Проверяем, запущен ли frontend внутри OrcaSlicer
    const isInOrcaSlicer = typeof window !== 'undefined' && (
      (window as any).filamenthub?.importProfile ||
      (window as any).wx?.postMessage
    );

    if (!isInOrcaSlicer) {
      return;
    }

    logNotification('INIT', { isInOrcaSlicer: true, currentPath: window.location.pathname });

    // Обработчик сообщений от OrcaSlicer
    const handleMessage = (event: MessageEvent) => {
      try {
        // Парсим сообщение (может быть строкой или объектом)
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        
        // Обрабатываем команду sync_complete — обновляем данные после синхронизации
        if (data.command === 'sync_complete') {
          logNotification('SYNC_COMPLETE', { timestamp: Date.now() });
          queryClient.invalidateQueries({ queryKey: ['presets'] });
          queryClient.invalidateQueries({ queryKey: ['user-presets'] });
          queryClient.invalidateQueries({ queryKey: ['my-presets'] });
          queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
          queryClient.invalidateQueries({ queryKey: ['my-presets-stats'] });
          return;
        }

        // Обрабатываем команду show_notification
        if (data.command === 'show_notification') {
          const message = data.message || 'Уведомление';
          const type = data.type || 'info';
          
          // Логируем получение уведомления от C++
          logNotification('RECEIVED', { 
            command: data.command, 
            type, 
            message: message.slice(0, 80),
            currentPath: window.location.pathname,
            timestamp: Date.now()
          });
          
          // Показываем toast-уведомление
          let result: string | null = null;
          switch (type) {
            case 'success':
              result = toast.success(message);
              break;
            case 'error':
              result = toast.error(message);
              break;
            case 'warning':
              result = toast.warning(message);
              break;
            case 'info':
            default:
              result = toast.info(message);
              break;
          }
          
          // Логируем результат (показан или отфильтрован)
          logNotification(result ? 'SHOWN' : 'FILTERED', { type, shown: !!result });
        }
      } catch (e) {
        // Игнорируем сообщения, которые не являются уведомлениями от OrcaSlicer
      }
    };

    // Добавляем обработчик для window.postMessage (от OrcaSlicer)
    window.addEventListener('message', handleMessage);

    // Также добавляем функцию showNotification в window.filamenthub (если её еще нет)
    if (typeof window !== 'undefined' && (window as any).filamenthub) {
      (window as any).filamenthub.showNotification = (message: string, type: string = 'info') => {
        switch (type) {
          case 'success':
            toast.success(message);
            break;
          case 'error':
            toast.error(message);
            break;
          case 'warning':
            toast.warning(message);
            break;
          case 'info':
          default:
            toast.info(message);
            break;
        }
      };
    }

    // Cleanup при размонтировании
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, []);
};

