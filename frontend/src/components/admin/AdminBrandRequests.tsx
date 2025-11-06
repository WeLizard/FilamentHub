/** Компонент для управления заявками на верификацию брендов */

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, CheckCircle, XCircle, Eye, Download, Clock, Building2, UserPlus, Trash2 } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { BrandRequest, BrandRequestStatus } from '../../types/api';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { useHeaderVisible } from '../../hooks/useHeaderVisible';

export function AdminBrandRequests() {
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();
  const [selectedStatus, setSelectedStatus] = useState<BrandRequestStatus | 'all'>('all');
  const [selectedRequest, setSelectedRequest] = useState<BrandRequest | null>(null);
  const [page, setPage] = useState(1);
  const [rejectionReason, setRejectionReason] = useState('');
  const [deleteRequestId, setDeleteRequestId] = useState<number | null>(null); // ID заявки для удаления

  // Загрузка заявок
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-brand-requests', selectedStatus, page],
    queryFn: () => adminAPI.listBrandRequests({
      page,
      size: 20,
      status: selectedStatus === 'all' ? undefined : selectedStatus,
    }),
  });

  // Одобрение заявки
  const approveMutation = useMutation({
    mutationFn: (id: number) => adminAPI.updateBrandRequest(id, { status: 'approved' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brand-requests'] });
      setSelectedRequest(null);
    },
  });

  // Отклонение заявки
  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      adminAPI.updateBrandRequest(id, { status: 'rejected', rejection_reason: reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brand-requests'] });
      setSelectedRequest(null);
      setRejectionReason('');
    },
  });

  // Удаление заявки
  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminAPI.deleteBrandRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-brand-requests'] });
      setSelectedRequest(null);
    },
  });

  const handleReject = (id: number) => {
    if (!rejectionReason.trim()) {
      alert('Укажите причину отклонения');
      return;
    }
    rejectMutation.mutate({ id, reason: rejectionReason });
  };

  const handleDelete = (id: number) => {
    setDeleteRequestId(id); // Открываем модалку
  };

  const confirmDelete = () => {
    if (deleteRequestId) {
      deleteMutation.mutate(deleteRequestId);
      setDeleteRequestId(null);
    }
  };

  const getStatusBadge = (status: BrandRequestStatus) => {
    switch (status) {
      case 'pending':
        return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">Ожидает</span>;
      case 'approved':
        return <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">Одобрена</span>;
      case 'rejected':
        return <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">Отклонена</span>;
    }
  };

  const getRequestTypeIcon = (type: string) => {
    return type === 'create' ? Building2 : UserPlus;
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка заявок...</div>;
  }

  if (error) {
    return <div className="text-center py-12 text-red-400">Ошибка загрузки заявок</div>;
  }

  const requests = data?.items || [];

  return (
    <>
      <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Заявки на верификацию</h2>
          <p className="text-gray-400">Всего: {data?.total || 0}</p>
        </div>

        {/* Фильтры */}
        <div className="flex gap-2">
          {(['all', 'pending', 'approved', 'rejected'] as const).map((status) => (
            <button
              key={status}
              onClick={() => {
                setSelectedStatus(status);
                setPage(1);
              }}
              className={`
                px-4 py-2 rounded-lg transition-all text-sm
                ${selectedStatus === status
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/5 text-gray-300 hover:bg-white/10'
                }
              `}
            >
              {status === 'all' ? 'Все' : status === 'pending' ? 'Ожидают' : status === 'approved' ? 'Одобрены' : 'Отклонены'}
            </button>
          ))}
        </div>
      </div>

      {/* Список заявок */}
      {requests.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет заявок для отображения</p>
        </div>
      ) : (
        <div className="space-y-4">
          {requests.map((request) => {
            const TypeIcon = getRequestTypeIcon(request.request_type);
            return (
              <div
                key={request.id}
                className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all cursor-pointer"
                onClick={() => setSelectedRequest(request)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-2">
                      <TypeIcon className="w-5 h-5 text-purple-400" />
                      <h3 className="text-lg font-semibold text-white">
                        {request.request_type === 'create' 
                          ? `Создать бренд: ${request.new_brand_name}` 
                          : `Присоединиться к бренду: ${request.brand_name || `#${request.brand_id}`}`}
                      </h3>
                      {getStatusBadge(request.status)}
                    </div>
                    <div className="text-sm text-gray-400 space-y-1">
                      <p>{request.user_email ? `Пользователь: ${request.user_email}` : `Пользователь ID: ${request.user_id}`}</p>
                      <p>Создана: {new Date(request.created_at).toLocaleString('ru-RU')}</p>
                      {request.processed_at && (
                        <p>Обработана: {new Date(request.processed_at).toLocaleString('ru-RU')}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    {request.status === 'pending' && (
                      <div className="flex items-center space-x-2">
                        <Clock className="w-5 h-5 text-yellow-400" />
                        <span className="text-sm text-yellow-400">Требует внимания</span>
                      </div>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(request.id);
                      }}
                      disabled={deleteMutation.isPending}
                      className="p-2 text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-50"
                      title="Удалить заявку"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Пагинация */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Назад
          </button>
          <span className="text-gray-400">Страница {page} из {data.pages}</span>
          <button
            onClick={() => setPage(p => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Вперед
          </button>
        </div>
      )}
      </div>

      {/* Модальное окно с деталями заявки */}
      {selectedRequest && createPortal(
        <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm z-50 overflow-y-auto ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
          <div className="min-h-full flex items-center justify-center p-4">
            <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-3xl w-full max-h-[90vh] my-8 overflow-hidden flex flex-col border border-white/20">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-2xl font-bold text-white">Детали заявки #{selectedRequest.id}</h3>
              <button
                onClick={() => setSelectedRequest(null)}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* Информация о заявке */}
              <div className="space-y-4 mb-6">
              {/* Кто и когда создал */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-gray-400 text-sm mb-1">Пользователь</p>
                  <p className="text-white">
                    {selectedRequest.user_email || `ID: ${selectedRequest.user_id}`}
                  </p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm mb-1">Статус</p>
                  {getStatusBadge(selectedRequest.status)}
                </div>
              </div>
              
              <div className="text-sm text-gray-400">
                <p>Создана: {new Date(selectedRequest.created_at).toLocaleString('ru-RU')}</p>
                {selectedRequest.processed_at && (
                  <p>Обработана: {new Date(selectedRequest.processed_at).toLocaleString('ru-RU')}</p>
                )}
              </div>

              {selectedRequest.request_type === 'create' && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Название бренда</p>
                      <p className="text-white font-semibold">{selectedRequest.new_brand_name}</p>
                    </div>
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Slug</p>
                      <p className="text-white">{selectedRequest.new_brand_slug}</p>
                    </div>
                  </div>
                  {selectedRequest.new_brand_description && (
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Описание</p>
                      <p className="text-white">{selectedRequest.new_brand_description}</p>
                    </div>
                  )}
                </>
              )}

              {selectedRequest.request_type === 'join' && selectedRequest.brand_id && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Присоединение к бренду</p>
                  <p className="text-white font-semibold">
                    {selectedRequest.brand_name || `Бренд #${selectedRequest.brand_id}`}
                  </p>
                  {selectedRequest.brand_id && (
                    <a
                      href={`/brands/${selectedRequest.brand_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-purple-400 hover:text-purple-300 underline text-sm mt-1 inline-block"
                    >
                      Открыть страницу бренда →
                    </a>
                  )}
                </div>
              )}

              {selectedRequest.message && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Сообщение</p>
                  <p className="text-white bg-white/5 rounded-lg p-3">{selectedRequest.message}</p>
                </div>
              )}

              {/* Email и сайт в одну строку */}
              {(selectedRequest.company_email || selectedRequest.company_website) && (
                <div className="grid grid-cols-2 gap-4">
                  {selectedRequest.company_email && (
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Email компании</p>
                      <p className="text-white">{selectedRequest.company_email}</p>
                    </div>
                  )}
                  {selectedRequest.company_website && (
                    <div>
                      <p className="text-gray-400 text-sm mb-1">Сайт компании</p>
                      {(() => {
                        // Добавляем протокол, если его нет
                        const websiteUrl = selectedRequest.company_website.startsWith('http://') || selectedRequest.company_website.startsWith('https://')
                          ? selectedRequest.company_website
                          : `https://${selectedRequest.company_website}`;
                        
                        return (
                          <a
                            href={websiteUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-purple-400 hover:text-purple-300 underline"
                          >
                            {selectedRequest.company_website}
                          </a>
                        );
                      })()}
                    </div>
                  )}
                </div>
              )}

              {/* Социальные сети */}
              {selectedRequest.social_media_urls && selectedRequest.social_media_urls.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">Социальные сети</p>
                  <div className="flex flex-wrap gap-2">
                    {selectedRequest.social_media_urls.map((url, index) => {
                      // Добавляем протокол, если его нет
                      const fullUrl = url.startsWith('http://') || url.startsWith('https://') 
                        ? url 
                        : `https://${url}`;
                      
                      return (
                        <a
                          key={index}
                          href={fullUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1 bg-white/10 rounded-lg border border-white/20 text-purple-400 hover:text-purple-300 hover:bg-white/15 transition-all text-sm"
                        >
                          {url}
                        </a>
                      );
                    })}
                  </div>
                </div>
              )}

              {selectedRequest.proof_text && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Описание подтверждающих документов</p>
                  <p className="text-white bg-white/5 rounded-lg p-3">{selectedRequest.proof_text}</p>
                </div>
              )}

              {selectedRequest.proof_files && selectedRequest.proof_files.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">Прикрепленные файлы</p>
                  <div className="space-y-3">
                    {selectedRequest.proof_files.map((fileInfo, idx) => {
                      // Поддержка старого формата (строка) и нового (объект)
                      let filePath: string;
                      let fileName: string;
                      
                      if (typeof fileInfo === 'string') {
                        // Старый формат: строка с путем
                        filePath = fileInfo;
                        fileName = fileInfo.split('/').pop() || `Файл ${idx + 1}`;
                      } else {
                        // Новый формат: объект с path и name
                        filePath = fileInfo.path;
                        fileName = fileInfo.name || fileInfo.path.split('/').pop() || `Файл ${idx + 1}`;
                      }
                      
                      const fileUrl = `/uploads/${filePath}`;
                      const fileExt = fileName.split('.').pop()?.toLowerCase() || '';
                      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(fileExt);
                      
                      return (
                        <div key={idx} className="bg-white/5 rounded-lg p-3 border border-white/10">
                          {isImage ? (
                            <div className="space-y-2">
                              <a
                                href={fileUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="block cursor-pointer"
                                onClick={(e) => {
                                  e.preventDefault();
                                  window.open(fileUrl, '_blank');
                                }}
                              >
                                <img
                                  src={fileUrl}
                                  alt={fileName}
                                  className="max-w-full h-auto max-h-64 rounded-lg border border-white/20 hover:border-purple-400/50 transition-colors"
                                  onError={(e) => {
                                    console.error('Failed to load image:', fileUrl, e);
                                    // Если изображение не загрузилось, показываем fallback
                                    const target = e.target as HTMLImageElement;
                                    const parent = target.parentElement;
                                    if (parent) {
                                      target.style.display = 'none';
                                      parent.innerHTML = `
                                        <div class="flex items-center justify-center h-32 bg-white/5 rounded-lg border border-white/20">
                                          <span class="text-gray-400 text-sm">Изображение не загружено</span>
                                        </div>
                                      `;
                                    }
                                  }}
                                />
                              </a>
                              <div className="flex items-center justify-between">
                                <span className="text-gray-300 text-sm truncate flex-1 mr-2" title={fileName}>
                                  {fileName}
                                </span>
                                <a
                                  href={fileUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center space-x-2 text-purple-400 hover:text-purple-300 text-sm flex-shrink-0"
                                  download
                                >
                                  <Download className="w-4 h-4" />
                                  <span className="hidden sm:inline">Скачать</span>
                                </a>
                              </div>
                            </div>
                          ) : (
                            <a
                              href={fileUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center space-x-2 text-purple-400 hover:text-purple-300"
                            >
                              <Download className="w-4 h-4" />
                              <span>{fileName}</span>
                            </a>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {selectedRequest.rejection_reason && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">Причина отклонения</p>
                  <p className="text-red-400 bg-red-500/10 rounded-lg p-3">{selectedRequest.rejection_reason}</p>
                </div>
              )}
              </div>
            </div>

            {/* Действия для pending заявок */}
            {selectedRequest.status === 'pending' && (
              <div className="p-6 border-t border-white/10">
                <div className="flex items-start gap-4">
                  <textarea
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder="Укажите причину отклонения заявки..."
                    className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none h-[108px]"
                  />

                  <div className="flex flex-col space-y-3 flex-shrink-0">
                    <button
                      onClick={() => {
                        approveMutation.mutate(selectedRequest.id);
                      }}
                      disabled={approveMutation.isPending}
                      className="flex items-center space-x-2 px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded-xl transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-5 h-5" />
                      <span>Одобрить</span>
                    </button>
                    <button
                      onClick={() => handleReject(selectedRequest.id)}
                      disabled={rejectMutation.isPending || !rejectionReason.trim()}
                      className="flex items-center space-x-2 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-5 h-5" />
                      <span>Отклонить</span>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>,
      document.body
      )}

      {/* Модалка подтверждения удаления */}
      <ConfirmDeleteModal
        isOpen={deleteRequestId !== null}
        onClose={() => setDeleteRequestId(null)}
        onConfirm={confirmDelete}
        title="Удалить заявку?"
        message="Все связанные файлы будут также удалены. Это действие нельзя отменить."
        isLoading={deleteMutation.isPending}
        itemName={deleteRequestId ? data?.items.find(r => r.id === deleteRequestId)?.new_brand_name || `Заявка #${deleteRequestId}` : undefined}
      />
    </>
  );
}

