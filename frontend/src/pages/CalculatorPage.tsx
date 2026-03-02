/**
 * Страница Калькулятора стоимости 3D-печати
 * Новая улучшенная версия с историей расчётов и загрузкой G-кода
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Calculator, Upload, FileText, Save, Download, Trash2, Eye, Clock, DollarSign, Weight, Printer } from 'lucide-react';

export const CalculatorPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'calculator' | 'history'>('calculator');

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900">
      {/* Header */}
      <div className="bg-black/20 backdrop-blur-sm border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-3 bg-purple-600/20 rounded-xl border border-purple-500/30">
                <Calculator className="w-8 h-8 text-purple-400" />
              </div>
              <div>
                <h1 className="text-2xl md:text-3xl font-bold text-white">
                  {t('calculator.title')}
                </h1>
                <p className="text-sm text-gray-400 mt-1">
                  {t('calculator.subtitle')}
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2">
              <button
                onClick={() => setActiveTab('calculator')}
                className={`px-4 py-2 rounded-lg transition-all text-sm font-medium ${
                  activeTab === 'calculator'
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Calculator className="w-4 h-4 inline mr-2" />
                {t('calculator.tabs.calculator')}
              </button>
              <button
                onClick={() => setActiveTab('history')}
                className={`px-4 py-2 rounded-lg transition-all text-sm font-medium ${
                  activeTab === 'history'
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Clock className="w-4 h-4 inline mr-2" />
                {t('calculator.tabs.history')}
                <span className="ml-2 px-2 py-0.5 bg-purple-500/30 rounded-full text-xs">
                  0
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'calculator' ? (
          <CalculatorView />
        ) : (
          <HistoryView />
        )}
      </div>
    </div>
  );
};

