# FilamentHub Edge

## Русский

Мост между FilamentHub и принтерами в вашей локальной сети. **Одна установка
для дома, мастерской или офиса — несколько независимых подключений принтеров.**
Сейчас поддерживаются Moonraker с Happy Hare и прямая подача Klipper.

Edge передаёт состояние принтера и слотов, получает назначения катушек из
FilamentHub и сохраняет подключение при перезапуске. Данные принтера не меняют
назначенную вами катушку автоматически. При включённом native Spoolman Edge
не отправляет второй поток расхода.

Откройте **Конфигурация**, добавьте принтер, сохраните настройки и запустите
приложение. Если форма не сохраняет поля, используйте её **Текстовый редактор**.
Подробности — на вкладке **Документация**, состояние подключения — в **Журнале**.
Принтеры и катушки отображаются на сайте FilamentHub; отдельных сущностей HA
и панели управления принтерами в этом приложении пока нет.

Ключи принтеров остаются в HA. Открывать входящие порты или отключать защиту
не нужно. Команды принтеру и запись NFC/RFID не выполняются.

## English

A bridge between FilamentHub and printers on your local network. **One installation
for a home, workshop or office, with multiple independent printer connections.**
Moonraker with Happy Hare and direct Klipper feed are currently supported.

Edge sends printer and slot observations, receives spool assignments from
FilamentHub and preserves connections across restarts. Observations never change
your assigned spool automatically. With native Spoolman configured, Edge does not
send a second usage stream.

Open **Configuration**, add a printer, save and start the app. Use **Edit in YAML**
if the form does not save its fields. See **Documentation** for instructions and
**Log** for connection status. View printers and spools in FilamentHub; this app
does not yet provide HA entities or a printer-control dashboard.

Printer credentials stay in HA. No inbound ports or disabled protection are
needed. The app does not send printer commands or write NFC/RFID tags.

## 中文

连接 FilamentHub 与局域网打印机的桥接应用。**家庭、工作室或办公室只需安装一次，
即可建立多个相互独立的打印机连接。** 目前支持 Moonraker 配合 Happy Hare，以及
Klipper 直送料。

Edge 上传打印机与槽位状态，接收 FilamentHub 中的料盘分配，并在重启后保留连接。
观测数据不会自动改变您分配的料盘。已配置原生 Spoolman 时，Edge 不会重复上传耗材用量。

打开 **配置**，添加打印机、保存并启动应用。如果表单无法保存字段，请使用 **YAML 编辑器**。
操作说明在 **文档** 中，连接状态在 **日志** 中。打印机与料盘在 FilamentHub 网站查看；
本应用尚不提供 HA 实体或打印机控制面板。

打印机密钥保留在 HA 本地。无需开放入站端口或关闭保护。应用不会发送打印机命令，
也不会写入 NFC/RFID 标签。
