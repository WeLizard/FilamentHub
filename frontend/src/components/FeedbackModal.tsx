/** Модалка обратной связи для бетатестеров и пользователей */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Send, Bug, Lightbulb, HelpCircle, MessageSquare } from 'lucide-react';
import { feedbackAPI } from '../api/client';
import type { FeedbackType } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface FeedbackTypeInfo {
  value: FeedbackType;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  subjectPlaceholder: string;
  messagePlaceholder: string;
  instructions: string;
}

export const FeedbackModal: React.FC<FeedbackModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isHeaderVisible = useHeaderVisible();

  const FEEDBACK_TYPES: FeedbackTypeInfo[] = [
    {
      value: 'bug',
      label: t('feedback.types.bug.label'),
      icon: Bug,
      description: t('feedback.types.bug.description'),
      subjectPlaceholder: t('feedback.types.bug.subjectPlaceholder'),
      messagePlaceholder: t('feedback.types.bug.messagePlaceholder'),
      instructions: t('feedback.types.bug.instructions'),
    },
    {
      value: 'feature',
      label: t('feedback.types.feature.label'),
      icon: Lightbulb,
      description: t('feedback.types.feature.description'),
      subjectPlaceholder: t('feedback.types.feature.subjectPlaceholder'),
      messagePlaceholder: t('feedback.types.feature.messagePlaceholder'),
      instructions: t('feedback.types.feature.instructions'),
    },
    {
      value: 'question',
      label: t('feedback.types.question.label'),
      icon: HelpCircle,
      description: t('feedback.types.question.description'),
      subjectPlaceholder: t('feedback.types.question.subjectPlaceholder'),
      messagePlaceholder: t('feedback.types.question.messagePlaceholder'),
      instructions: t('feedback.types.question.instructions'),
    },
    {
      value: 'other',
      label: t('feedback.types.other.label'),
      icon: MessageSquare,
      description: t('feedback.types.other.description'),
      subjectPlaceholder: t('feedback.types.other.subjectPlaceholder'),
      messagePlaceholder: t('feedback.types.other.messagePlaceholder'),
      instructions: t('feedback.types.other.instructions'),
    },
  ];
  
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
      console.error('Feedback submission error:', err);
      setError(err?.response?.data?.detail || err?.message || t('feedback.sendError'));
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
      className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[72px] md:pt-[88px]' : ''}`}
      onClick={onClose}
      onKeyDown={handleKeyDown}
    >
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="fixed inset-0 flex items-end md:items-center justify-center pointer-events-none p-0 md:p-4"
        style={{ top: isHeaderVisible ? '72px' : '0' }}
      >
        <div
          className={`bg-gradient-to-br from-gray-900 to-gray-800 rounded-t-2xl md:rounded-2xl shadow-2xl border-t md:border border-white/20 w-full md:max-w-2xl ${isHeaderVisible ? 'max-h-[calc(100vh-80px)] md:max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'} overflow-hidden flex flex-col pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-3 md:gap-4 px-4 md:px-6 pt-4 md:pt-6 pb-3 md:pb-4 border-b border-white/10">
            <div>
              <h2 className="text-lg md:text-2xl font-semibold text-white">{t('feedback.title')}</h2>
              <p className="text-xs md:text-sm text-gray-400 mt-0.5 md:mt-1">
                {t('feedback.subtitle')}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors p-2 -mt-1 md:-mt-2 -mr-1 md:-mr-2"
              disabled={isSubmitting}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-4 md:px-6 py-3 md:py-4 space-y-3 md:space-y-4 custom-scrollbar">
            {success ? (
              <div className="bg-green-500/20 border border-green-500/40 rounded-xl p-4 text-center">
                <div className="text-green-400 font-medium mb-1">{t('feedback.thankYou')}</div>
                <div className="text-sm text-gray-300">{t('feedback.messageSent')}</div>
              </div>
            ) : (
              <>
                {/* Type Selection */}
                <div>
                  <label className="block text-xs md:text-sm font-medium text-gray-300 mb-2">
                    {t('feedback.typeLabel')} *
                  </label>
                  {/* Мобильная версия: компактные кнопки 2x2 */}
                  <div className="grid grid-cols-2 gap-2 md:hidden">
                    {FEEDBACK_TYPES.map(({ value, label, icon: Icon }) => (
                      <button
                        key={value}
                        type="button"
                        onClick={() => handleTypeChange(value)}
                        className={`flex items-center justify-center gap-2 p-2.5 rounded-lg border transition-all ${
                          type === value
                            ? 'border-purple-500 bg-purple-500/20 text-white'
                            : 'border-white/10 bg-white/5 text-gray-300 hover:bg-white/10 active:bg-white/15'
                        }`}
                      >
                        <Icon className={`w-4 h-4 flex-shrink-0 ${type === value ? 'text-purple-400' : 'text-gray-400'}`} />
                        <span className="font-medium text-xs">{label}</span>
                      </button>
                    ))}
                  </div>
                  {/* Десктопная версия: полные кнопки с описаниями */}
                  <div className="hidden md:grid grid-cols-2 gap-2">
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
                  <label htmlFor="feedback-subject" className="block text-xs md:text-sm font-medium text-gray-300 mb-1.5 md:mb-2">
                    {t('feedback.subjectLabel')} *
                  </label>
                  <input
                    id="feedback-subject"
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    required
                    maxLength={200}
                    placeholder={currentTypeInfo.subjectPlaceholder}
                    className="w-full px-3 md:px-4 py-2.5 md:py-2 bg-white/5 border border-white/10 rounded-lg text-sm md:text-base text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                    disabled={isSubmitting}
                  />
                </div>

                {/* Message */}
                <div>
                  <label htmlFor="feedback-message" className="block text-xs md:text-sm font-medium text-gray-300 mb-1.5 md:mb-2">
                    {t('feedback.messageLabel')} *
                  </label>
                  <textarea
                    id="feedback-message"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    required
                    rows={5}
                    placeholder={currentTypeInfo.messagePlaceholder}
                    className="w-full px-3 md:px-4 py-2.5 md:py-2 bg-white/5 border border-white/10 rounded-lg text-sm md:text-base text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none custom-scrollbar md:font-mono"
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
            <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2 sm:gap-3 px-4 md:px-6 py-3 md:py-4 border-t border-white/10">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2.5 sm:py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 active:bg-white/15 transition-all"
                disabled={isSubmitting}
              >
                {t('feedback.cancel')}
              </button>
              <button
                type="submit"
                onClick={handleSubmit}
                disabled={isSubmitting || !subject.trim() || !message.trim()}
                className="px-4 py-2.5 sm:py-2 rounded-lg bg-purple-600 hover:bg-purple-700 active:bg-purple-800 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>{t('feedback.sending')}</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>{t('feedback.send')}</span>
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

