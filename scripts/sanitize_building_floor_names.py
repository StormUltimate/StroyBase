#!/usr/bin/env python
# scripts/sanitize_building_floor_names.py — StroyBase
# Однократная очистка данных: санитизация названий и удаление дубликатов в buildings и floors.
# Запуск: из корня проекта:
#   python scripts/sanitize_building_floor_names.py [--dry-run] [--batch-size N] [--yes] [--restore-prefixes] [--quiet]
#
# Политика проекта: миграции БД не используются (pgAdmin). Скрипт выполняет только данные (UPDATE/DELETE).
# Откат не предусмотрен: очистка необратима. Рекомендуется снимок БД перед запуском.

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime

# Корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Санитизация названий и дедупликация buildings/floors. Необратимо без --dry-run.'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Только симуляция: вывести, что было бы изменено/удалено, без COMMIT и без записи в БД.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        metavar='N',
        help='Размер батча для коммитов (по умолчанию 100).'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Пропустить запрос подтверждения при удалении >10%% записей.'
    )
    parser.add_argument(
        '--restore-prefixes',
        action='store_true',
        default=True,
        help='Восстанавливать известные сломанные префиксы (а гб N → Корпус N, аж N → Этаж N). (по умолчанию: вкл.)'
    )
    parser.add_argument(
        '--no-restore-prefixes',
        action='store_false',
        dest='restore_prefixes',
        help='Отключить восстановление префиксов.'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Меньше вывода: не печатать каждую замену before→after, только сводки и предупреждения.'
    )
    return parser.parse_args()


class DualLogger:
    """Пишет одно и то же сообщение в файл и в stdout."""
    def __init__(self, filepath):
        self._path = filepath
        self._file = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._file = open(self._path, 'w', encoding='utf-8')
        return self

    def __exit__(self, *args):
        if self._file:
            self._file.close()

    def log(self, msg):
        line = msg if msg.endswith('\n') else msg + '\n'
        print(msg, flush=True)
        if self._file:
            self._file.write(line)
            self._file.flush()


