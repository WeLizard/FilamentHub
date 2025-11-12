/** Хук для обработки уведомлений от OrcaSlicer */

import { useEffect } from 'react';
import { toast } from '../components/Toast';

export const useOrcaSlicerNotifications = () => {
  useEffect(() => {
    // Проверяем, запущен ли frontend внутри OrcaSlicer
    const isInOrcaSlicer = typeof window !== 'undefined' && (
      (window as any).filamenthub?.importProfile ||
      (window as any).wx?.postMessage
    );

    if (!isInOrcaSlicer) {
      return;
    }

    // Обработчик сообщений от OrcaSlicer
    const handleMessage = (event: MessageEvent) => {
      try {
        // Парсим сообщение (может быть строкой или объектом)
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        
        // Обрабатываем команду show_notification
        if (data.command === 'show_notification') {
          const message = data.message || 'Уведомление';
          const type = data.type || 'info';
          
          // Показываем toast-уведомление
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

