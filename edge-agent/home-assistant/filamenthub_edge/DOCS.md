# FilamentHub Edge

## Русский

### Установка

Нужны Home Assistant OS с магазином приложений и доступ к принтерам по локальной
сети. Для Home Assistant Container тот же Edge запускается отдельным Docker
контейнером. HACS для этого приложения не используется.

1. Откройте **Настройки → Приложения → Установить приложение → меню → Репозитории**.
2. Добавьте `https://github.com/WeLizard/FilamentHub`, найдите **FilamentHub Edge**
   и нажмите **Установить**. Для установки из репозитория должен быть опубликован
   образ соответствующей версии; наличие исходников ещё не означает выпуск.
3. На вкладке **Конфигурация** оставьте HTTPS-адрес FilamentHub, добавьте
   подключения принтеров и сохраните. Если форма не сохраняет поля, откройте
   **меню → Текстовый редактор**. Затем на вкладке **Информация** нажмите **Запустить**.
4. Для постоянной работы включите **Автозагрузка**. Проверьте **Журнал** и обновите
   карточку принтера в FilamentHub: должны появиться данные слотов, а не только
   отметка об успешном подключении.

SSH, входящие порты, доступ к Supervisor API и отключение защиты не нужны.
При запуске Edge подготавливает своё локальное хранилище и продолжает работу
без прав администратора. Ключи Moonraker остаются в HA.

### Подключение принтеров

Одно приложение обслуживает несколько принтеров: добавьте каждому запись в
`connections`. Сейчас поддерживаются Moonraker с Happy Hare (`happy_hare`) и
прямая подача Klipper (`legacy`). Предел конфигурации — 32 подключения; реальная
нагрузка зависит от устройства.

В настройках системы подачи принтера в FilamentHub создайте код подключения
Edge. Укажите его вместе с локальным адресом Moonraker и, если нужен, API-ключом.
После первого успешного подключения удалите одноразовый код из настроек HA.
Новый код используйте только для обновления доступа к тому же принтеру.

Пример для двух принтеров; замените адреса и коды своими:

```yaml
filamenthub_url: https://filamenthub.ru
sync_interval: 30
allow_insecure_cloud: false
connections:
  - id: workshop-mmu
    name: Мастерская
    enabled: true
    adapter: moonraker
    material_provider: happy_hare
    moonraker_url: http://192.168.1.20:7125
    moonraker_api_key: ""
    pairing_code: FH-XXXXX-XXXXX
  - id: office-printer
    name: Офис
    enabled: true
    adapter: moonraker
    material_provider: legacy
    moonraker_url: http://192.168.1.21:7125
    moonraker_api_key: ""
    pairing_code: FH-YYYYY-YYYYY
```

После изменения настроек сохраните их и перезапустите приложение. Не меняйте
`id`: с ним связаны доступ, сохранённое состояние и очередь событий принтера.
`enabled: false` приостанавливает только выбранное подключение. Удаление записи
из настроек не удаляет её сохранённые данные; для возобновления верните тот же
`id`. Недоступность одного принтера не останавливает остальные.

Состояние хранится в локальном томе `/data`. Edge получает назначения катушек
из FilamentHub, но наблюдения принтера не заменяют их автоматически. Пустой слот
или неизвестная катушка не снимают ваше назначение.

Для Happy Hare обмен катушками и назначениями использует штатную интеграцию
Spoolman в Moonraker: сначала выполните
[настройку принтера](https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation).
При настроенном Spoolman или неизвестном состоянии этой интеграции Edge не
создаёт второй поток расхода. Самостоятельный учёт возможен только при
подтверждённом отсутствии native Spoolman, выключенной поддержке Spoolman в
Happy Hare и однозначных данных о счётчике и активной назначенной катушке.
Edge не выполняет команды принтера, не меняет гейты и не записывает NFC/RFID.

### Обновление и восстановление

Используйте кнопку **Обновить**, когда HA предложит новую версию. Сначала
прочитайте список изменений и включите приложение в резервную копию. Выполняйте
обновление и резервное копирование, когда принтеры не печатают: холодная копия
ненадолго останавливает Edge. На корректное завершение отведено до 210 секунд.
Перезапуск и замена контейнера сохраняют идентификаторы узла и подключений,
доступ и неподтверждённые события в `/data`; повторное подключение не требуется.

Не удаляйте приложение ради обновления и не запускайте одновременно второй
Edge из той же резервной копии. Копия восстанавливает прежний узел, а не создаёт
новый. Храните её безопасно — она содержит локальные ключи. После восстановления
проверьте подключения и очереди перед возобновлением печати.

- **Образ не скачивается:** проверьте, опубликована ли точная версия в GHCR
  для вашей архитектуры. Не вводите пароль FilamentHub в настройках реестра
  и не подставляйте непроверенный образ.
