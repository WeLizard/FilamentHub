/** Sync Wiki articles from backend/wiki_content/*.md into the database.
 *  Extracted from the former AdminDatabase tab (a safe content operation, not a
 *  raw-DB tool). */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation } from '@tanstack/react-query';
import {
  FileText,
  Loader,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { adminAPI } from '../../api/client';

export function AdminWikiSync() {
  const { t } = useTranslation();
  const [syncResult, setSyncResult] = useState<{
    success: boolean;
    message: string;
    created: number;
    updated: number;
    skipped: number;
    errors: number;
    details: Array<{ file: string; status: string; title?: string; slug?: string; reason?: string }>;
  } | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const syncMutation = useMutation({
    mutationFn: () => adminAPI.syncWiki(),
    onSuccess: (data) => {
      setSyncResult(data);
    },
  });

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-white flex items-center space-x-2">
          <FileText className="w-5 h-5" />
          <span>{t('adminDatabase.wikiSync.title')}</span>
        </h3>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors flex items-center space-x-2 disabled:opacity-50"
        >
          {syncMutation.isPending ? (
            <Loader className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          <span>{t('adminDatabase.wikiSync.syncButton')}</span>
        </button>
      </div>

      <p className="text-gray-400 text-sm mb-4">
        {t('adminDatabase.wikiSync.description')} <code className="bg-white/10 px-1.5 py-0.5 rounded">backend/wiki_content/*.md</code>
      </p>

      {syncMutation.isPending && (
        <div className="flex items-center space-x-2 text-gray-400">
          <Loader className="w-4 h-4 animate-spin" />
          <span>{t('adminDatabase.wikiSync.syncing')}</span>
        </div>
      )}

      {syncResult && (
        <div className={`mt-3 p-4 rounded-lg border ${syncResult.success ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
          <div className="flex items-start space-x-3">
            {syncResult.success ? (
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <p className={`${syncResult.success ? 'text-green-400' : 'text-red-400'} font-semibold`}>
                {syncResult.message}
              </p>
              <div className="mt-2 flex flex-wrap gap-3 text-sm">
                <span className="text-green-300">{t('adminDatabase.wikiSync.created', { count: syncResult.created })}</span>
                <span className="text-blue-300">{t('adminDatabase.wikiSync.updated', { count: syncResult.updated })}</span>
                {syncResult.skipped > 0 && <span className="text-yellow-300">{t('adminDatabase.wikiSync.skipped', { count: syncResult.skipped })}</span>}
                {syncResult.errors > 0 && <span className="text-red-300">{t('adminDatabase.wikiSync.errors', { count: syncResult.errors })}</span>}
              </div>
              {syncResult.details && syncResult.details.length > 0 && (
                <button
                  onClick={() => setShowDetails(!showDetails)}
                  className="mt-2 text-gray-400 hover:text-white text-sm flex items-center space-x-1"
                >
                  {showDetails ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  <span>{showDetails ? t('adminDatabase.wikiSync.hideDetails') : t('adminDatabase.wikiSync.showDetails')}</span>
                </button>
              )}
              {showDetails && syncResult.details && (
                <div className="mt-2 space-y-1 text-sm max-h-48 overflow-y-auto">
                  {syncResult.details.map((item, idx) => (
                    <div key={idx} className="flex items-center space-x-2">
                      {item.status === 'created' && <span className="text-green-400">✓</span>}
                      {item.status === 'updated' && <span className="text-blue-400">↻</span>}
                      {item.status === 'skipped' && <span className="text-yellow-400">○</span>}
                      {item.status === 'error' && <span className="text-red-400">✗</span>}
                      <span className="text-gray-300">{item.file}</span>
                      {item.title && <span className="text-gray-500">— {item.title}</span>}
                      {item.reason && <span className="text-gray-500 italic">({item.reason})</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {syncMutation.isError && (
        <div className="mt-3 p-4 rounded-lg border bg-red-500/10 border-red-500/30">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-red-400">
              {t('adminDatabase.wikiSync.error', { message: syncMutation.error?.message || t('adminDatabase.errorUnknown') })}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
