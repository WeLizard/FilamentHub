/** Модальное окно с согласием на обработку персональных данных */

import { Link } from 'react-router-dom';
import { X, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface ConsentModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ConsentModal: React.FC<ConsentModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  if (!isOpen) return null;

  return (
    <div className={`fixed inset-0 z-[60] flex items-center justify-center p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onClose}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20 shadow-xl z-10 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/20">
          <h2 className="text-2xl font-bold text-white">{t('consentModal.title')}</h2>
          <div className="flex items-center space-x-2">
            <Link
              to="/personal-data-consent"
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => {
                e.stopPropagation();
              }}
              className="flex items-center space-x-1 px-3 py-1.5 text-sm bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all border border-white/20"
            >
              <ExternalLink className="w-4 h-4" />
              <span>{t('consentModal.full_version')}</span>
            </Link>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 text-gray-300">
          <div className="prose prose-invert max-w-none space-y-6">
            <section>
              <h3 className="text-xl font-bold text-white mb-4">1. Общие положения</h3>
              <p className="mb-2">
                1.1. Данное Согласие дается на обработку персональных данных, как без использования средств автоматизации,
                так и с их использованием.
              </p>
              <p className="mb-2">
                1.2. Согласие дается на обработку следующих моих персональных данных:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Адрес электронной почты;</li>
                <li>Никнейм (имя пользователя);</li>
                <li>ФИО (только при добровольном указании Пользователем в профиле или при обращении к Оператору);</li>
                <li>Иные данные профиля, которые Пользователь указывает добровольно (например, поле «о себе»);</li>
                <li>
                  Данные, предоставляемые при подаче заявки на верификацию как представитель бренда или производителя:
                  <ul className="list-disc list-inside ml-6 mt-1 space-y-1">
                    <li>Наименование бренда / торговой марки;</li>
                    <li>Корпоративный email;</li>
                    <li>Официальный сайт;</li>
                    <li>Ссылки на социальные сети бренда;</li>
                    <li>Сканы/файлы подтверждающих документов (доверенность, выписка из ЕГРЮЛ/ЕГРИП, письмо на фирменном бланке и т.п.).</li>
                  </ul>
                  Указанные данные обрабатываются исключительно в целях верификации полномочий Пользователя и администрирования кабинета производителя. Данные о бренде не относятся к персональным данным Пользователя, но предоставляются им добровольно и с его согласия.
                </li>
                <li>Технические данные, обрабатываемые при использовании сервиса: IP-адрес, user-agent, дата и время запросов, служебные технические идентификаторы;</li>
                <li>Настройки печати, передаваемые при использовании функции синхронизации: пресеты материалов,
                  профили принтеров, профили печати и связанные технические параметры (температуры, скорости,
                  коэффициенты потока и т.п.).</li>
              </ul>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">2. Цель обработки персональных данных</h3>
              <p className="mb-2">
                2.1. Цель обработки персональных данных: регистрация пользователя на сайте FilamentHub, предоставление
                услуг, а также верификация Пользователя в качестве официального представителя бренда или производителя материалов для 3D-печати в соответствии с{' '}
                <Link
                  to="/user-agreement"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  Пользовательским соглашением
                </Link>{' '}
                (<Link
                  to="/user-agreement"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  /user-agreement
                </Link>
                ), включая:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Поддержание оперативной связи с Пользователем;</li>
                <li>Упрощение процесса коммуникации среди Пользователей Сервиса;</li>
                <li>Информирование Пользователя об услугах и продуктах Сервиса, которые могут представлять для него интерес;</li>
                <li>Обеспечение безопасности использования Сервиса;</li>
                <li>Улучшение качества предоставляемых услуг;</li>
                <li>Статистика и аналитика использования Сервиса.</li>
              </ul>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">3. Действия с персональными данными</h3>
              <p className="mb-2">
                3.1. В ходе обработки с персональными данными будут совершены следующие действия:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Сбор;</li>
                <li>Систематизация;</li>
                <li>Хранение;</li>
                <li>Использование;</li>
                <li>Извлечение;</li>
                <li>Блокирование;</li>
                <li>Уничтожение;</li>
                <li>Запись;</li>
                <li>Удаление;</li>
                <li>Накопление;</li>
                <li>Обновление;</li>
                <li>Изменение;</li>
                <li>Обезличивание;</li>
                <li>Передача (в пределах указанных в настоящем Согласии целей).</li>
              </ul>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">4. Срок действия согласия</h3>
              <p className="mb-2">
                4.1. Персональные данные обрабатываются до удаления пользователем личного кабинета на сайте.
              </p>
              <p className="mb-2">
                4.2. Согласие Пользователя на обработку его персональных данных действует бессрочно до момента отзыва
                согласия.
              </p>
              <p className="mb-2">
                4.3. В случае отзыва согласия Оператор прекращает обработку персональных данных и уничтожает их в срок,
                не превышающий 7 дней с даты поступления отзыва (при самостоятельном удалении через интерфейс личного кабинета)
                или 30 дней при запросе через форму обратной связи или почтовое уведомление, если иное не предусмотрено договором,
                стороной которого является субъект персональных данных, или иным соглашением между Оператором и субъектом персональных данных.
              </p>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">5. Порядок отзыва согласия</h3>
              <p className="mb-2">
                5.1. Согласие может быть отозвано субъектом персональных данных или его представителем путем направления
                заявления Оператору по адресу электронной почты: admin@filamenthub.ru.
              </p>
              <p className="mb-2">
                5.2. В заявлении об отзыве согласия должна содержаться следующая информация:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Адрес электронной почты, на который был зарегистрирован аккаунт;</li>
                <li>Никнейм (имя пользователя) или ID аккаунта (при наличии);</li>
                <li>ФИО (если ранее предоставлялись Оператору);</li>
                <li>Текст заявления об отзыве согласия на обработку персональных данных.</li>
              </ul>
              <p className="mb-2">
                5.3. После получения заявления об отзыве согласия Оператор прекращает обработку персональных данных и
                удаляет персональные данные в соответствии с п. 4.3 настоящего Согласия.
              </p>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">6. Защита персональных данных</h3>
              <p className="mb-2">
                6.1. Оператор не передает персональные данные Пользователей третьим лицам и не совершает трансграничную
                передачу персональных данных.
              </p>
              <p className="mb-2">
                6.2. Оператор принимает необходимые правовые, организационные и технические меры для защиты персональных
                данных от неправомерного или случайного доступа к ним, уничтожения, изменения, блокирования, копирования,
                предоставления, распространения персональных данных, а также от иных неправомерных действий в отношении
                персональных данных.
              </p>
              <p className="mb-2">
                6.3. Оператор гарантирует конфиденциальность персональных данных и не разглашает их без согласия
                субъекта персональных данных, за исключением случаев, предусмотренных законодательством Российской
                Федерации.
              </p>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">7. Информирование об использовании Cookie</h3>
              <p className="mb-2">
                7.1. Оператор собирает данные, не относящиеся к информации, идентифицирующей личность Пользователя,
                которые становятся доступными в результате использования клиентом Веб-сайта.
              </p>
              <p className="mb-2">
                7.2. Оператор использует Cookie-файлы для обеспечения работы отдельных функций Веб-сайта, включая:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Авторизацию пользователя;</li>
                <li>Сохранение пользовательских настроек;</li>
                <li>Аналитику посещений;</li>
                <li>Улучшение функциональности сайта.</li>
              </ul>
              <p className="mb-2">
                7.3. Пользователь может отключить использование Cookie-файлов в настройках браузера, однако это может
                привести к ограничению функциональности сайта.
              </p>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">8. Права субъекта персональных данных</h3>
              <p className="mb-2">
                8.1. Субъект персональных данных имеет право:
              </p>
              <ul className="list-disc list-inside ml-4 mb-4 space-y-1">
                <li>Получать информацию, касающуюся обработки его персональных данных;</li>
                <li>Требовать уточнения, блокирования или уничтожения персональных данных, если персональные данные
                  являются неполными, устаревшими, неточными, незаконно полученными или не являются необходимыми для
                  заявленной цели обработки;</li>
                <li>Отозвать согласие на обработку персональных данных;</li>
                <li>Обжаловать действия или бездействие Оператора в уполномоченный орган по защите прав субъектов
                  персональных данных или в судебном порядке;</li>
                <li>На получение информации о сроках хранения персональных данных.</li>
              </ul>
            </section>

            <section>
              <h3 className="text-xl font-bold text-white mb-4">9. Контактная информация</h3>
              <p className="mb-2">
                9.1. По всем вопросам, связанным с обработкой персональных данных, субъект персональных данных может
                обратиться к Оператору по адресу электронной почты: admin@filamenthub.ru.
              </p>
              <p className="mb-2">
                9.2. Пользовательское соглашение доступно на странице{' '}
                <Link
                  to="/user-agreement"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  Пользовательского соглашения
                </Link>{' '}
                (<Link
                  to="/user-agreement"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline"
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  /user-agreement
                </Link>
                ).
              </p>
            </section>

            <section className="mt-8 pt-6 border-t border-white/20">
              <p className="text-sm text-gray-400">
                Подтверждая регистрацию на сайте FilamentHub, Пользователь подтверждает, что ознакомился с условиями
                настоящего Согласия на обработку персональных данных и полностью их принимает.
              </p>
            </section>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end p-6 border-t border-white/20">
          <button
            onClick={onClose}
            className="px-6 py-3 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40"
          >
            {t('consentModal.close_button')}
          </button>
        </div>
      </div>
    </div>
  );
};