/** View: Калькулятор (основная форма) */
const CalculatorView: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Левая панель: Ввод параметров */}
      <div className="lg:col-span-2 space-y-6">
        {/* Загрузка G-кода */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Upload className="w-5 h-5 text-purple-400" />
            {t('calculator.uploadGcode')}
          </h3>
          
          <div className="border-2 border-dashed border-gray-600 hover:border-purple-500 rounded-xl p-8 transition-all cursor-pointer bg-gray-900/50">
            <div className="text-center">
              <Upload className="w-12 h-12 text-gray-500 mx-auto mb-4" />
              <p className="text-white font-medium mb-2">
                {t('calculator.dragDropGcode')}
              </p>
              <p className="text-sm text-gray-400">
                {t('calculator.orClickToSelect')}
              </p>
              <p className="text-xs text-gray-500 mt-2">
                {t('calculator.supportedFormats')}
              </p>
            </div>
          </div>
        </div>

        {/* Параметры материала */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Weight className="w-5 h-5 text-purple-400" />
            {t('calculator.materialSection')}
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('calculator.selectMaterial')}
              </label>
              <select className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent">
                <option value="">{t('calculator.chooseFromCatalog')}</option>
                {/* Здесь будет список материалов из API */}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.partWeight')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-12"
                    placeholder="0"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    {t('calculator.grams')}
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.supportsWeight')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-12"
                    placeholder="0"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    {t('calculator.grams')}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.spoolPrice')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-12"
                    placeholder="0"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    ₽
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.spoolWeight')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-12"
                    placeholder="1"
                    step="0.1"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    {t('calculator.kg')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Время печати */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <Clock className="w-5 h-5 text-purple-400" />
            {t('calculator.printTimeSection')}
          </h3>
          
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('calculator.hours')}
              </label>
              <input
                type="number"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="0"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('calculator.minutes')}
              </label>
              <input
                type="number"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="0"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {t('calculator.seconds')}
              </label>
              <input
                type="number"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                placeholder="0"
              />
            </div>
          </div>
        </div>

        {/* Дополнительные параметры */}
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
          <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-purple-400" />
            {t('calculator.ratesSection')}
          </h3>
          
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.printingRate')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-16"
                    placeholder="170"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    ₽/{t('calculator.hourAbbr')}
                  </span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.electricityCost')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-16"
                    placeholder="6"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    ₽/{t('calculator.kwhAbbr')}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.quantity')}
                </label>
                <input
                  type="number"
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                  placeholder="1"
                  min="1"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {t('calculator.printerPower')}
                </label>
                <div className="relative">
                  <input
                    type="number"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-purple-500 focus:border-transparent pr-12"
                    placeholder="350"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 text-sm">
                    {t('calculator.wattAbbr')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Кнопка расчёта */}
        <button
          className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-bold py-4 px-6 rounded-xl shadow-lg shadow-purple-500/25 transition-all transform hover:scale-[1.02] active:scale-[0.98]"
        >
          <Calculator className="w-5 h-5 inline mr-2" />
          {t('calculator.calculateButton')}
        </button>
      </div>

      {/* Правая панель: Результаты */}
      <div className="lg:col-span-1">
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6 sticky top-6">
          <h3 className="text-lg font-bold text-white mb-6">
            {t('calculator.resultsTitle')}
          </h3>

          {/* Итоговая сумма */}
          <div className="bg-gradient-to-br from-purple-600/20 to-pink-600/20 rounded-xl p-6 border border-purple-500/30 mb-6">
            <p className="text-sm text-gray-400 mb-2">
              {t('calculator.totalCost')}
            </p>
            <p className="text-4xl font-bold text-white">
              0.00 ₽
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {t('calculator.perPart')}: 0.00 ₽
            </p>
          </div>

          {/* Детализация */}
          <div className="space-y-3 mb-6">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('calculator.material')}</span>
              <span className="text-white">0.00 ₽</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('calculator.electricity')}</span>
              <span className="text-white">0.00 ₽</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('calculator.printing')}</span>
              <span className="text-white">0.00 ₽</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('calculator.overhead')}</span>
              <span className="text-white">0.00 ₽</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('calculator.markup')}</span>
              <span className="text-white">0.00 ₽</span>
            </div>
          </div>

          {/* Кнопки действий */}
          <div className="space-y-3">
            <button
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-3 px-4 rounded-lg transition-all flex items-center justify-center gap-2"
            >
              <Save className="w-4 h-4" />
              {t('calculator.saveToHistory')}
            </button>

            <button
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-3 px-4 rounded-lg transition-all flex items-center justify-center gap-2"
            >
              <FileText className="w-4 h-4" />
              {t('calculator.generateQuote')}
            </button>
          </div>

          {/* Инфо */}
          <div className="mt-6 pt-6 border-t border-gray-700">
            <div className="flex items-start gap-3">
              <div className="p-2 bg-yellow-500/10 rounded-lg">
                <Printer className="w-5 h-5 text-yellow-400" />
              </div>
              <div>
                <p className="text-sm text-gray-300">
                  {t('calculator.printTimeEstimate')}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {t('calculator.basedOnGcode')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/** View: История расчётов */
const HistoryView: React.FC = () => {
  const { t } = useTranslation();

  return (
    <div className="bg-gray-800/50 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-white">
          {t('calculator.historyTitle')}
        </h2>
        
        <div className="flex gap-2">
          <button className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-all">
            <Download className="w-4 h-4 inline mr-2" />
            {t('calculator.export')}
          </button>
          <button className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 text-sm rounded-lg transition-all border border-red-500/30">
            <Trash2 className="w-4 h-4 inline mr-2" />
            {t('calculator.deleteSelected')}
          </button>
        </div>
      </div>

      {/* Пустое состояние */}
      <div className="text-center py-16">
        <Clock className="w-16 h-16 text-gray-600 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-white mb-2">
          {t('calculator.noHistory')}
        </h3>
        <p className="text-gray-400 mb-6">
          {t('calculator.noHistoryDescription')}
        </p>
        <button className="px-6 py-3 bg-purple-600 hover:bg-purple-500 text-white font-medium rounded-lg transition-all">
          {t('calculator.createFirstCalculation')}
        </button>
      </div>

      {/* Таблица (когда будут данные) */}
      {/* <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                <input type="checkbox" className="rounded bg-gray-700 border-gray-600" />
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.name')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.date')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.client')}
              </th>
              <th className="text-left py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.status')}
              </th>
              <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.cost')}
              </th>
              <th className="text-right py-3 px-4 text-sm font-medium text-gray-400">
                {t('calculator.actions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {/* Строки таблицы * /}
          </tbody>
        </table>
      </div> */}
    </div>
  );
};
