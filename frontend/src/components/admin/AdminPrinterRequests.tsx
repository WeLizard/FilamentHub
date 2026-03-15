/** Компонент для управления заявками на добавление принтеров */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Package, CheckCircle, XCircle, Eye, Clock, Download } from 'lucide-react';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import { adminAPI } from '../../api/client';
import type { PrinterRequest } from '../../types/api';
import { ModalOverlay } from '../ModalOverlay';

type PrinterRequestStatus = 'pending' | 'approved' | 'rejected';

export function AdminPrinterRequests() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedStatus, setSelectedStatus] = useState<PrinterRequestStatus | 'all'>('all');
  const [selectedRequest, setSelectedRequest] = useState<PrinterRequest | null>(null);
  const [page, setPage] = useState(1);
  const [rejectionReason, setRejectionReason] = useState('');

  // Загрузка заявок
  const { data, isLoading, error, isError } = useQuery({
    queryKey: ['admin-printer-requests', selectedStatus, page],
    queryFn: () => adminAPI.listPrinterRequests({
      page,
      size: 20,
      status: selectedStatus === 'all' ? undefined : selectedStatus,
    }),
    retry: 1,
    retryOnMount: false,
  });

  // Одобрение заявки
  const approveMutation = useMutation({
    mutationFn: (id: number) => adminAPI.updatePrinterRequest(id, { status: 'approved' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-printer-requests'] });
      setSelectedRequest(null);
    },
  });

  // Отклонение заявки
  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      adminAPI.updatePrinterRequest(id, { status: 'rejected', rejection_reason: reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-printer-requests'] });
      setSelectedRequest(null);
      setRejectionReason('');
    },
  });

  const handleReject = (id: number) => {
    if (!rejectionReason.trim()) {
      alert(t('adminPrinterRequests.specifyRejectionReason'));
      return;
    }
    rejectMutation.mutate({ id, reason: rejectionReason });
  };

  const getStatusBadge = (status: PrinterRequestStatus) => {
    switch (status) {
      case 'pending':
        return <span className="px-2 py-1 rounded bg-yellow-500/20 text-yellow-400 text-xs font-semibold">{t('adminPrinterRequests.statusPending')}</span>;
      case 'approved':
        return <span className="px-2 py-1 rounded bg-green-500/20 text-green-400 text-xs font-semibold">{t('adminPrinterRequests.statusApproved')}</span>;
      case 'rejected':
        return <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">{t('adminPrinterRequests.statusRejected')}</span>;
    }
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminPrinterRequests.loading')}</div>;
  }

  // Если есть реальная ошибка (не просто пустой список)
  if (isError && error) {
    const errorMessage = error instanceof Error 
      ? error.message
      : t('adminPrinterRequests.unknownError');
    
    // Проверяем, не является ли это просто отсутствием данных (404 может быть нормальным)
    const isNotFound = errorMessage.includes('404') || errorMessage.includes('not found');
    
    if (!isNotFound) {
      return (
        <div className="text-center py-12">
          <div className="text-red-400 mb-2">{t('adminPrinterRequests.loadError')}</div>
          <div className="text-gray-400 text-sm">{errorMessage}</div>
        </div>
      );
    }
  }

  const requests = data?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">{t('adminPrinterRequests.title')}</h2>
          <p className="text-gray-400">{t('adminPrinterRequests.total')}: {data?.total || 0}</p>
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
              {status === 'all' ? t('adminPrinterRequests.filterAll') : status === 'pending' ? t('adminPrinterRequests.filterPending') : status === 'approved' ? t('adminPrinterRequests.filterApproved') : t('adminPrinterRequests.filterRejected')}
            </button>
          ))}
        </div>
      </div>

      {/* Список заявок */}
      {requests.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Package className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminPrinterRequests.noRequests')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {requests.map((request) => (
            <div
              key={request.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all cursor-pointer"
              onClick={() => setSelectedRequest(request)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Printer3DIcon className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{request.name}</h3>
                    <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-xs font-semibold">
                      {request.manufacturer} {request.model}
                    </span>
                    {getStatusBadge(request.status)}
                  </div>
                  <div className="text-sm text-gray-400 space-y-1">
                    <p>{request.user_email ? `${t('adminPrinterRequests.user')}: ${request.user_email}` : `${t('adminPrinterRequests.userId')}: ${request.user_id}`}</p>
                    <p>Slug: {request.slug}</p>
                    <p>{t('adminPrinterRequests.created')}: {new Date(request.created_at).toLocaleString('ru-RU')}</p>
                    {request.processed_at && (
                      <p>{t('adminPrinterRequests.processed')}: {new Date(request.processed_at).toLocaleString('ru-RU')}</p>
                    )}
                  </div>
                </div>
                {request.status === 'pending' && (
                  <div className="flex items-center space-x-2">
                    <Clock className="w-5 h-5 text-yellow-400" />
                    <span className="text-sm text-yellow-400">{t('adminPrinterRequests.needsAttention')}</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Пагинация */}
      {data && data.total > 20 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminPrinterRequests.prev')}
          </button>
          <span className="text-gray-400">{t('adminPrinterRequests.page')} {page}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={requests.length < 20}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminPrinterRequests.next')}
          </button>
        </div>
      )}

      {/* Модальное окно с деталями заявки */}
      {selectedRequest && (
        <ModalOverlay onClose={() => setSelectedRequest(null)}>
          <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-white/20" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <h3 className="text-2xl font-bold text-white">{t('adminPrinterRequests.requestDetails')} #{selectedRequest.id}</h3>
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
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.printerName')}</p>
                  <p className="text-white font-semibold">{selectedRequest.name}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.status')}</p>
                  {getStatusBadge(selectedRequest.status)}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.manufacturer')}</p>
                  <p className="text-white">{selectedRequest.manufacturer}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.model')}</p>
                  <p className="text-white">{selectedRequest.model}</p>
                </div>
              </div>

              <div>
                <p className="text-gray-400 text-sm mb-1">Slug</p>
                <p className="text-white">{selectedRequest.slug}</p>
              </div>

              {selectedRequest.description && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.description')}</p>
                  <p className="text-white bg-white/5 rounded-lg p-3">{selectedRequest.description}</p>
                </div>
              )}

              {(selectedRequest.build_volume_x || selectedRequest.build_volume_y || selectedRequest.build_volume_z) && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.buildVolume')}</p>
                  <p className="text-white">
                    {selectedRequest.build_volume_x || '?'} × {selectedRequest.build_volume_y || '?'} × {selectedRequest.build_volume_z || '?'} {t('adminPrinterRequests.mm')}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-3 gap-4">
                {selectedRequest.nozzle_diameter && (
                  <div>
                    <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.nozzleDiameter')}</p>
                    <p className="text-white">{selectedRequest.nozzle_diameter}{t('adminPrinters.units.mm')}</p>
                  </div>
                )}
                {selectedRequest.max_extruder_temp && (
                  <div>
                    <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.maxNozzleTemp')}</p>
                    <p className="text-white">{selectedRequest.max_extruder_temp}°C</p>
                  </div>
                )}
                {selectedRequest.max_bed_temp && (
                  <div>
                    <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.maxBedTemp')}</p>
                    <p className="text-white">{selectedRequest.max_bed_temp}°C</p>
                  </div>
                )}
              </div>

              {selectedRequest.message && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.additionalInfo')}</p>
                  <p className="text-white bg-white/5 rounded-lg p-3">{selectedRequest.message}</p>
                </div>
              )}

              {selectedRequest.proof_files && selectedRequest.proof_files.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">{t('adminPrinterRequests.attachedFiles')}</p>
                  <div className="space-y-3">
                    {selectedRequest.proof_files.map((file: string, idx: number) => {
                      const accessToken = localStorage.getItem('access_token');
                      const fileUrl = `/api/v1/uploads/${file}${accessToken ? `?token=${accessToken}` : ''}`;
                      const fileName = file.split('/').pop() || `${t('adminPrinterRequests.file')} ${idx + 1}`;
                      const fileExt = fileName.split('.').pop()?.toLowerCase() || '';
                      const isImage = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(fileExt);
                      
                      return (
                        <div key={idx} className="bg-white/5 rounded-lg p-3 border border-white/10">
                          {isImage ? (
                            <div className="space-y-2">
                              <img
                                src={fileUrl}
                                alt={fileName}
                                className="max-w-full h-auto max-h-64 rounded-lg border border-white/20"
                                onError={(e) => {
                                  const target = e.target as HTMLImageElement;
                                  target.style.display = 'none';
                                  const fallback = document.createElement('div');
                                  fallback.className = 'flex items-center justify-center h-32 bg-white/5 rounded-lg border border-white/20';
                                  const span = document.createElement('span');
                                  span.className = 'text-gray-400 text-sm';
                                  span.textContent = t('adminPrinterRequests.imageNotLoaded');
                                  fallback.appendChild(span);
                                  target.parentElement?.appendChild(fallback);
                                }}
                              />
                              <a
                                href={fileUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center space-x-2 text-purple-400 hover:text-purple-300 text-sm"
                              >
                                <Download className="w-4 h-4" />
                                <span>{fileName}</span>
                              </a>
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

              <div className="text-sm text-gray-400 space-y-1">
                <p>{selectedRequest.user_email ? `${t('adminPrinterRequests.user')}: ${selectedRequest.user_email}` : `${t('adminPrinterRequests.userId')}: ${selectedRequest.user_id}`}</p>
                <p>{t('adminPrinterRequests.created')}: {new Date(selectedRequest.created_at).toLocaleString('ru-RU')}</p>
                {selectedRequest.processed_at && (
                  <p>{t('adminPrinterRequests.processed')}: {new Date(selectedRequest.processed_at).toLocaleString('ru-RU')}</p>
                )}
              </div>

              {selectedRequest.rejection_reason && (
                <div>
                  <p className="text-gray-400 text-sm mb-1">{t('adminPrinterRequests.rejectionReason')}</p>
                  <p className="text-red-400 bg-red-500/10 rounded-lg p-3">{selectedRequest.rejection_reason}</p>
                </div>
              )}
            </div>

            {/* Действия для pending заявок */}
            {selectedRequest.status === 'pending' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-gray-300 mb-2">{t('adminPrinterRequests.rejectionReasonLabel')}</label>
                  <textarea
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder={t('adminPrinterRequests.rejectionPlaceholder')}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                    rows={3}
                  />
                </div>

                <div className="flex items-center justify-end space-x-3">
                  <button
                    onClick={() => {
                      if (confirm(t('adminPrinterRequests.confirmApprove'))) {
                        approveMutation.mutate(selectedRequest.id);
                      }
                    }}
                    disabled={approveMutation.isPending}
                    className="flex items-center space-x-2 px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded-xl transition-all disabled:opacity-50"
                  >
                    <CheckCircle className="w-5 h-5" />
                    <span>{t('adminPrinterRequests.approve')}</span>
                  </button>
                  <button
                    onClick={() => handleReject(selectedRequest.id)}
                    disabled={rejectMutation.isPending || !rejectionReason.trim()}
                    className="flex items-center space-x-2 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50"
                  >
                    <XCircle className="w-5 h-5" />
                    <span>{t('adminPrinterRequests.reject')}</span>
                  </button>
                </div>
              </div>
            )}
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
}

