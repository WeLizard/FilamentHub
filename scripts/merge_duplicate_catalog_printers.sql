-- Разовая чистка: каталожные записи принтеров, которые аккаунт успел создать сам
-- до импорта бандла OrcaSlicer. Бандл принёс те же модели как системные записи,
-- и две записи на одну модель разрывают принтеры человека: одно устройство
-- смотрит на пользовательскую запись, другое на системную.
--
-- Пользовательская запись передаёт системной пресеты, конфигурации, устройства и
-- совместимость процессов, после чего удаляется. Системную оставляем: её
-- обновляет импорт бандла, удалённая вернётся при следующем импорте.
--
-- Запуск (прод):
--   cat scripts/merge_duplicate_catalog_printers.sql \
--     | docker exec -i filamenthub_postgres_prod psql -U filamenthub -d filamenthub

BEGIN;

CREATE TEMP TABLE printer_merge_pairs AS
SELECT mine.id AS mine_id, mine.slug AS mine_slug,
       theirs.id AS theirs_id, theirs.slug AS theirs_slug
FROM printers AS mine
JOIN printers AS theirs
  ON theirs.source = 'system'
 AND lower(theirs.name) = lower(mine.name)
 AND theirs.id <> mine.id
WHERE mine.source <> 'system';

\echo 'Будут склеены:'
SELECT mine_id, mine_slug, theirs_id, theirs_slug FROM printer_merge_pairs;

-- Пресет, уже привязанный к системной записи, иначе задвоится.
DELETE FROM preset_printers AS victim
USING printer_merge_pairs AS p
WHERE victim.printer_id = p.mine_id
  AND EXISTS (
      SELECT 1 FROM preset_printers AS kept
      WHERE kept.printer_id = p.theirs_id AND kept.preset_id = victim.preset_id
  );

UPDATE preset_printers AS t SET printer_id = p.theirs_id
FROM printer_merge_pairs AS p WHERE t.printer_id = p.mine_id;

UPDATE printer_profiles AS t SET printer_id = p.theirs_id
FROM printer_merge_pairs AS p WHERE t.printer_id = p.mine_id;

UPDATE user_printer_devices AS t SET printer_id = p.theirs_id
FROM printer_merge_pairs AS p WHERE t.printer_id = p.mine_id;

DELETE FROM print_profile_printers AS victim
USING printer_merge_pairs AS p
WHERE victim.printer_id = p.mine_id
  AND EXISTS (
      SELECT 1 FROM print_profile_printers AS kept
      WHERE kept.printer_id = p.theirs_id
        AND kept.print_profile_id = victim.print_profile_id
  );

UPDATE print_profile_printers AS t
   SET printer_id = p.theirs_id, printer_slug = p.theirs_slug
FROM printer_merge_pairs AS p WHERE t.printer_id = p.mine_id;

-- Совместимость, записанная одним слагом, без разрешённого идентификатора.
UPDATE print_profile_printers AS t SET printer_slug = p.theirs_slug
FROM printer_merge_pairs AS p
WHERE t.printer_id IS NULL AND t.printer_slug = p.mine_slug;

DELETE FROM printers AS t USING printer_merge_pairs AS p WHERE t.id = p.mine_id;

\echo 'Осталось моделей с одинаковым именем:'
SELECT name, count(*) FROM printers GROUP BY name HAVING count(*) > 1;

COMMIT;