- **Приложение работает, но принтера нет:** проверьте список `connections`,
  сохранение настроек и перезапуск. Нужен адрес принтера, не `localhost` и не HA.
- **PairingRequired / AuthenticationError:** создайте новый код для того же
  принтера, замените только код, сохраните и перезапустите. Сохраните прежний `id`.
- **ProviderUnavailable:** проверьте адрес Moonraker и его ключ. Не отключайте
  авторизацию; другие подключения продолжат работать.
- **ConfigurationError / StateError:** исправьте указанную настройку или
  восстановите исправную резервную копию. Не удаляйте файлы состояния для запуска.

Принтеры и катушки доступны на сайте FilamentHub. Здесь находятся настройки и
журнал Edge; отдельных сущностей HA и встроенной панели управления пока нет.

## English

### Install

Requires Home Assistant OS with the Apps store and network access to your
printers. Home Assistant Container users can run the same Edge image as a
separate Docker container; HACS is not the installation path for this app.

1. Open **Settings → Apps → Install app → menu → Repositories**.
2. Add `https://github.com/WeLizard/FilamentHub`, then open **FilamentHub Edge**
   in the store and select **Install**. The matching public image must have been
   released; a repository checkout is not a published release.
3. Open **Configuration**, keep the HTTPS FilamentHub address, and add the
   printer entries below. Use HA's **Edit in YAML** option if its form does not
   expose the connection list. Save, then select **Start** on the information tab.
4. Keep **Start on boot** enabled. Check **Log**, then refresh the printer card
   in FilamentHub and verify actual slots/observations, not just a paired label.

No SSH, HACS, inbound ports, Supervisor API permission or disabled protection
mode is needed. Edge starts with a brief local storage bootstrap, then runs as
an unprivileged user; Moonraker credentials stay on this host.

### Add printers

One Edge app serves multiple printers on the local network. Add one item to
`connections` for each printer, without installing a separate app. The current
Moonraker adapter supports Happy Hare and direct Klipper feed. This runtime bounds
the configuration to 32 connections; usable capacity depends on the host.

Create an Edge pairing code for the printer's material system in FilamentHub,
paste it into that connection, and enter its local Moonraker address. The app keeps printer and
slot observations synchronized while storing the cloud token and cached spool
assignments only in Home Assistant's local `/data` volume.
After the first successful pairing, clear the one-time code from the app options.
Paste a newly issued code only when rotating the same binding.

Example configuration (add entries with distinct IDs, addresses and pairing codes):

```yaml
filamenthub_url: https://filamenthub.ru
sync_interval: 30
allow_insecure_cloud: false
connections:
  - id: workshop-mmu
    name: Workshop MMU
    enabled: true
    adapter: moonraker
    material_provider: happy_hare
    moonraker_url: http://192.168.1.20:7125
    moonraker_api_key: ""
    pairing_code: FH-XXXXX-XXXXX
  - id: office-printer
    name: Office printer
    enabled: true
    adapter: moonraker
    material_provider: legacy
    moonraker_url: http://192.168.1.21:7125
    moonraker_api_key: ""
    pairing_code: FH-YYYYY-YYYYY
```

Save the app options and restart after adding or changing entries. Keep each
connection's `id` stable: it selects its private state and retry queue. Set
`enabled: false` to pause one connection. Removing an item does not delete its
credentials or queued events; restore the same ID to resume. One offline printer
does not block the others. Preserve the app's `/data` volume across restarts.

Choose `happy_hare` for an MMU managed by Happy Hare or `legacy` for a direct
Klipper feed. The app can report replay-protected filament usage when Moonraker
provides an unambiguous counter and active desired spool. It remains read-only
toward printer hardware: it does not change gates, run local commands, or write
RFID/NFC tags.

Happy Hare inventory and assignments use Moonraker's native Spoolman integration.
Follow the [printer setup guide](https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation)
before relying on spool identity. When native Spoolman is configured or unknown,
Edge does not submit a second usage stream. Empty/unknown observations never
erase your desired spool assignments.

### Update and recovery

Use the app's **Update** action when HA offers a new version; read the changelog
and include this app in a backup first. Schedule updates/backups while printers
are idle: a cold backup briefly stops Edge so the node and connection states are
captured together. HA allows up to 210 seconds for a graceful stop. Normal
restarts and container replacement preserve the local node ID, individual
credentials and pending events in `/data`. No new pairing is needed for an update.

Do not uninstall/reinstall to update, rename connection IDs or copy a backup to
a second concurrently running Edge. A restore is recovery of this node, not
provisioning another node. Protect HA backups: they include local credentials.
After restoring, verify each binding and pending queue before resuming prints.

- **Image cannot be downloaded:** check the exact app version was published as
  a public GHCR image for your architecture. Do not enter your FilamentHub login
  as registry credentials or use an unverified replacement image.
