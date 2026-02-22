"""Централизованные русскоязычные сообщения об ошибках для HTTP-ответов."""

# 404 — Не найдено
ERR_USER_NOT_FOUND = "Пользователь не найден"
ERR_BRAND_NOT_FOUND = "Бренд не найден"
ERR_PRESET_NOT_FOUND = "Пресет не найден"
ERR_FILAMENT_NOT_FOUND = "Материал не найден"
ERR_PRINTER_NOT_FOUND = "Принтер не найден"
ERR_REQUEST_NOT_FOUND = "Заявка не найдена"
ERR_NOTIFICATION_NOT_FOUND = "Уведомление не найдено"
ERR_FEEDBACK_NOT_FOUND = "Обратная связь не найдена"
ERR_REVIEW_NOT_FOUND = "Отзыв не найден"
ERR_ARTICLE_NOT_FOUND = "Статья не найдена"

# 400 — Дублирование / конфликт
ERR_BRAND_SLUG_EXISTS = "Бренд с таким slug уже существует"
ERR_PRINTER_SLUG_EXISTS = "Принтер с таким slug уже существует"
ERR_EMAIL_EXISTS = "Email уже зарегистрирован"
ERR_USERNAME_EXISTS = "Имя пользователя уже занято"
ERR_USER_ALREADY_IN_BRAND = "Пользователь уже привязан к бренду"
ERR_USER_NOT_IN_BRAND = "Пользователь не привязан к бренду"
ERR_REQUEST_NOT_PENDING = "Можно изменять только ожидающие заявки"

# 401 — Аутентификация
ERR_INVALID_CREDENTIALS = "Неверный email/логин или пароль"
ERR_INVALID_REFRESH_TOKEN = "Токен обновления недействителен или истёк"
ERR_INVALID_VERIFICATION_TOKEN = "Токен верификации недействителен или истёк"

# 403 — Права доступа
ERR_ACCOUNT_INACTIVE = "Аккаунт пользователя неактивен"
ERR_NO_PERMISSION_CREATE_FILAMENT = "Недостаточно прав. Вы можете создавать материалы только для своего бренда."
ERR_NO_PERMISSION_EDIT_FILAMENT = "Недостаточно прав. Вы можете редактировать материалы только своего бренда."
ERR_NO_PERMISSION_DELETE_FILAMENT = "Недостаточно прав. Вы можете удалять материалы только своего бренда."
ERR_NO_PERMISSION_EDIT_PRESET = "Вы можете редактировать только свои пресеты"
ERR_NO_PERMISSION_DELETE_PRESET = "Вы можете удалять только свои пресеты"
ERR_WEIGHTED_PRESET_READONLY = "Взвешенные пресеты нельзя редактировать напрямую"
ERR_WEIGHTED_PRESET_NO_DELETE = "Взвешенные пресеты нельзя удалять напрямую"
