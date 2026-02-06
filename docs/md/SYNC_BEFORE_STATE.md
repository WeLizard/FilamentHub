# Состояние базы данных и OrcaSlicer ДО синхронизации

**Дата:** 2025-11-23  
**Пользователь:** admin (id=6, email=admin@filamenthub.ru)

## Пресеты пользователя admin в базе данных

| ID | Название | Filament ID | Active | Source | External ID | Sync Enabled | Updated At |
|----|----------|-------------|--------|--------|-------------|--------------|------------|
| 14 | PolyTerra Green Standard | 8 | True | user | NULL | **True** | 2025-11-13 20:30:19 |
| 15 | ТЕСТПРЕСЕТ | 9 | True | user | NULL | False | 2025-11-13 20:32:50 |
| 16 | 100проц печать | 10 | True | user | NULL | False | 2025-11-13 20:29:06 |
| 17 | ТЫЛох | 11 | True | user | NULL | False | 2025-11-13 20:32:45 |
| 18 | Золотище | 12 | True | user | NULL | False | 2025-11-13 20:32:46 |

**Всего пресетов:** 5  
**С sync_enabled=True:** 1 (PolyTerra Green Standard)

## Пресеты в OrcaSlicer (user/2136879404/filament/)

**Важно:** Это номерной каталог от BambuLab сервера (2136879404 - ID пользователя на сервере BambuLab).

### С постфиксом [FilamentHub]:
**Примечание:** Файлы с [FilamentHub] в данный момент не найдены в этой директории. Возможно, они будут созданы при синхронизации или находятся в другом месте.

### Без постфикса [FilamentHub] (локальные пресеты пользователя):
- ABS HTP
- ABS НИТ
- ABS
- HTP ABS-5
- HTP ABS-6
- HTP PETG Black
- HTP PETG
- (и другие в base/)

## Детали пресетов в OrcaSlicer

**Примечание:** Пресеты с [FilamentHub] в user/2136879404/filament/ не найдены в данный момент. После синхронизации нужно проверить:
- Создались ли новые пресеты с [FilamentHub] в этой директории
- Обновились ли существующие пресеты с метаданными FilamentHub
- Появились ли метки `fhub_id`, `fhub_source` в JSON файлах
- Заполнились ли поля `sync_info`, `user_id`, `setting_id` в .info файлах

## Ожидаемое поведение при синхронизации

1. **Пресеты с sync_enabled=True** должны синхронизироваться:
   - PolyTerra Green Standard (id=14) → должен экспортироваться в OrcaSlicer

2. **Пресеты с sync_enabled=False** НЕ должны синхронизироваться:
   - ТЕСТПРЕСЕТ (id=15)
   - 100проц печать (id=16)
   - ТЫЛох (id=17)
   - Золотище (id=18)

3. **Пресеты из OrcaSlicer** (без [FilamentHub] или с external_id) могут быть импортированы в базу как черновики

4. **После синхронизации проверить:**
   - Создались ли пресеты с [FilamentHub] в `user/2136879404/filament/` (номерной каталог BambuLab)
   - Обновились ли .info файлы с правильными метаданными FilamentHub (`sync_info`, `user_id`, `setting_id`)
   - Появились ли метки `fhub_id`, `fhub_source` в JSON файлах
   - Создались ли новые черновики в базе данных
   - Экспортировался ли пресет PolyTerra Green Standard (id=14, sync_enabled=True) в OrcaSlicer

---

**Следующий шаг:** После синхронизации сравнить с этим состоянием.