- **App starts but no printer appears:** an empty `connections` list is valid
  but connects nothing. Add an entry, save and restart; use the printer's LAN
  address, not `localhost` or the HA address.
- **PairingRequired / AuthenticationError:** generate a new code for that same
  printer in FilamentHub, replace only its code, save and restart. Preserve the ID.
- **ProviderUnavailable:** check the local endpoint and Moonraker authentication.
  Other connections continue; do not disable authentication to resolve the error.
- **ConfigurationError / StateError:** correct the reported configuration or
  restore a known-good app backup. Do not delete state files to force startup.

The app currently has no separate ingress dashboard or HA entities. Printer and
spool state is viewed in FilamentHub; app settings and logs are managed here.

## 中文

### 安装

需要带应用商店的 Home Assistant OS，并能通过局域网访问打印机。Home Assistant
Container 用户可将同一个 Edge 镜像作为独立 Docker 容器运行；本应用不通过 HACS 安装。

1. 打开 **设置 → 应用 → 安装应用 → 菜单 → 存储库**。
2. 添加 `https://github.com/WeLizard/FilamentHub`，找到 **FilamentHub Edge** 并安装。
   对应版本的公开镜像必须已发布；源代码不等于已发布的镜像。
3. 在 **配置** 中保留 FilamentHub 的 HTTPS 地址，添加打印机连接并保存。
   如果表单无法保存字段，请使用菜单中的 **YAML 编辑器**，随后在信息页启动应用。
4. 持续运行时开启 **开机启动**。检查 **日志**，并刷新 FilamentHub 打印机卡片：
   应收到实际槽位数据，而不仅是配对成功标记。

无需 SSH、入站端口、Supervisor API 权限或关闭保护。Edge 初始化本地存储后，
以非管理员身份运行。Moonraker 密钥保留在 HA 中。

### 连接打印机

每台打印机在 `connections` 中添加一条记录，无需重复安装应用。目前支持
Moonraker 配合 Happy Hare（`happy_hare`）或 Klipper 直送料（`legacy`）。
配置最多接受 32 个连接，实际承载能力取决于设备。

在 FilamentHub 的打印机供料系统设置中创建 Edge 配对码，填入对应连接及 Moonraker
的局域网地址和可选 API 密钥。上面的 YAML 示例展示了两个独立连接；请替换其中的
名称、地址和配对码。首次配对成功后，从 HA 配置中移除一次性配对码。
新配对码仅用于更新同一打印机的访问凭据。

修改配置后保存并重启。不要更改 `id`，它对应连接凭据、持久状态和待发送事件。
设置 `enabled: false` 仅暂停该连接。移除配置项不会删除已保存的数据；恢复相同
`id` 即可继续。某台打印机离线不会阻塞其他连接。

`/data` 保存连接状态及从 FilamentHub 获取的料盘分配。观测到空槽位或未知料盘
不会自动清除您指定的分配。Happy Hare 的料盘和分配交换使用 Moonraker 原生
Spoolman 集成；请先完成
[打印机设置](https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation)。
已配置原生 Spoolman，或无法确认其状态时，Edge 不会发送第二份用量。
只有确认无原生 Spoolman、Happy Hare 的 Spoolman 支持关闭，且计数器与当前分配
料盘均明确时，才可独立上传用量。Edge 不发送打印机命令、不切换槽位，也不写入 NFC/RFID。

### 更新与恢复

HA 提供新版本时，先阅读更新说明并备份本应用，再使用 **更新**。请在打印机空闲时
更新和备份：冷备份会短暂停止 Edge，正常停止最多等待 210 秒。重启或替换容器会保留
`/data` 中的节点和连接标识、凭据及待发送事件，无需再次配对。

不要通过卸载重装来更新，也不要在另一台同时运行的 Edge 上使用同一备份。恢复备份
是恢复原节点，而不是建立新节点。备份含本地密钥，请妥善保管，并在恢复后检查连接
和事件队列，再恢复打印。

- **镜像无法下载：** 确认 GHCR 中已发布适配当前架构的准确版本。不要将 FilamentHub
  登录密码用作镜像仓库凭据，也不要替换为未经验证的镜像。
- **应用运行但没有打印机：** 检查 `connections` 是否为空，保存后重启。使用打印机
  的局域网地址，而非 `localhost` 或 HA 地址。
- **PairingRequired / AuthenticationError：** 为同一打印机创建新配对码，仅替换配对码，
  保存并重启；保留原 `id`。
- **ProviderUnavailable：** 检查 Moonraker 地址及密钥，不要关闭身份验证。其他连接仍可运行。
- **ConfigurationError / StateError：** 修正报错的配置或恢复有效备份，不要删除状态文件强行启动。

打印机与料盘在 FilamentHub 网站查看；本应用提供配置与日志，尚不提供 HA 实体或内嵌控制面板。
