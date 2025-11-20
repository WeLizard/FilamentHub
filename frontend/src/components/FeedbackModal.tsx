/** Модалка обратной связи для бетатестеров и пользователей */

import { useState } from 'react';
import { X, Send, Bug, Lightbulb, HelpCircle, MessageSquare } from 'lucide-react';
import { feedbackAPI } from '../api/client';
import type { FeedbackType } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const FEEDBACK_TYPES: Array<{ 
  value: FeedbackType; 
  label: string; 
  icon: React.ComponentType<{ className?: string }>; 
  description: string;
  subjectPlaceholder: string;
  messagePlaceholder: string;
  instructions: string;
}> = [
  { 
    value: 'bug', 
    label: 'Ошибка', 
    icon: Bug, 
    description: 'Сообщить об ошибке или баге',
    subjectPlaceholder: 'Например: "Ошибка при создании пресета на странице материала"',
    messagePlaceholder: `Опишите проблему подробно:

1. Что вы делали перед появлением ошибки? (шаги воспроизведения)
2. Какое поведение вы ожидали?
3. Что произошло на самом деле?
4. На какой странице/в каком разделе возникла ошибка?
5. Используете ли вы браузер на мобильном или десктопе?
6. Есть ли скриншоты или сообщения об ошибке?

Чем подробнее вы опишете проблему, тем быстрее мы её исправим!`,
    instructions: 'Для багов важно описать шаги воспроизведения и ожидаемое поведение'
  },
  { 
    value: 'feature', 
    label: 'Предложение', 
    icon: Lightbulb, 
    description: 'Предложить новую функцию',
    subjectPlaceholder: 'Например: "Добавить фильтр по рейтингу материалов"',
    messagePlaceholder: `Опишите ваше предложение:

1. Какую функцию вы хотели бы видеть?
2. Для чего она будет полезна?
3. Как вы её себе представляете?
4. Есть ли примеры из других сервисов, которые можно взять за основу?

Ваши идеи помогают сделать FilamentHub лучше!`,
    instructions: 'Опишите функцию, её назначение и как она должна работать'
  },
  { 
    value: 'question', 
    label: 'Вопрос', 
    icon: HelpCircle, 
    description: 'Задать вопрос',
    subjectPlaceholder: 'Например: "Как синхронизировать пресеты с OrcaSlicer?"',
    messagePlaceholder: `Задайте ваш вопрос:

Опишите что вас интересует или с чем нужна помощь. Мы постараемся ответить как можно скорее!`,
    instructions: 'Задайте ваш вопрос, и мы обязательно ответим'
  },
  { 
    value: 'other', 
    label: 'Другое', 
    icon: MessageSquare, 
    description: 'Другая обратная связь',
    subjectPlaceholder: 'Кратко опишите суть обращения',
    messagePlaceholder: `Опишите ваш вопрос, предложение или проблему подробно.

Ваша обратная связь очень важна для нас!`,
    instructions: 'Опишите вашу обратную связь подробно'
  },
];

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ isOpen, onClose }) => {
  const { user } = useAuth();
  const isHeaderVisible = useHeaderVisible();
  
  const [type, setType] = useState<FeedbackType>('bug');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Получаем текущий тип обратной связи
  const currentTypeInfo = FEEDBACK_TYPES.find(t => t.value === type) || FEEDBACK_TYPES[0];

  // Показываем модалку только для авторизованных пользователей
  if (!isOpen || !user) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await feedbackAPI.create({
        type,
        subject: subject.trim(),
        message: message.trim(),
        email: null, // Email не нужен для авторизованных пользователей
      });

      setSuccess(true);
      // Очищаем форму
      setTimeout(() => {
        setSubject('');
        setMessage('');
        setType('bug');
        setSuccess(false);
        onClose();
      }, 2000);
    } catch (err: any) {
      console.error('Ошибка отправки обратной связи:', err);
      setError(err?.response?.data?.detail || err?.message || 'Не удалось отправить сообщение. Попробуйте позже.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTypeChange = (newType: FeedbackType) => {
    setType(newType);
    // Очищаем сообщение при смене типа, чтобы показать новый плейсхолдер
    if (message.trim() === '') {
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[88px]' : ''}`}
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="fixed inset-0 flex items-center justify-center pointer-events-none p-4"
        style={{ top: isHeaderVisible ? '88px' : '0' }}
      >
        <div
          className={`bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-2xl w-full ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'} overflow-hidden flex flex-col pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-white/10">
            <div>
              <h2 className="text-2xl font-semibold text-white">Обратная связь</h2>
              <p className="text-sm text-gray-400 mt-1">
                Сообщите о багах, предложите функции или задайте вопрос
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors p-2 -mt-2 -mr-2"
              disabled={isSubmitting}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-4 space-y-4 custom-scrollbar">
            {success ? (
              <div className="bg-green-500/20 border border-green-500/40 rounded-xl p-4 text-center">
                <div className="text-green-400 font-medium mb-1">Спасибо за обратную связь!</div>
                <div className="text-sm text-gray-300">Ваше сообщение отправлено. Мы рассмотрим его в ближайшее время.</div>
              </div>
            ) : (
              <>
                {/* Type Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Тип обращения *
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {FEEDBACK_TYPES.map(({ value, label, icon: Icon, description }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => handleTypeChange(value)}
                        className={`flex items-start gap-3 p-3 rounded-lg border transition-all text-left ${
                          type === value
                            ? 'border-purple-500 bg-purple-500/20 text-white'
                            : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10 hover:border-white/20'
                        }`}
                      >
                        <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${type === value ? 'text-purple-400' : 'text-gray-400'}`} />
                        <div>
                          <div className="font-medium text-sm">{label}</div>
                          <div className="text-xs text-gray-400 mt-0.5">{description}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                  
                  {/* Инструкции для выбранного типа */}
                  {currentTypeInfo.instructions && (
                    <div className="mt-2 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                      <p className="text-xs text-blue-300">{currentTypeInfo.instructions}</p>
                    </div>
                  )}
                </div>

                {/* Subject */}
                <div>
                  <label htmlFor="feedback-subject" className="block text-sm font-medium text-gray-300 mb-2">
                    Тема *
                  </label>
                  <input
                    id="feedback-subject"
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    required
                    maxLength={200}
                    placeholder={currentTypeInfo.subjectPlaceholder}
                    className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    disabled={isSubmitting}
                  />
                </div>

                {/* Message */}
                <div>
                  <label htmlFor="feedback-message" className="block text-sm font-medium text-gray-300 mb-2">
                    Сообщение *
                  </label>
                  <textarea
                    id="feedback-message"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    required
                    rows={8}
                    placeholder={currentTypeInfo.messagePlaceholder}
                    className="w-full px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar font-mono text-sm"
                    disabled={isSubmitting}
                  />
                </div>

                {/* Error */}
                {error && (
                  <div className="bg-red-500/20 border border-red-500/40 rounded-lg p-3 text-red-400 text-sm">
                    {error}
                  </div>
                )}
              </>
            )}
          </form>

          {/* Footer */}
          {!success && (
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-white/10">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 transition-all"
                disabled={isSubmitting}
              >
                Отмена
              </button>
              <button
                type="submit"
                onClick={handleSubmit}
                disabled={isSubmitting || !subject.trim() || !message.trim()}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Отправка...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Отправить
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