def run(app, dry_run=False, batch_size=100, skip_confirm=False, restore_prefixes=True, quiet=False):
    """Выполнить очистку в контексте приложения."""
    from app.extensions import db
    from app.models import (
        Building, Floor, Document, MaterialMovement, ScheduleWork,
        BuildingParticipant, Plan, Mark, FloorMaterial, FloorEquipment, FloorQuantity, Task,
    )
    from app.utils.sanitize_names import (
        normalize_name,
        normalized_key_for_dedup,
        restore_known_patterns,
    )

    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    log_filename = f"sanitize_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = os.path.join(log_dir, log_filename)

    with app.app_context():
        with DualLogger(log_path) as dual:
            def log(msg):
                dual.log(msg)

            log(f"Скрипт запущен: dry_run={dry_run}, batch_size={batch_size}, restore_prefixes={restore_prefixes}")
            if dry_run:
                log("[DRY-RUN] Изменения в БД не вносятся.")

            # --- Проверка на циклические FK (Building ↔ Floor только Floor→Building) ---
            log("Проверка FK: Floor.building_id → Building.id (циклов нет).")

            # Загружаем все записи
            buildings = Building.query.order_by(Building.id).all()
            floors = Floor.query.order_by(Floor.id).all()
            total_b = len(buildings)
            total_f = len(floors)
            log(f"Всего buildings: {total_b}, floors: {total_f}")

            # В памяти считаем, сколько зданий/этажей будет удалено после санитизации и дедупликации
            # 1) Санитизированные имена (для подсчёта дублей); при restore_prefixes — восстановление «Корпус N»/«Этаж N»
            def safe_name_b(b):
                raw = b.name
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    return f"Корпус {b.id}"
                cleaned = normalize_name(raw, f"Корпус {b.id}")
                if restore_prefixes:
                    restored = restore_known_patterns(cleaned, 'building', b.id)
                    if restored is not None:
                        return restored
                return cleaned

            def safe_name_f(f):
                raw = f.name
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    return f"Этаж {f.id}"
                cleaned = normalize_name(raw, f"Этаж {f.id}")
                if restore_prefixes:
                    restored = restore_known_patterns(cleaned, 'floor', f.id)
                    if restored is not None:
                        return restored
                return cleaned

            building_norm = {b.id: (b.project_id, normalized_key_for_dedup(safe_name_b(b))) for b in buildings}
            building_groups_pre = defaultdict(list)
            for bid, key in building_norm.items():
                building_groups_pre[key].append(bid)
            dup_building_count = sum(len(ids) - 1 for ids in building_groups_pre.values() if len(ids) > 1)

            floor_norm = {f.id: (f.building_id, normalized_key_for_dedup(safe_name_f(f))) for f in floors}
            floor_groups_pre = defaultdict(list)
            for fid, key in floor_norm.items():
                floor_groups_pre[key].append(fid)
            dup_floor_count = sum(len(ids) - 1 for ids in floor_groups_pre.values() if len(ids) > 1)

            total_records = total_b + total_f
            to_delete = dup_building_count + dup_floor_count
            if total_records > 0 and to_delete / total_records > 0.10 and not dry_run and not skip_confirm:
                log(f"Внимание: будет удалено {to_delete} записей (buildings: {dup_building_count}, floors: {dup_floor_count}), "
                    f">{10}% от общего числа ({total_records}). Подтвердите: введите 'yes' для продолжения или 'no' для отмены.")
                try:
                    answer = input("> ").strip().lower()
                except EOFError:
                    answer = "no"
                if answer != 'yes':
                    log("Отменено пользователем.")
                    return
                log("Подтверждено, продолжаем.")

            # --- [1/4] Санитизация названий в buildings ---
            log("[1/4] Санитизация названий в buildings...")
            updated_b = 0
            for i, b in enumerate(buildings):
                new_name = safe_name_b(b)
                if new_name != (b.name or ""):
                    if not quiet:
                        log(f"  building id={b.id}: {repr(b.name)[:60]} -> {repr(new_name)[:60]}")
                    if not dry_run:
                        b.name = new_name
                    updated_b += 1
                if not dry_run and (i + 1) % batch_size == 0:
                    db.session.commit()
                    log(f"  commit (buildings, {i + 1} обработано)")
            if not dry_run:
                db.session.commit()
            log(f"  Итого обновлено названий в buildings: {updated_b}")

            # --- [2/4] Санитизация названий в floors ---
            log("[2/4] Санитизация названий в floors...")
            updated_f = 0
            for i, f in enumerate(floors):
                new_name = safe_name_f(f)
                if new_name != (f.name or ""):
                    if not quiet:
                        log(f"  floor id={f.id}: {repr(f.name)[:60]} -> {repr(new_name)[:60]}")
                    if not dry_run:
                        f.name = new_name
                    updated_f += 1
                if not dry_run and (i + 1) % batch_size == 0:
                    db.session.commit()
                    log(f"  commit (floors, {i + 1} обработано)")
            if not dry_run:
                db.session.commit()
            log(f"  Итого обновлено названий в floors: {updated_f}")

            # Перечитываем для дедупликации (после санитизации ключи могли измениться)
            if not dry_run:
                db.session.expire_all()  # сброс кэша после коммита
                buildings = Building.query.order_by(Building.id).all()
                floors = Floor.query.order_by(Floor.id).all()

            log("[3/4] Дедупликация buildings (по project_id + нормализованное имя), оставляем запись с min(id)...")
            building_groups = defaultdict(list)
            for b in buildings:
                name_for_key = safe_name_b(b) if dry_run else (b.name or f"Корпус {b.id}")
                key = (b.project_id, normalized_key_for_dedup(name_for_key))
                building_groups[key].append(b.id)
            dup_building_ids = []
            building_kept_for_dup = {}
            for key, ids in building_groups.items():
                if len(ids) > 1:
                    ids.sort()
                    kept = ids[0]
                    for dup_id in ids[1:]:
                        dup_building_ids.append(dup_id)
                        building_kept_for_dup[dup_id] = kept
                    log(f"  project_id={key[0]}, name_key={key[1][:40]!r}: оставляем id={kept}, удаляем {ids[1:]}")
            for dup_id in dup_building_ids:
                kept_id = building_kept_for_dup[dup_id]
                if dry_run:
                    log(f"  [DRY-RUN] Был бы удалён дубликат building id={dup_id}, ссылки переназначены на id={kept_id}")
                else:
                    Floor.query.filter(Floor.building_id == dup_id).update({Floor.building_id: kept_id}, synchronize_session=False)
                    Document.query.filter(Document.building_id == dup_id).update({Document.building_id: kept_id}, synchronize_session=False)
                    MaterialMovement.query.filter(MaterialMovement.building_id == dup_id).update({MaterialMovement.building_id: kept_id}, synchronize_session=False)
                    ScheduleWork.query.filter(ScheduleWork.building_id == dup_id).update({ScheduleWork.building_id: kept_id}, synchronize_session=False)
                    BuildingParticipant.query.filter(BuildingParticipant.building_id == dup_id).update({BuildingParticipant.building_id: kept_id}, synchronize_session=False)
                    Building.query.filter(Building.id == dup_id).delete()
                    log(f"  Удалён дубликат building id={dup_id}, ссылки переназначены на id={kept_id}")
            if not dry_run:
                db.session.commit()
            log(f"  Удалено дубликатов buildings: {len(dup_building_ids)}")

            log("[4/4] Дедупликация floors (по building_id + нормализованное имя), оставляем запись с min(id)...")
            if not dry_run:
                floors = Floor.query.order_by(Floor.id).all()
            floor_groups = defaultdict(list)
            for f in floors:
                name_for_key = safe_name_f(f) if dry_run else (f.name or f"Этаж {f.id}")
                key = (f.building_id, normalized_key_for_dedup(name_for_key))
                floor_groups[key].append(f.id)
            dup_floor_ids = []
            floor_kept_for_dup = {}
            for key, ids in floor_groups.items():
                if len(ids) > 1:
                    ids.sort()
                    kept = ids[0]
                    for dup_id in ids[1:]:
                        dup_floor_ids.append(dup_id)
                        floor_kept_for_dup[dup_id] = kept
                    log(f"  building_id={key[0]}, name_key={key[1][:40]!r}: оставляем id={kept}, удаляем {ids[1:]}")
            for dup_id in dup_floor_ids:
                kept_id = floor_kept_for_dup[dup_id]
                if dry_run:
                    log(f"  [DRY-RUN] Был бы удалён дубликат floor id={dup_id}, ссылки переназначены на id={kept_id}")
                else:
                    Document.query.filter(Document.floor_id == dup_id).update({Document.floor_id: kept_id}, synchronize_session=False)
                    Plan.query.filter(Plan.floor_id == dup_id).update({Plan.floor_id: kept_id}, synchronize_session=False)
                    Mark.query.filter(Mark.floor_id == dup_id).update({Mark.floor_id: kept_id}, synchronize_session=False)
                    FloorMaterial.query.filter(FloorMaterial.floor_id == dup_id).update({FloorMaterial.floor_id: kept_id}, synchronize_session=False)
                    FloorEquipment.query.filter(FloorEquipment.floor_id == dup_id).update({FloorEquipment.floor_id: kept_id}, synchronize_session=False)
                    FloorQuantity.query.filter(FloorQuantity.floor_id == dup_id).update({FloorQuantity.floor_id: kept_id}, synchronize_session=False)
                    MaterialMovement.query.filter(MaterialMovement.floor_id == dup_id).update({MaterialMovement.floor_id: kept_id}, synchronize_session=False)
                    ScheduleWork.query.filter(ScheduleWork.floor_id == dup_id).update({ScheduleWork.floor_id: kept_id}, synchronize_session=False)
                    Task.query.filter(Task.floor_id == dup_id).update({Task.floor_id: kept_id}, synchronize_session=False)
                    Floor.query.filter(Floor.id == dup_id).delete()
                    log(f"  Удалён дубликат floor id={dup_id}, ссылки переназначены на id={kept_id}")
            if not dry_run:
                db.session.commit()
            log(f"  Удалено дубликатов floors: {len(dup_floor_ids)}")

            # --- Итоговая сводка ---
            log("--- Итог ---")
            log(f"Buildings: обработано {total_b}, санитизировано названий {updated_b}, объединено/удалено дубликатов {len(dup_building_ids)}.")
            log(f"Floors: обработано {total_f}, санитизировано названий {updated_f}, объединено/удалено дубликатов {len(dup_floor_ids)}.")
            if dry_run:
                log("[DRY-RUN] Завершено без изменений в БД.")
            else:
                log("Готово. Изменения сохранены в БД.")

            # --- Валидация после санитизации: предупреждение о возможном «мусоре» в названиях ---
            def _is_valid_display_name(name):
                if not name or len(name.strip()) < 3:
                    return False
                s = name.strip()
                if s.startswith("Корпус ") or s.startswith("Этаж "):
                    return True
                return any(c.isalpha() for c in s)

            if not dry_run:
                log("--- Проверка названий ---")
                bad_b = [(b.id, b.name) for b in Building.query.all() if not _is_valid_display_name(b.name)]
                bad_f = [(f.id, f.name) for f in Floor.query.all() if not _is_valid_display_name(f.name)]
                if bad_b:
                    log(f"  Внимание: у {len(bad_b)} зданий название короче 3 символов или без букв/известного префикса: {bad_b[:10]}{'...' if len(bad_b) > 10 else ''}")
                if bad_f:
                    log(f"  Внимание: у {len(bad_f)} этажей название короче 3 символов или без букв/известного префикса: {bad_f[:10]}{'...' if len(bad_f) > 10 else ''}")
                if not bad_b and not bad_f:
                    log("  Все названия buildings и floors проходят проверку (длина >= 3, есть буквы или префикс «Корпус»/«Этаж»).")

            log(f"Лог сохранён: {log_path}")


if __name__ == "__main__":
    args = _parse_args()
    if args.batch_size < 1:
        print("Ошибка: --batch-size должен быть >= 1.", file=sys.stderr)
        sys.exit(1)
    from app import create_app
    app = create_app()
    run(
        app,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        skip_confirm=args.yes,
        restore_prefixes=args.restore_prefixes,
        quiet=args.quiet,
    )
