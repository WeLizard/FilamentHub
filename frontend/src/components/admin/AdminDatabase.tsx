/** Компонент для управления базой данных и миграциями */

import { useState, useMemo } from 'react';
import { ModalOverlay } from '../ModalOverlay';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Database, 
  Download, 
  Upload, 
  ArrowUp, 
  ArrowDown, 
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Loader,
  Search,
  ChevronRight,
  ChevronDown,
  Info,
  FileText,
  Clock,
  TrendingUp,
  TrendingDown,
  XCircle,
  Play,
  RotateCcw,
  X,
  Eye,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  Edit,
  Save,
  Trash2
} from 'lucide-react';
import { adminAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import { useTranslation } from 'react-i18next';

interface MigrationInfo {
  revision: string;
  down_revision: string | null;
  branch_labels: string | null;
  is_head: boolean;
  is_applied: boolean;
  applied_at: string | null;
  description: string | null;
}

interface TableInfo {
  table: string;
  schema: string;
  row_count: number;
  size: string;
  size_bytes: number;
}

const JSON_COLUMN_TYPES = new Set(['json', 'jsonb']);

function stringifyForAdminCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function IntegrityCheck() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: integrity, isLoading, refetch } = useQuery({
    queryKey: ['admin-db-integrity'],
    queryFn: () => adminAPI.checkDatabaseIntegrity(),
    refetchOnWindowFocus: false,
    enabled: false, // Загружается только по запросу
  });

  const recreateTablesMutation = useMutation({
    mutationFn: () => adminAPI.recreateTables(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-db-integrity'] });
      queryClient.invalidateQueries({ queryKey: ['admin-db-stats'] });
    },
  });

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-white flex items-center space-x-2">
          <CheckCircle className="w-5 h-5" />
          <span>{t('adminDatabase.integrityCheck.title')}</span>
        </h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors flex items-center space-x-2 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            <span>{t('adminDatabase.integrityCheck.checkButton')}</span>
          </button>
          {integrity && !integrity.is_valid && integrity.missing_tables.length > 0 && (
            <button
              onClick={() => recreateTablesMutation.mutate()}
              disabled={recreateTablesMutation.isPending}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors flex items-center space-x-2 disabled:opacity-50"
              title={t('adminDatabase.integrityCheck.restoreButtonTitle')}
            >
              {recreateTablesMutation.isPending ? (
                <Loader className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle className="w-4 h-4" />
              )}
              <span>{t('adminDatabase.integrityCheck.restoreButton')}</span>
            </button>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center space-x-2 text-gray-400">
          <Loader className="w-4 h-4 animate-spin" />
          <span>{t('adminDatabase.integrityCheck.checking')}</span>
        </div>
      )}

      {!isLoading && !integrity && (
        <div className="text-gray-400">
          {t('adminDatabase.integrityCheck.prompt')}
        </div>
      )}

      {!isLoading && integrity && (
        <div className={`p-4 rounded-lg border ${
          integrity.is_valid 
            ? 'bg-green-500/10 border-green-500/30' 
            : 'bg-red-500/10 border-red-500/30'
        }`}>
          <div className="flex items-start space-x-3">
            {integrity.is_valid ? (
              <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            ) : (
              <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <p className={`font-semibold ${
                integrity.is_valid ? 'text-green-400' : 'text-red-400'
              }`}>
                {integrity.message}
              </p>
              {integrity.missing_tables && integrity.missing_tables.length > 0 && (
                <div className="mt-2">
                  <p className="text-gray-300 text-sm mb-1">{t('adminDatabase.integrityCheck.missingTables')}</p>
                  <ul className="list-disc list-inside text-red-300 text-sm space-y-1">
                    {integrity.missing_tables.map((table) => (
                      <li key={table}>{table}</li>
                    ))}
                  </ul>
                  <div className="mt-3 p-3 bg-blue-600/10 border border-blue-500/30 rounded-lg">
                    <p className="text-blue-400 text-sm font-semibold mb-1">{t('adminDatabase.integrityCheck.howToRestore')}</p>
                    <p className="text-gray-300 text-xs">
                      {t('adminDatabase.integrityCheck.restoreSteps.intro')}
                    </p>
                    <ol className="text-gray-300 text-xs mt-1 ml-4 list-decimal space-y-1">
                      <li>{t('adminDatabase.integrityCheck.restoreSteps.step1')}</li>
                      <li>{t('adminDatabase.integrityCheck.restoreSteps.step2')}</li>
                    </ol>
                    <p className="text-gray-300 text-xs mt-2">
                      {t('adminDatabase.integrityCheck.restoreSteps.manualAlternative')}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {recreateTablesMutation.isSuccess && (
        <div className="mt-3 p-4 rounded-lg border bg-green-500/10 border-green-500/30">
          <div className="flex items-start space-x-3">
            <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-green-400 font-semibold">{recreateTablesMutation.data.message}</p>
              {recreateTablesMutation.data.created_tables && recreateTablesMutation.data.created_tables.length > 0 && (
                <div className="mt-2">
                  <p className="text-gray-300 text-sm mb-1">{t('adminDatabase.integrityCheck.createdTables')}</p>
                  <ul className="list-disc list-inside text-green-300 text-sm space-y-1">
                    {recreateTablesMutation.data.created_tables.map((table) => (
                      <li key={table}>{table}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {recreateTablesMutation.isError && (
        <div className="mt-3 p-4 rounded-lg border bg-red-500/10 border-red-500/30">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-red-400 font-semibold">
                {t('adminDatabase.integrityCheck.errorMessage', { message: recreateTablesMutation.error?.message || t('adminDatabase.errorUnknown') })}
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function WikiSync() {
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

export function AdminDatabase() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedRevision, setSelectedRevision] = useState<string>('head');
  const [exportFormat, setExportFormat] = useState<'custom' | 'plain' | 'tar'>('custom');
  const [includeData, setIncludeData] = useState(true);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importFormat, setImportFormat] = useState<'custom' | 'plain' | 'tar'>('custom');
  const [cleanImport, setCleanImport] = useState(false);
  
  // Фильтры и поиск
  const [migrationSearch, setMigrationSearch] = useState('');
  const [migrationFilter, setMigrationFilter] = useState<'all' | 'applied' | 'pending'>('all');
  const [tableSearch, setTableSearch] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'rows' | 'size'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  
  // Просмотр таблицы
  const [selectedTable, setSelectedTable] = useState<{ name: string; schema: string } | null>(null);
  const [tableDataPage, setTableDataPage] = useState(1);
  const [tableDataSize, setTableDataSize] = useState(50);
  const [tableDataSearch, setTableDataSearch] = useState('');
  const [tableDataOrderBy, setTableDataOrderBy] = useState<string | null>(null);
  const [tableDataOrderDesc, setTableDataOrderDesc] = useState(false);
  const [editingRow, setEditingRow] = useState<{ row: Record<string, any>; primaryKey: Record<string, any> } | null>(null);
  const [editFormData, setEditFormData] = useState<Record<string, any>>({});
  const [editError, setEditError] = useState<string | null>(null);

  // Загрузка истории миграций
  const { data: migrationHistory, isLoading: loadingHistory, refetch: refetchMigrations } = useQuery({
    queryKey: ['admin-migrations'],
    queryFn: () => adminAPI.getMigrationHistory(),
    refetchOnWindowFocus: false,
    staleTime: 0, // Всегда считаем данные устаревшими для миграций
  });

  // Загрузка статистики БД
  const { data: dbStats, isLoading: loadingStats, refetch: refetchStats } = useQuery({
    queryKey: ['admin-db-stats'],
    queryFn: () => adminAPI.getDatabaseStats(),
  });

  // Применение миграции
  const applyMigrationMutation = useMutation({
    mutationFn: (revision: string) => adminAPI.applyMigration({ revision }),
    onSuccess: async () => {
      // Инвалидируем все связанные запросы
      queryClient.invalidateQueries({ queryKey: ['admin-migrations'] });
      queryClient.invalidateQueries({ queryKey: ['admin-db-stats'] });
      queryClient.invalidateQueries({ queryKey: ['admin-db-integrity'] });
      // Принудительно обновляем список миграций после задержки для гарантии обновления БД
      await new Promise(resolve => setTimeout(resolve, 500));
      await refetchMigrations();
    },
  });

  // Откат миграции
  const downgradeMigrationMutation = useMutation({
    mutationFn: (revision: string) => adminAPI.downgradeMigration({ revision }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-migrations'] });
      queryClient.invalidateQueries({ queryKey: ['admin-db-stats'] });
    },
  });

  // Экспорт БД
  const exportMutation = useMutation({
    mutationFn: (data: { format: string; include_data: boolean; tables?: string[] }) =>
      adminAPI.exportDatabase(data),
  });

  // Импорт БД
  const importMutation = useMutation({
    mutationFn: (file: File) => adminAPI.importDatabase(file, importFormat, cleanImport, false), // create=false по умолчанию
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-db-stats'] });
      queryClient.invalidateQueries({ queryKey: ['admin-migrations'] });
      setImportFile(null);
    },
    onError: (error: any) => {
      console.error(t('adminDatabase.import.errorTitle'), error);
    },
  });

  // Обновление строки таблицы
  const updateTableRowMutation = useMutation({
    mutationFn: ({ tableName, primaryKey, data, schemaName }: {
      tableName: string;
      primaryKey: Record<string, any>;
      data: Record<string, any>;
      schemaName?: string;
    }) => adminAPI.updateTableData(tableName, { primary_key: primaryKey, data }, schemaName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-table-data'] });
      setEditingRow(null);
      setEditError(null);
    },
    onError: (error: any) => {
      setEditError(translateApiError(t, error?.response?.data?.detail, t('adminDatabase.tableViewer.error')));
    },
  });

  // Удаление строки таблицы
  const deleteTableRowMutation = useMutation({
    mutationFn: ({ tableName, primaryKey, schemaName }: {
      tableName: string;
      primaryKey: Record<string, any>;
      schemaName?: string;
    }) => adminAPI.deleteTableData(tableName, primaryKey, schemaName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-table-data'] });
      setEditingRow(null);
      setEditError(null);
    },
    onError: (error: any) => {
      setEditError(translateApiError(t, error?.response?.data?.detail, t('adminDatabase.tableViewer.error')));
    },
  });

  // Фильтрация и сортировка миграций
  const filteredMigrations = useMemo(() => {
    if (!migrationHistory?.migrations) return [];
    
    let filtered = [...migrationHistory.migrations];
    
    // Поиск
    if (migrationSearch) {
      const searchLower = migrationSearch.toLowerCase();
      filtered = filtered.filter((m: MigrationInfo) =>
        m.revision.toLowerCase().includes(searchLower) ||
        (m.description || '').toLowerCase().includes(searchLower)
      );
    }
    
    // Фильтр по статусу
    if (migrationFilter === 'applied') {
      // Применённые: есть is_applied ИЛИ есть applied_at
      filtered = filtered.filter((m: MigrationInfo) => m.is_applied || m.applied_at);
    } else if (migrationFilter === 'pending') {
      // Неприменённые: нет is_applied И нет applied_at И не head
      filtered = filtered.filter((m: MigrationInfo) => !m.is_applied && !m.applied_at && !m.is_head);
    }
    
    // Правильная сортировка: строим порядок от base до head
    // Создаем карту для быстрого доступа
    const migrationMap = new Map<string, any>();
    filtered.forEach((m: MigrationInfo) => migrationMap.set(m.revision, m));
    
    // Находим head миграции
    const headMigrations = filtered.filter((m: MigrationInfo) => m.is_head);
    
    // Строим порядок от head к base (обратный порядок применения)
    const ordered: MigrationInfo[] = [];
    const visited = new Set<string>();
    
    function traverse(migration: MigrationInfo) {
      if (visited.has(migration.revision)) return;
      visited.add(migration.revision);
      
      // Добавляем текущую миграцию
      ordered.push(migration);
      
      // Если есть down_revision, добавляем её перед текущей
      if (migration.down_revision) {
        const downMigration = migrationMap.get(migration.down_revision);
        if (downMigration) {
          traverse(downMigration);
        }
      }
    }
    
    // Начинаем с head миграций
    headMigrations.forEach((head: MigrationInfo) => traverse(head));
    
    // Если нет head миграций, используем все миграции и строим порядок от тех, у кого нет down_revision
    if (ordered.length === 0) {
      const baseMigrations = filtered.filter((m: MigrationInfo) => !m.down_revision);
      baseMigrations.forEach((base: MigrationInfo) => {
        let current: MigrationInfo | undefined = base;
        const chain: MigrationInfo[] = [];
        while (current && !visited.has(current.revision)) {
          visited.add(current.revision);
          chain.push(current);
          // Находим следующую миграцию, которая ссылается на текущую
          const next = filtered.find((m: MigrationInfo) => m.down_revision === current?.revision);
          current = next;
        }
        ordered.push(...chain);
      });
    }
    
    // Если всё ещё пусто, используем исходный порядок
    if (ordered.length === 0) {
      ordered.push(...filtered);
    }
    
    // Разворачиваем порядок: от base (старые) к head (новые)
    ordered.reverse();
    
    // Если есть применённые и неприменённые, сортируем: применённые сначала
    ordered.sort((a: MigrationInfo, b: MigrationInfo) => {
      // Сравниваем по статусу применения (is_applied ИЛИ applied_at)
      const aApplied = a.is_applied || a.applied_at;
      const bApplied = b.is_applied || b.applied_at;
      if (aApplied !== bApplied) {
        return aApplied ? -1 : 1;
      }
      // Если оба применены или оба не применены, сохраняем порядок
      return 0;
    });
    
    return ordered;
  }, [migrationHistory, migrationSearch, migrationFilter]);

  // Построение пути миграций (от current до head)
  const migrationPath = useMemo(() => {
    if (!migrationHistory) return [];
    
    const path: MigrationInfo[] = [];
    const migrations = migrationHistory.migrations;
    const currentRev = migrationHistory.current_revision;
    
    if (!currentRev) {
      // Нет текущей ревизии - показываем все неприменённые до head
      const headMigration = migrations.find((m: MigrationInfo) => m.is_head);
      if (headMigration) {
        let m: MigrationInfo | undefined = headMigration;
        while (m) {
          path.unshift(m);
          if (m.down_revision) {
            const nextM = migrations.find((mp: MigrationInfo) => mp.revision === m?.down_revision);
            if (!nextM) break;
            m = nextM;
          } else {
            break;
          }
        }
      }
      return path;
    }

    // Находим текущую миграцию
    let current = migrations.find((m: MigrationInfo) => m.revision === currentRev);
    if (!current) return [];

    // Находим head
    const headMigration = migrations.find((m: MigrationInfo) => m.is_head);
    if (!headMigration) return [];

    // Строим путь от current до head
    const pathMap = new Map<string, MigrationInfo>();
    migrations.forEach((m: MigrationInfo) => {
      pathMap.set(m.revision, m);
    });
    
    // Находим путь через down_revision
    const pathSet = new Set();
    let m: MigrationInfo | undefined = headMigration;
    while (m) {
      pathSet.add(m.revision);
      if (m.down_revision) {
        m = pathMap.get(m.down_revision);
      } else {
        break;
      }
    }

    // Если current в пути, показываем путь от current до head
    if (pathSet.has(currentRev)) {
      let m2: MigrationInfo | undefined = headMigration;
      while (m2 && m2.revision !== currentRev) {
        path.unshift(m2);
        if (m2.down_revision) {
          m2 = pathMap.get(m2.down_revision);
        } else {
          break;
        }
      }
    }
    
    return path;
  }, [migrationHistory]);

  // Фильтрация и сортировка таблиц БД
  const filteredTables = useMemo(() => {
    if (!dbStats?.table_stats) return [];
    
    let filtered = [...dbStats.table_stats];
    
    // Поиск
    if (tableSearch) {
      const searchLower = tableSearch.toLowerCase();
      filtered = filtered.filter((table: TableInfo) =>
        table.table.toLowerCase().includes(searchLower)
      );
    }
    
    // Сортировка
    filtered.sort((a: TableInfo, b: TableInfo) => {
      let aVal: string | number, bVal: string | number;
      
      switch (sortBy) {
        case 'rows':
          aVal = a.row_count;
          bVal = b.row_count;
          break;
        case 'size':
          aVal = a.size_bytes;
          bVal = b.size_bytes;
          break;
        default:
          aVal = a.table;
          bVal = b.table;
      }
      
      if (typeof aVal === 'string') {
        return sortOrder === 'asc'
          ? aVal.localeCompare(bVal as string)
          : (bVal as string).localeCompare(aVal);
      }

      return sortOrder === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });
    
    return filtered;
  }, [dbStats, tableSearch, sortBy, sortOrder]);

  const handleApplyMigration = (revision?: string) => {
    const rev = revision || selectedRevision;
    if (rev) {
      applyMigrationMutation.mutate(rev);
    }
  };

  const handleDowngradeMigration = (revision?: string) => {
    const rev = revision || selectedRevision;
    if (rev) {
      downgradeMigrationMutation.mutate(rev);
    }
  };

  const handleExport = () => {
    exportMutation.mutate({
      format: exportFormat,
      include_data: includeData,
    });
  };

  const handleImport = () => {
    if (importFile) {
      importMutation.mutate(importFile);
    }
  };

  const toggleSort = (column: 'name' | 'rows' | 'size') => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('asc');
    }
  };

  // Загрузка данных таблицы
  const { data: tableData, isLoading: loadingTableData } = useQuery({
    queryKey: ['admin-table-data', selectedTable?.name, selectedTable?.schema, tableDataPage, tableDataSize, tableDataSearch, tableDataOrderBy, tableDataOrderDesc],
    queryFn: () => selectedTable ? adminAPI.getTableData(selectedTable.name, {
      schema_name: selectedTable.schema,
      page: tableDataPage,
      size: tableDataSize,
      order_by: tableDataOrderBy || undefined,
      order_desc: tableDataOrderDesc,
      search: tableDataSearch || undefined,
    }) : Promise.resolve(null),
    enabled: !!selectedTable,
  });

  const { data: tableStructure } = useQuery({
    queryKey: ['admin-table-structure', selectedTable?.name, selectedTable?.schema],
    queryFn: () => selectedTable
      ? adminAPI.getTableStructure(selectedTable.name, selectedTable.schema)
      : Promise.resolve(null),
    enabled: !!selectedTable,
    staleTime: 60_000,
  });

  const columnTypeMap = useMemo(() => {
    const map = new Map<string, string>();
    tableStructure?.columns.forEach((column) => {
      map.set(column.column_name, column.data_type.toLowerCase());
    });
    return map;
  }, [tableStructure]);

  const isJsonColumn = (columnName: string): boolean => {
    const dataType = columnTypeMap.get(columnName);
    return !!dataType && JSON_COLUMN_TYPES.has(dataType);
  };

  const toEditableFieldValue = (columnName: string, value: unknown): string => {
    if (value === null || value === undefined) return '';
    if (isJsonColumn(columnName) || typeof value === 'object') {
      try {
        return JSON.stringify(value, null, 2);
      } catch {
        return String(value);
      }
    }
    return String(value);
  };

  const parseEditableFieldValue = (
    columnName: string,
    rawValue: unknown,
  ): { ok: true; value: unknown } | { ok: false; error: string } => {
    if (rawValue === null || rawValue === undefined) return { ok: true, value: null };

    if (typeof rawValue !== 'string') {
      return { ok: true, value: rawValue };
    }

    const trimmed = rawValue.trim();

    if (isJsonColumn(columnName)) {
      if (!trimmed) {
        return { ok: true, value: null };
      }
      try {
        return { ok: true, value: JSON.parse(trimmed) };
      } catch {
        return {
          ok: false,
          error: t('adminDatabase.tableViewer.invalidJsonField', { field: columnName }),
        };
      }
    }

    if (trimmed.toLowerCase() === 'true') return { ok: true, value: true };
    if (trimmed.toLowerCase() === 'false') return { ok: true, value: false };
    if (trimmed.toLowerCase() === 'null') return { ok: true, value: null };

    return { ok: true, value: rawValue };
  };

  const handleTableClick = (table: { table: string; schema: string }) => {
    setSelectedTable({ name: table.table, schema: table.schema });
    setTableDataPage(1);
    setTableDataSearch('');
    setTableDataOrderBy(null);
    setTableDataOrderDesc(false);
  };

  const handleTableDataSort = (column: string) => {
    if (tableDataOrderBy === column) {
      setTableDataOrderDesc(!tableDataOrderDesc);
    } else {
      setTableDataOrderBy(column);
      setTableDataOrderDesc(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">{t('adminDatabase.title')}</h2>
        <p className="text-gray-400">{t('adminDatabase.description')}</p>
      </div>

      {/* Проверка целостности БД */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10 mb-6">
        <IntegrityCheck />
      </div>

      {/* Синхронизация Wiki */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10 mb-6">
        <WikiSync />
      </div>

      {/* Статистика БД */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-white flex items-center space-x-2">
            <Database className="w-5 h-5" />
            <span>{t('adminDatabase.dbStats.title')}</span>
          </h3>
          <button
            onClick={() => refetchStats()}
            className="text-gray-400 hover:text-white transition-colors"
            title={t('adminDatabase.dbStats.refreshButtonTitle')}
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
        
        {loadingStats ? (
          <div className="text-center py-8 text-gray-400 flex items-center justify-center space-x-2">
            <Loader className="w-5 h-5 animate-spin" />
            <span>{t('adminDatabase.dbStats.loading')}</span>
          </div>
        ) : dbStats ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gradient-to-br from-purple-600/20 to-purple-800/20 rounded-lg p-4 border border-purple-500/30">
                <p className="text-gray-400 text-sm mb-1 flex items-center space-x-1">
                  <Database className="w-3.5 h-3.5" />
                  <span>{t('adminDatabase.dbStats.databaseName')}</span>
                </p>
                <p className="text-white font-semibold text-lg">{dbStats.database_name}</p>
              </div>
              <div className="bg-gradient-to-br from-blue-600/20 to-blue-800/20 rounded-lg p-4 border border-blue-500/30">
                <p className="text-gray-400 text-sm mb-1 flex items-center space-x-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span>{t('adminDatabase.dbStats.size')}</span>
                </p>
                <p className="text-white font-semibold text-lg">{dbStats.database_size}</p>
              </div>
              <div className="bg-gradient-to-br from-green-600/20 to-green-800/20 rounded-lg p-4 border border-green-500/30">
                <p className="text-gray-400 text-sm mb-1 flex items-center space-x-1">
                  <FileText className="w-3.5 h-3.5" />
                  <span>{t('adminDatabase.dbStats.tables')}</span>
                </p>
                <p className="text-white font-semibold text-lg">{dbStats.table_stats.length}</p>
              </div>
            </div>

            <div className="mt-6">
              <div className="flex items-center justify-between mb-3">
                <p className="text-gray-300 font-semibold">{t('adminDatabase.dbStats.tablesTitle')}</p>
                <div className="relative w-64">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                  <input
                    type="text"
                    placeholder={t('adminDatabase.dbStats.searchPlaceholder')}
                    value={tableSearch}
                    onChange={(e) => setTableSearch(e.target.value)}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 pl-10 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm"
                  />
                </div>
              </div>
              
              <div className="bg-white/5 rounded-lg overflow-hidden border border-white/10">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10 bg-white/5">
                        <th 
                          className="text-left py-3 px-4 text-gray-300 font-semibold cursor-pointer hover:text-white transition-colors"
                          onClick={() => toggleSort('name')}
                        >
                          <div className="flex items-center space-x-2">
                            <span>{t('adminDatabase.dbStats.tableHeader')}</span>
                            {sortBy === 'name' && (
                              sortOrder === 'asc' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />
                            )}
                          </div>
                        </th>
                        <th 
                          className="text-right py-3 px-4 text-gray-300 font-semibold cursor-pointer hover:text-white transition-colors"
                          onClick={() => toggleSort('rows')}
                        >
                          <div className="flex items-center justify-end space-x-2">
                            <span>{t('adminDatabase.dbStats.rowsHeader')}</span>
                            {sortBy === 'rows' && (
                              sortOrder === 'asc' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />
                            )}
                          </div>
                        </th>
                        <th 
                          className="text-right py-3 px-4 text-gray-300 font-semibold cursor-pointer hover:text-white transition-colors"
                          onClick={() => toggleSort('size')}
                        >
                          <div className="flex items-center justify-end space-x-2">
                            <span>{t('adminDatabase.dbStats.sizeHeader')}</span>
                            {sortBy === 'size' && (
                              sortOrder === 'asc' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />
                            )}
                          </div>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredTables.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="text-center py-8 text-gray-400">
                            {tableSearch ? t('adminDatabase.dbStats.noTablesFound') : t('adminDatabase.dbStats.noTables')}
                          </td>
                        </tr>
                      ) : (
                        filteredTables.map((table: TableInfo) => (
                          <tr 
                            key={table.table} 
                            onClick={() => handleTableClick(table)}
                            className="border-b border-white/5 hover:bg-white/10 transition-colors cursor-pointer"
                          >
                            <td className="py-3 px-4 text-white font-mono text-xs flex items-center space-x-2">
                              <Eye className="w-4 h-4 text-gray-400" />
                              <span>{table.table}</span>
                            </td>
                            <td className="py-3 px-4 text-right text-gray-300">
                              {table.row_count.toLocaleString()}
                            </td>
                            <td className="py-3 px-4 text-right text-gray-300">{table.size}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-red-400 flex items-center justify-center space-x-2">
            <XCircle className="w-5 h-5" />
            <span>{t('adminDatabase.dbStats.error')}</span>
          </div>
        )}
      </div>

      {/* Миграции */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-white flex items-center space-x-2">
            <RefreshCw className="w-5 h-5" />
            <span>{t('adminDatabase.migrations.title')}</span>
          </h3>
          <button
            onClick={() => refetchMigrations()}
            className="text-gray-400 hover:text-white transition-colors"
            title={t('adminDatabase.migrations.refreshButtonTitle')}
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>

        {loadingHistory ? (
          <div className="text-center py-8 text-gray-400 flex items-center justify-center space-x-2">
            <Loader className="w-5 h-5 animate-spin" />
            <span>{t('adminDatabase.migrations.loading')}</span>
          </div>
        ) : migrationHistory ? (
          <div className="space-y-6">
            {/* Текущий статус */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-gradient-to-br from-purple-600/20 to-purple-800/20 rounded-lg p-4 border border-purple-500/30">
                <p className="text-gray-400 text-sm mb-1 flex items-center space-x-1">
                  <Clock className="w-3.5 h-3.5" />
                  <span>{t('adminDatabase.migrations.currentRevision')}</span>
                </p>
                {migrationHistory.current_revision ? (
                  <>
                    <p className="text-white font-semibold text-lg font-mono mb-1">
                      {migrationHistory.current_revision}
                    </p>
                    {migrationHistory.current_revision === migrationHistory.heads[0] ? (
                      <p className="text-green-400 text-xs flex items-center space-x-1">
                        <CheckCircle className="w-3 h-3" />
                        <span>{t('adminDatabase.migrations.upToDate')}</span>
                      </p>
                    ) : (
                      <p className="text-yellow-400 text-xs flex items-center space-x-1">
                        <AlertCircle className="w-3 h-3" />
                        <span>{t('adminDatabase.migrations.pendingMigrations')}</span>
                      </p>
                    )}
                  </>
                ) : (
                  <>
                    <p className="text-yellow-400 font-semibold text-lg mb-1">
                      {t('adminDatabase.migrations.noMigrations')}
                    </p>
                    <p className="text-gray-400 text-xs">
                      {t('adminDatabase.migrations.notInitialized')}
                    </p>
                  </>
                )}
              </div>
              <div className="bg-gradient-to-br from-green-600/20 to-green-800/20 rounded-lg p-4 border border-green-500/30">
                <p className="text-gray-400 text-sm mb-1 flex items-center space-x-1">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span>{t('adminDatabase.migrations.latestRevision')}</span>
                </p>
                <p className="text-white font-semibold text-lg font-mono mb-1">
                  {migrationHistory.heads[0] || 'head'}
                </p>
                <p className="text-gray-400 text-xs">
                  {t('adminDatabase.migrations.latestDescription')}
                </p>
              </div>
            </div>

            {/* Визуализация пути миграций */}
            {migrationPath.length > 0 ? (
              <div className="bg-white/5 rounded-lg p-4 border border-white/10">
                <p className="text-gray-300 text-sm mb-3 flex items-center space-x-2">
                  <Info className="w-4 h-4" />
                  <span>
                    {migrationHistory.current_revision 
                      ? t('adminDatabase.migrations.pathFromCurrent', { current: migrationHistory.current_revision.substring(0, 8)})
                      : t('adminDatabase.migrations.pathFromStart')
                    }
                  </span>
                </p>
                <div className="flex items-center space-x-2 flex-wrap gap-2">
                  {migrationPath.map((migration: MigrationInfo, index: number) => (
                    <div key={migration.revision} className="flex items-center space-x-2">
                      {index > 0 && <ChevronRight className="w-4 h-4 text-gray-500" />}
                      <div className={`
                        px-3 py-1.5 rounded-lg text-xs font-mono border
                        ${migration.is_applied 
                          ? 'bg-green-600/20 text-green-400 border-green-500/30' 
                          : 'bg-yellow-600/20 text-yellow-400 border-yellow-500/30'
                        }
                      `}>
                        {migration.revision.substring(0, 12)}...
                      </div>
                    </div>
                  ))}
                </div>
                {migrationHistory.current_revision && migrationHistory.current_revision !== migrationHistory.heads[0] && (
                  <div className="mt-3 p-3 bg-yellow-600/10 border border-yellow-500/30 rounded-lg">
                    <p className="text-yellow-400 text-sm flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4" />
                      <span>
                        {t('adminDatabase.migrations.applyXNewMigrations', { count: migrationPath.length })}
                      </span>
                    </p>
                  </div>
                )}
              </div>
            ) : migrationHistory.current_revision ? null : (
              <div className="bg-yellow-600/10 rounded-lg p-4 border border-yellow-500/30">
                <p className="text-yellow-400 text-sm flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4" />
                  <span>{t('adminDatabase.migrations.notInitialized')}</span>
                </p>
              </div>
            )}

            {/* Быстрые действия */}
            <div className="bg-white/5 rounded-lg p-4 border border-white/10">
              <p className="text-gray-300 text-sm mb-3">{t('adminDatabase.migrations.quickActions')}</p>
              <div className="flex items-center space-x-4">
                <input
                  type="text"
                  value={selectedRevision}
                  onChange={(e) => setSelectedRevision(e.target.value)}
                  placeholder={t('adminDatabase.migrations.revisionInputPlaceholder')}
                  className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm font-mono"
                />
                <button
                  onClick={() => handleApplyMigration('head')}
                  disabled={applyMigrationMutation.isPending || migrationHistory.current_revision === migrationHistory.heads[0]}
                  className="flex items-center space-x-2 px-4 py-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                  title={t('adminDatabase.migrations.applyToHeadTitle')}
                >
                  {applyMigrationMutation.isPending ? (
                    <Loader className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4" />
                  )}
                  <span>{t('adminDatabase.migrations.applyToHeadButton')}</span>
                </button>
                <button
                  onClick={() => handleApplyMigration(selectedRevision)}
                  disabled={applyMigrationMutation.isPending || !selectedRevision}
                  className="flex items-center space-x-2 px-4 py-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {applyMigrationMutation.isPending ? (
                    <Loader className="w-4 h-4 animate-spin" />
                  ) : (
                    <ArrowUp className="w-4 h-4" />
                  )}
                  <span>{t('adminDatabase.migrations.applyButton')}</span>
                </button>
                <button
                  onClick={() => handleDowngradeMigration(selectedRevision)}
                  disabled={downgradeMigrationMutation.isPending || !selectedRevision || !migrationHistory.current_revision}
                  className="flex items-center space-x-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                >
                  {downgradeMigrationMutation.isPending ? (
                    <Loader className="w-4 h-4 animate-spin" />
                  ) : (
                    <RotateCcw className="w-4 h-4" />
                  )}
                  <span>{t('adminDatabase.migrations.downgradeButton')}</span>
                </button>
              </div>
            </div>

            {/* Фильтры и поиск миграций */}
            <div className="flex items-center space-x-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <input
                  type="text"
                  placeholder={t('adminDatabase.migrations.tableHeaderDescription')}
                  value={migrationSearch}
                  onChange={(e) => setMigrationSearch(e.target.value)}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 pl-10 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm"
                />
              </div>
              <select
                value={migrationFilter}
                onChange={(e) => setMigrationFilter(e.target.value as 'all' | 'applied' | 'pending')}
                className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500 text-sm"
              >
                <option value="all">{t('adminDatabase.migrations.filterAll')}</option>
                <option value="applied">{t('adminDatabase.migrations.filterApplied')}</option>
                <option value="pending">{t('adminDatabase.migrations.filterPending')}</option>
              </select>
            </div>

            {/* Информационная подсказка (сворачиваемая) */}
            {!applyMigrationMutation.isPending && !downgradeMigrationMutation.isPending && (
              <details className="group bg-blue-600/10 rounded-lg border border-blue-500/30">
                <summary className="p-4 text-blue-400 text-sm font-semibold flex items-center space-x-2 cursor-pointer select-none hover:text-blue-300 transition-colors list-none [&::-webkit-details-marker]:hidden">
                  <Info className="w-4 h-4 flex-shrink-0" />
                  <span>{t('adminDatabase.migrations.howToUseTitle')}</span>
                  <ChevronRight className="w-4 h-4 ml-auto transition-transform group-open:rotate-90" />
                </summary>
                <div className="px-4 pb-4">
                  <ul className="text-gray-300 text-xs space-y-1 ml-6 list-disc">
                    <li><strong>{t('adminDatabase.migrations.applyToHeadButton')}</strong> — {t('adminDatabase.migrations.howToUseHead')}</li>
                    <li>
                      <strong>{t('adminDatabase.migrations.applyButton')}</strong> — {t('adminDatabase.migrations.howToUseApply')}
                      <ul className="ml-4 mt-1 space-y-0.5 list-disc">
                        <li><code className="bg-white/5 px-1 rounded">head</code> — {t('adminDatabase.migrations.howToUseApplyHead')}</li>
                        <li><code className="bg-white/5 px-1 rounded">+1</code> — {t('adminDatabase.migrations.howToUseApplyPlusOne')}</li>
                        <li><code className="bg-white/5 px-1 rounded">a2b3c4d5e6f7</code> — {t('adminDatabase.migrations.howToUseApplyRevision')}</li>
                      </ul>
                    </li>
                    <li>
                      <strong>{t('adminDatabase.migrations.downgradeButton')}</strong> — {t('adminDatabase.migrations.howToUseDowngrade')}
                      <ul className="ml-4 mt-1 space-y-0.5 list-disc">
                        <li><code className="bg-white/5 px-1 rounded">-1</code> — {t('adminDatabase.migrations.howToUseDowngradeMinusOne')}</li>
                        <li><code className="bg-white/5 px-1 rounded">base</code> — {t('adminDatabase.migrations.howToUseDowngradeBase')}</li>
                      </ul>
                    </li>
                    <li>{t('adminDatabase.migrations.howToUseClickHint')}</li>
                  </ul>
                </div>
              </details>
            )}

            {/* Сообщения об успехе/ошибке */}
            {(applyMigrationMutation.isSuccess || downgradeMigrationMutation.isSuccess) && (
              <div className={`flex items-start space-x-2 rounded-lg p-3 border ${
                applyMigrationMutation.data?.validation_errors && applyMigrationMutation.data.validation_errors.length > 0
                  ? 'text-yellow-400 bg-yellow-600/10 border-yellow-500/30'
                  : 'text-green-400 bg-green-600/10 border-green-500/30'
              }`}>
                {applyMigrationMutation.data?.validation_errors && applyMigrationMutation.data.validation_errors.length > 0 ? (
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                ) : (
                  <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1">
                  <span className="text-sm">
                    {applyMigrationMutation.isSuccess ? t('adminDatabase.migrations.migrationSuccess') : t('adminDatabase.migrations.downgradeSuccess')}
                  </span>
                  {applyMigrationMutation.data?.validation_errors && applyMigrationMutation.data.validation_errors.length > 0 && (
                    <div className="mt-2">
                      <p className="text-yellow-300 text-xs mb-1">{t('adminDatabase.migrations.validationErrors')}</p>
                      <ul className="list-disc list-inside text-yellow-300/80 text-xs space-y-1">
                        {applyMigrationMutation.data.validation_errors.map((table) => (
                          <li key={table}>{table}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            )}

            {(applyMigrationMutation.isError || downgradeMigrationMutation.isError) && (
              <div className="flex items-center space-x-2 text-red-400 bg-red-600/10 rounded-lg p-3 border border-red-500/30">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <span className="text-sm">
                  {applyMigrationMutation.error?.message || downgradeMigrationMutation.error?.message || t('adminDatabase.migrations.migrationError')}
                </span>
              </div>
            )}

            {/* Объяснение статусов (сворачиваемое) */}
            <details className="group bg-blue-600/10 rounded-lg border border-blue-500/30">
              <summary className="p-4 text-blue-400 text-sm font-semibold flex items-center space-x-2 cursor-pointer select-none hover:text-blue-300 transition-colors list-none [&::-webkit-details-marker]:hidden">
                <Info className="w-4 h-4 flex-shrink-0" />
                <span>{t('adminDatabase.migrations.statusExplanationTitle')}</span>
                <ChevronRight className="w-4 h-4 ml-auto transition-transform group-open:rotate-90" />
              </summary>
              <div className="px-4 pb-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                  <div className="flex items-start space-x-2">
                    <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-green-400 font-semibold">✓ {t('adminDatabase.migrations.statusApplied')}</p>
                      <p className="text-gray-400">{t('adminDatabase.migrations.statusAppliedDesc')}</p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-2">
                    <Clock className="w-4 h-4 text-gray-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-gray-400 font-semibold">⏳ {t('adminDatabase.migrations.statusPending')}</p>
                      <p className="text-gray-400">{t('adminDatabase.migrations.statusPendingDesc')}</p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-2">
                    <TrendingUp className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-yellow-400 font-semibold">↑ {t('adminDatabase.migrations.statusHead')}</p>
                      <p className="text-gray-400">{t('adminDatabase.migrations.statusHeadDesc')}</p>
                    </div>
                  </div>
                </div>
                <div className="mt-3 pt-3 border-t border-blue-500/20">
                  <p className="text-gray-300 text-xs">
                    <strong className="text-purple-400">{t('adminDatabase.migrations.currentLabel')}</strong> — {t('adminDatabase.migrations.currentLabelHint')}
                  </p>
                </div>
              </div>
            </details>

            {/* Таблица миграций */}
            <div className="bg-white/5 rounded-lg overflow-hidden border border-white/10">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 bg-white/5">
                      <th className="text-left py-3 px-4 text-gray-300 font-semibold">{t('adminDatabase.migrations.tableHeaderStatus')}</th>
                      <th className="text-left py-3 px-4 text-gray-300 font-semibold">{t('adminDatabase.migrations.tableHeaderRevision')}</th>
                      <th className="text-left py-3 px-4 text-gray-300 font-semibold">{t('adminDatabase.migrations.tableHeaderDescription')}</th>
                      <th className="text-left py-3 px-4 text-gray-300 font-semibold">{t('adminDatabase.migrations.tableHeaderAppliedDate')}</th>
                      <th className="text-center py-3 px-4 text-gray-300 font-semibold">{t('adminDatabase.migrations.tableHeaderActions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMigrations.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="text-center py-8 text-gray-400">
                          {migrationSearch || migrationFilter !== 'all' ? t('adminDatabase.migrations.noMigrationsFound') : t('adminDatabase.migrations.noMigrationsExist')}
                        </td>
                      </tr>
                    ) : (
                      filteredMigrations.map((migration: MigrationInfo) => (
                        <tr 
                          key={migration.revision} 
                          className={`
                            border-b border-white/5 hover:bg-white/5 transition-colors
                            ${migration.is_applied ? 'bg-green-600/5' : ''}
                            ${migration.revision === migrationHistory.current_revision ? 'ring-2 ring-purple-500/50' : ''}
                          `}
                        >
                          <td className="py-3 px-4">
                            {/* Миграция применена, если is_applied=true ИЛИ есть applied_at */}
                            {(migration.is_applied || migration.applied_at) ? (
                              <span className="flex items-center space-x-1 text-green-400">
                                <CheckCircle className="w-4 h-4" />
                                <span className="text-xs">{t('adminDatabase.migrations.statusLabelApplied')}</span>
                              </span>
                            ) : migration.is_head ? (
                              <span className="flex items-center space-x-1 text-yellow-400">
                                <TrendingUp className="w-4 h-4" />
                                <span className="text-xs">{t('adminDatabase.migrations.statusLabelHead')}</span>
                              </span>
                            ) : (
                              <span className="flex items-center space-x-1 text-gray-500">
                                <Clock className="w-4 h-4" />
                                <span className="text-xs">{t('adminDatabase.migrations.statusLabelPending')}</span>
                              </span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center space-x-2">
                              <code className="text-white font-mono text-xs bg-white/5 px-2 py-1 rounded">
                                {migration.revision}
                              </code>
                              {migration.revision === migrationHistory.current_revision && (
                                <span className="text-xs text-purple-400 bg-purple-600/20 px-2 py-0.5 rounded">{t('adminDatabase.migrations.currentLabel')}</span>
                              )}
                            </div>
                          </td>
                          <td className="py-3 px-4 text-gray-300">
                            {migration.description || (
                              <span className="text-gray-500 italic">{t('adminDatabase.migrations.noDescription')}</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-gray-400 text-xs">
                            {migration.applied_at ? (
                              new Date(migration.applied_at).toLocaleString('ru-RU')
                            ) : (
                              <span className="text-gray-500">{t('adminDatabase.migrations.notApplied')}</span>
                            )}
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center justify-center space-x-2">
                              {/* Показываем кнопку "Применить" только если миграция НЕ применена (нет is_applied И нет applied_at) */}
                              {!migration.is_applied && !migration.applied_at ? (
                                <button
                                  onClick={() => handleApplyMigration(migration.revision)}
                                  disabled={applyMigrationMutation.isPending}
                                  className="p-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded transition-all disabled:opacity-50"
                                  title={t('adminDatabase.migrations.applyActionTitle')}
                                >
                                  {applyMigrationMutation.isPending ? (
                                    <Loader className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <ArrowUp className="w-4 h-4" />
                                  )}
                                </button>
                              ) : migration.revision !== migrationHistory.current_revision ? (
                                <button
                                  onClick={() => handleDowngradeMigration(migration.down_revision || '-1')}
                                  disabled={downgradeMigrationMutation.isPending}
                                  className="p-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded transition-all disabled:opacity-50"
                                  title={t('adminDatabase.migrations.downgradeToPreviousTitle')}
                                >
                                  {downgradeMigrationMutation.isPending ? (
                                    <Loader className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <ArrowDown className="w-4 h-4" />
                                  )}
                                </button>
                              ) : (
                                <span className="text-gray-500 text-xs">{t('adminDatabase.migrations.currentActionLabel')}</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-red-400 flex items-center justify-center space-x-2">
            <XCircle className="w-5 h-5" />
            <span>{t('adminDatabase.migrations.migrationError')}</span>
          </div>
        )}
      </div>

      {/* Экспорт */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Download className="w-5 h-5" />
          <span>{t('adminDatabase.export.title')}</span>
        </h3>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-400 text-sm mb-2">{t('adminDatabase.export.formatLabel')}</label>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as 'custom' | 'plain' | 'tar')}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500"
              >
                <option value="custom">{t('adminDatabase.export.formatCustom')}</option>
                <option value="plain">{t('adminDatabase.export.formatPlain')}</option>
                <option value="tar">{t('adminDatabase.export.formatTar')}</option>
              </select>
            </div>
            <div className="flex items-center space-x-2 mt-6">
              <input
                type="checkbox"
                id="includeData"
                checked={includeData}
                onChange={(e) => setIncludeData(e.target.checked)}
                className="w-4 h-4 text-purple-600 bg-white/5 border-white/10 rounded focus:ring-purple-500"
              />
              <label htmlFor="includeData" className="text-gray-300">
                {t('adminDatabase.export.includeDataLabel')}
              </label>
            </div>
          </div>

          <button
            onClick={handleExport}
            disabled={exportMutation.isPending}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg transition-all disabled:opacity-50"
          >
            {exportMutation.isPending ? (
              <Loader className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            <span>{t('adminDatabase.export.exportButton')}</span>
          </button>

          {exportMutation.isSuccess && exportMutation.data.download_url && exportMutation.data.filename && (
            <div className="flex items-center space-x-2 text-green-400 bg-green-600/10 rounded-lg p-3 border border-green-500/30">
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
              <div className="flex-1">
                <span className="text-sm">{exportMutation.data.message}</span>
                {exportMutation.data.size && (
                  <span className="text-xs text-gray-400 ml-2">
                    ({(exportMutation.data.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                )}
              </div>
              <button
                onClick={async () => {
                  try {
                    // Используем fetch с относительным URL, который будет проксироваться через Vite на localhost:8000
                    const token = localStorage.getItem('access_token');
                    
                    const response = await fetch(exportMutation.data.download_url!, {
                      headers: {
                        'Authorization': `Bearer ${token}`,
                      },
                    });
                    
                    if (!response.ok) {
                      const errorText = await response.text();
                      throw new Error(t('adminDatabase.export.downloadError', { message: `${response.status} ${errorText}` }));
                    }
                    
                    // Создаём blob URL и скачиваем файл
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = exportMutation.data.filename!;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                  } catch (error: any) {
                    const errorMessage = error.message || t('adminDatabase.errorUnknown');
                    alert(t('adminDatabase.export.downloadError', { message: errorMessage }));
                  }
                }}
                className="ml-auto text-blue-400 hover:text-blue-300 underline text-sm flex items-center space-x-1 transition-colors"
              >
                <Download className="w-4 h-4" />
                <span>{t('adminDatabase.export.downloadButton')}</span>
              </button>
            </div>
          )}

          {exportMutation.isError && (
            <div className="flex items-center space-x-2 text-red-400 bg-red-600/10 rounded-lg p-3 border border-red-500/30">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm">{t('adminDatabase.export.error', { message: exportMutation.error?.message })}</span>
            </div>
          )}
        </div>
      </div>

      {/* Импорт */}
      <div className="bg-white/5 rounded-xl p-6 border border-white/10">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Upload className="w-5 h-5" />
          <span>{t('adminDatabase.import.title')}</span>
        </h3>

        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-400 text-sm mb-2">{t('adminDatabase.import.formatLabel')}</label>
              <select
                value={importFormat}
                onChange={(e) => setImportFormat(e.target.value as 'custom' | 'plain' | 'tar')}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500"
              >
                <option value="custom">{t('adminDatabase.import.formatCustom')}</option>
                <option value="plain">{t('adminDatabase.import.formatPlain')}</option>
                <option value="tar">{t('adminDatabase.import.formatTar')}</option>
              </select>
            </div>
            <div className="flex items-center space-x-2 mt-6">
              <input
                type="checkbox"
                id="cleanImport"
                checked={cleanImport}
                onChange={(e) => setCleanImport(e.target.checked)}
                className="w-4 h-4 text-purple-600 bg-white/5 border-white/10 rounded focus:ring-purple-500"
              />
              <label htmlFor="cleanImport" className="text-gray-300">
                {t('adminDatabase.import.cleanImportLabel')}
              </label>
            </div>
          </div>

          <div>
            <label className="block text-gray-400 text-sm mb-2">{t('adminDatabase.import.dumpFileLabel')}</label>
            <input
              type="file"
              onChange={(e) => setImportFile(e.target.files?.[0] || null)}
              accept=".dump,.sql,.tar"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white cursor-pointer
                file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 
                file:text-sm file:font-semibold 
                file:bg-purple-600 file:text-white 
                file:hover:bg-purple-700 file:active:bg-purple-800
                file:cursor-pointer file:transition-colors
                hover:border-purple-500/50 focus:border-purple-500 focus:outline-none"
            />
            {importFile && (
              <p className="text-sm text-gray-400 mt-2 flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 text-green-400" />
                <span>{t('adminDatabase.import.fileSelected', { fileName: importFile.name })}</span>
                <span className="text-gray-500">({(importFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              </p>
            )}
          </div>

          <button
            onClick={handleImport}
            disabled={importMutation.isPending || !importFile}
            className="flex items-center space-x-2 px-4 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {importMutation.isPending ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                <span>{t('adminDatabase.import.importing')}</span>
              </>
            ) : (
              <>
                <Upload className="w-4 h-4" />
                <span>{t('adminDatabase.import.importButton')}</span>
              </>
            )}
          </button>
          
          {importMutation.isPending && (
            <div className="bg-blue-600/10 rounded-lg p-3 border border-blue-500/30">
              <div className="flex items-center space-x-2 text-blue-400">
                <Loader className="w-4 h-4 animate-spin" />
                <span className="text-sm">
                  {t('adminDatabase.import.importingDescription')}
                </span>
              </div>
            </div>
          )}

          {importMutation.isSuccess && (
            <div className="flex items-center space-x-2 text-green-400 bg-green-600/10 rounded-lg p-3 border border-green-500/30">
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm">{importMutation.data.message}</span>
            </div>
          )}

          {importMutation.isError && (
            <div className="flex items-start space-x-2 text-red-400 bg-red-600/10 rounded-lg p-3 border border-red-500/30">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold">{t('adminDatabase.import.errorTitle')}</p>
                <p className="text-xs text-red-300 mt-1">
                  {translateApiError(t, importMutation.error?.response?.data?.detail, t('adminDatabase.import.errorUnknown'))}
                </p>
                {importMutation.error?.code === 'ECONNABORTED' && (
                  <p className="text-xs text-yellow-300 mt-1">
                    {t('adminDatabase.import.errorTimeout')}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Модальное окно просмотра таблицы */}
      {selectedTable && (
        <ModalOverlay onClose={() => setSelectedTable(null)}>
          <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-7xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-white/20" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div>
                <h3 className="text-2xl font-bold text-white flex items-center space-x-2">
                  <Database className="w-6 h-6" />
                  <span>{t('adminDatabase.tableViewer.title', { schema: selectedTable.schema, name: selectedTable.name })}</span>
                </h3>
                {tableData && (
                  <p className="text-gray-400 text-sm mt-1">
                    {t('adminDatabase.tableViewer.totalRows', { count: tableData.total })}
                  </p>
                )}
              </div>
              <button
                onClick={() => setSelectedTable(null)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* Поиск и пагинация */}
              <div className="flex items-center space-x-4 mb-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                  <input
                    type="text"
                    placeholder={t('adminDatabase.tableViewer.searchPlaceholder')}
                    value={tableDataSearch}
                    onChange={(e) => {
                      setTableDataSearch(e.target.value);
                      setTableDataPage(1);
                    }}
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 pl-10 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm"
                  />
                </div>
                <select
                  value={tableDataSize}
                  onChange={(e) => {
                    setTableDataSize(Number(e.target.value));
                    setTableDataPage(1);
                  }}
                  className="bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500 text-sm"
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={200}>200</option>
                </select>
              </div>

              {/* Таблица данных */}
              {loadingTableData ? (
                <div className="flex items-center justify-center py-12 text-gray-400">
                  <Loader className="w-6 h-6 animate-spin mr-2" />
                  <span>{t('adminDatabase.tableViewer.loadingData')}</span>
                </div>
              ) : tableData ? (
                <>
                  <div className="bg-white/5 rounded-lg border border-white/10 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-white/10 border-b border-white/10">
                        <tr>
                          {tableData.columns.map((col: string) => (
                            <th
                              key={col}
                              onClick={() => handleTableDataSort(col)}
                              className="text-left py-3 px-4 text-gray-300 font-semibold cursor-pointer hover:text-white transition-colors"
                            >
                              <div className="flex items-center space-x-2">
                                <span>{col}</span>
                                {tableDataOrderBy === col && (
                                  tableDataOrderDesc ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />
                                )}
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {tableData.rows.length === 0 ? (
                          <tr>
                            <td colSpan={tableData.columns.length} className="text-center py-8 text-gray-400">
                              {tableDataSearch ? t('adminDatabase.tableViewer.noDataFound') : t('adminDatabase.tableViewer.noData')}
                            </td>
                          </tr>
                        ) : (
                          tableData.rows.map((row: Record<string, unknown>, idx: number) => {
                            // Используем реальный primary key из бэкенда
                            const pkCols: string[] = tableData.primary_key_columns?.length
                              ? tableData.primary_key_columns
                              : [tableData.columns.find((col: string) =>
                                  col.toLowerCase() === 'id'
                                ) || tableData.columns[0]];
                            const primaryKey: Record<string, any> = {};
                            pkCols.forEach((col: string) => { primaryKey[col] = row[col]; });
                            
                            return (
                              <tr 
                                key={idx} 
                                className="border-b border-white/5 hover:bg-white/10 transition-colors cursor-pointer"
                                onClick={() => {
                                  setEditingRow({ row, primaryKey });
                                  const normalizedFormData: Record<string, any> = {};
                                  tableData.columns.forEach((columnName: string) => {
                                    normalizedFormData[columnName] = toEditableFieldValue(columnName, row[columnName]);
                                  });
                                  setEditFormData(normalizedFormData);
                                  setEditError(null);
                                }}
                                title={t('adminDatabase.tableViewer.editRowHint')}
                              >
                                {tableData.columns.map((col: string) => (
                                  <td key={col} className="py-2 px-4 text-gray-300 text-xs">
                                    <div className="max-w-xs truncate" title={row[col] === null ? 'NULL' : stringifyForAdminCell(row[col])}>
                                      {row[col] === null ? (
                                        <span className="text-gray-500 italic">{t('adminDatabase.tableViewer.nullValue')}</span>
                                      ) : typeof row[col] === 'boolean' ? (
                                        <span className={row[col] ? 'text-green-400' : 'text-red-400'}>
                                          {row[col] ? 'true' : 'false'}
                                        </span>
                                      ) : (
                                        stringifyForAdminCell(row[col])
                                      )}
                                    </div>
                                  </td>
                                ))}
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Пагинация */}
                  {tableData.pages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <div className="text-gray-400 text-sm">
                        {t('adminDatabase.tableViewer.pageInfo', { page: tableData.page, pages: tableData.pages })}
                      </div>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => setTableDataPage(p => Math.max(1, p - 1))}
                          disabled={tableData.page === 1}
                          className="p-2 bg-white/5 hover:bg-white/10 text-white rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="text-gray-300 text-sm px-4">
                          {tableData.page}
                        </span>
                        <button
                          onClick={() => setTableDataPage(p => Math.min(tableData.pages, p + 1))}
                          disabled={tableData.page === tableData.pages}
                          className="p-2 bg-white/5 hover:bg-white/10 text-white rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <ChevronRightIcon className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex items-center justify-center py-12 text-red-400">
                  <AlertCircle className="w-6 h-6 mr-2" />
                  <span>{t('adminDatabase.tableViewer.error')}</span>
                </div>
              )}
            </div>
          </div>
        </ModalOverlay>
      )}

      {/* Модальное окно редактирования строки */}
      {editingRow && selectedTable && (
        <ModalOverlay onClose={() => { setEditingRow(null); setEditError(null); }}>
          <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-white/20" onClick={(e) => e.stopPropagation()}>
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-white/10">
                <h3 className="text-2xl font-bold text-white flex items-center space-x-2">
                  <Edit className="w-6 h-6" />
                  <span>{t('adminDatabase.tableViewer.editRowTitle')}</span>
                </h3>
                <button
                  onClick={() => {
                    setEditingRow(null);
                    setEditError(null);
                  }}
                  className="text-gray-400 hover:text-white transition-colors"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-6">
                {editError && (
                  <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-400 text-sm mb-4">
                    {editError}
                  </div>
                )}

                <div className="space-y-4">
                  {tableData?.columns.map((col: string) => {
                    // Пропускаем первичный ключ - его нельзя редактировать
                    const isPrimaryKey = Object.keys(editingRow.primaryKey).includes(col);
                    const value = editFormData[col];
                    const jsonField = isJsonColumn(col);
                    
                    return (
                      <div key={col}>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          {col}
                          {isPrimaryKey && <span className="text-gray-500 ml-2">{t('adminDatabase.tableViewer.primaryKeyLabel')}</span>}
                        </label>
                        {isPrimaryKey ? (
                          <input
                            type="text"
                            value={value ?? ''}
                            disabled
                            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                          />
                        ) : (
                          jsonField ? (
                            <textarea
                              value={value ?? ''}
                              onChange={(e) => {
                                const newValue = e.target.value;
                                setEditFormData(prev => ({
                                  ...prev,
                                  [col]: newValue,
                                }));
                              }}
                              rows={8}
                              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white text-sm font-mono focus:outline-none focus:border-purple-500"
                              placeholder={t('adminDatabase.tableViewer.jsonPlaceholder')}
                            />
                          ) : (
                            <input
                              type="text"
                              value={value ?? ''}
                              onChange={(e) => {
                                const newValue = e.target.value;
                                setEditFormData(prev => ({
                                  ...prev,
                                  [col]: newValue,
                                }));
                              }}
                              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-purple-500"
                              placeholder={value === null ? t('adminDatabase.tableViewer.nullValue') : ''}
                            />
                          )
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between p-6 border-t border-white/10">
                <button
                  onClick={async () => {
                    if (!selectedTable) return;
                    if (!confirm(t('adminDatabase.tableViewer.confirmDelete'))) return;
                    await deleteTableRowMutation.mutateAsync({
                      tableName: selectedTable.name,
                      primaryKey: editingRow.primaryKey,
                      schemaName: selectedTable.schema,
                    });
                  }}
                  disabled={deleteTableRowMutation.isPending}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50 flex items-center space-x-2"
                >
                  {deleteTableRowMutation.isPending ? (
                    <Loader className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                  <span>{t('adminDatabase.tableViewer.deleteButton')}</span>
                </button>
                <div className="flex items-center space-x-4">
                <button
                  onClick={() => {
                    setEditingRow(null);
                    setEditError(null);
                  }}
                  className="px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg transition-all"
                >
                  {t('adminDatabase.tableViewer.cancelButton')}
                </button>
                <button
                  onClick={async () => {
                    setEditError(null);
                    if (!selectedTable) return;
                    
                    // Готовим payload: отправляем только реально изменённые поля
                    const updateData: Record<string, unknown> = {};
                    for (const [key, rawValue] of Object.entries(editFormData)) {
                      if (Object.keys(editingRow.primaryKey).includes(key)) {
                        continue;
                      }

                      const parsed = parseEditableFieldValue(key, rawValue);
                      if (!parsed.ok) {
                        setEditError(parsed.error);
                        return;
                      }

                      const originalEditableValue = toEditableFieldValue(key, editingRow.row[key]);
                      const parsedOriginal = parseEditableFieldValue(key, originalEditableValue);
                      if (!parsedOriginal.ok) {
                        setEditError(parsedOriginal.error);
                        return;
                      }

                      const currentComparable = toEditableFieldValue(key, parsed.value);
                      const originalComparable = toEditableFieldValue(key, parsedOriginal.value);
                      if (currentComparable === originalComparable) {
                        continue;
                      }

                      updateData[key] = parsed.value;
                    }
                    
                    if (Object.keys(updateData).length === 0) {
                      setEditError(t('adminDatabase.tableViewer.noDataToUpdate'));
                      return;
                    }
                    
                    await updateTableRowMutation.mutateAsync({
                      tableName: selectedTable.name,
                      primaryKey: editingRow.primaryKey,
                      data: updateData,
                      schemaName: selectedTable.schema,
                    });
                  }}
                  disabled={updateTableRowMutation.isPending}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all disabled:opacity-50 flex items-center space-x-2"
                >
                  {updateTableRowMutation.isPending ? (
                    <>
                      <Loader className="w-4 h-4 animate-spin" />
                      <span>{t('adminDatabase.tableViewer.saving')}</span>
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      <span>{t('adminDatabase.tableViewer.saveButton')}</span>
                    </>
                  )}
                </button>
                </div>
              </div>
            </div>
        </ModalOverlay>
      )}
    </div>
  );
}
