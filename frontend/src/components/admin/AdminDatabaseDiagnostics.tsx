/** Read-only database diagnostics: migration history, integrity, table sizes.
 *  No schema changes, no data editing, no import/export — those are done on the
 *  server via CLI/ops, not through the web admin. */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { GitBranch, ShieldCheck, ShieldAlert, HardDrive } from 'lucide-react';
import { adminAPI } from '../../api/client';
import { AdminWikiSync } from './AdminWikiSync';
import { AdminCatalogSources } from './AdminCatalogSources';

type DbSubTab = 'diagnostics' | 'wiki' | 'catalog';

export function AdminDatabaseDiagnostics() {
  const { t } = useTranslation();
  const [subTab, setSubTab] = useState<DbSubTab>('diagnostics');

  const { data: migrations, isLoading: migLoading } = useQuery({
    queryKey: ['admin-migrations'],
    queryFn: () => adminAPI.getMigrationHistory(),
  });
  const { data: integrity } = useQuery({
    queryKey: ['admin-db-integrity'],
    queryFn: () => adminAPI.checkDatabaseIntegrity(),
  });
  const { data: stats } = useQuery({
    queryKey: ['admin-db-stats'],
    queryFn: () => adminAPI.getDatabaseStats(),
  });

  const tabs: { id: DbSubTab; labelKey: string }[] = [
    { id: 'diagnostics', labelKey: 'adminDatabase.diag.tab' },
    { id: 'wiki', labelKey: 'adminDatabase.tabs.wiki' },
    { id: 'catalog', labelKey: 'adminDatabase.tabs.catalog' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex gap-2 flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setSubTab(tab.id)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              subTab === tab.id ? 'bg-purple-600 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'
            }`}
          >
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {subTab === 'wiki' && <AdminWikiSync />}
      {subTab === 'catalog' && <AdminCatalogSources />}

      {subTab === 'diagnostics' && (
      <>
      <p className="text-sm text-gray-400">{t('adminDatabase.diag.note')}</p>

      {/* Migrations */}
      <section className="bg-white/5 border border-white/10 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <GitBranch className="w-5 h-5 text-purple-300" />
          <h3 className="text-base font-semibold text-white">{t('adminDatabase.diag.migrations')}</h3>
        </div>
        {migLoading ? (
          <p className="text-sm text-gray-400">{t('adminDatabase.diag.loading')}</p>
        ) : (
          <>
            <p className="text-xs text-gray-400 mb-2">
              {t('adminDatabase.diag.current')}:{' '}
              <span className="text-gray-200 font-mono">{migrations?.current_revision ?? '—'}</span>
            </p>
            <div className="max-h-72 overflow-y-auto space-y-1">
              {(migrations?.migrations ?? []).map((m) => (
                <div
                  key={m.revision}
                  className="flex items-center gap-2 text-xs px-2 py-1.5 rounded bg-white/5"
                >
                  <span className="font-mono text-gray-300 flex-shrink-0">{m.revision}</span>
                  <span className="flex-1 text-gray-400 truncate">{m.description ?? ''}</span>
                  {m.is_head && (
                    <span className="px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-200 border border-blue-400/25">
                      head
                    </span>
                  )}
                  <span
                    className={`px-1.5 py-0.5 rounded-full border ${
                      m.is_applied
                        ? 'bg-emerald-500/15 text-emerald-200 border-emerald-400/25'
                        : 'bg-white/10 text-gray-400 border-white/20'
                    }`}
                  >
                    {m.is_applied ? t('adminDatabase.diag.applied') : t('adminDatabase.diag.pending')}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      {/* Integrity */}
      <section className="bg-white/5 border border-white/10 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          {integrity?.is_valid ? (
            <ShieldCheck className="w-5 h-5 text-emerald-300" />
          ) : (
            <ShieldAlert className="w-5 h-5 text-amber-300" />
          )}
          <h3 className="text-base font-semibold text-white">{t('adminDatabase.diag.integrity')}</h3>
        </div>
        {integrity ? (
          integrity.is_valid ? (
            <p className="text-sm text-emerald-300/90">{t('adminDatabase.diag.integrityOk')}</p>
          ) : (
            <div className="text-sm text-amber-300/90">
              <p>{t('adminDatabase.diag.integrityBad')}</p>
              {integrity.missing_tables.length > 0 && (
                <p className="mt-1 text-xs text-gray-300">
                  {t('adminDatabase.diag.missingTables')}: {integrity.missing_tables.join(', ')}
                </p>
              )}
            </div>
          )
        ) : (
          <p className="text-sm text-gray-400">{t('adminDatabase.diag.loading')}</p>
        )}
      </section>

      {/* Sizes */}
      <section className="bg-white/5 border border-white/10 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <HardDrive className="w-5 h-5 text-purple-300" />
          <h3 className="text-base font-semibold text-white">{t('adminDatabase.diag.stats')}</h3>
        </div>
        {stats ? (
          <>
            <p className="text-xs text-gray-400 mb-2">
              {stats.database_name} · {stats.database_size}
            </p>
            <div className="max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="text-gray-500">
                  <tr className="text-left">
                    <th className="py-1 pr-2">{t('adminDatabase.diag.table')}</th>
                    <th className="py-1 pr-2 text-right">{t('adminDatabase.diag.rows')}</th>
                    <th className="py-1 text-right">{t('adminDatabase.diag.size')}</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.table_stats.map((row) => (
                    <tr key={`${row.schema}.${row.table}`} className="border-t border-white/5">
                      <td className="py-1 pr-2 text-gray-300 font-mono">{row.table}</td>
                      <td className="py-1 pr-2 text-right text-gray-400">
                        {row.row_count.toLocaleString()}
                      </td>
                      <td className="py-1 text-right text-gray-400">{row.size}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-sm text-gray-400">{t('adminDatabase.diag.loading')}</p>
        )}
      </section>
      </>
      )}
    </div>
  );
}
