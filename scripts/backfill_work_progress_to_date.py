#!/usr/bin/env python3
"""
Обратная заливка work_progress: для работ, у которых ещё нет записей по дням,
создаётся одна запись на указанную дату с полным плановым объёмом.
Так модалка «Ежедневное выполнение» начинает работать: исходный объём учитывается одним днём,
дальше можно добавлять/редактировать по факту по дням.

Требование: таблица work_progress должна существовать (docs/sql/works_and_progress_create.sql).

Использование:
  python scripts/backfill_work_progress_to_date.py --date YYYY-MM-DD
  python scripts/backfill_work_progress_to_date.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date


def main():
    parser = argparse.ArgumentParser(
        description="Залить существующий объём работ одним днём в work_progress на выбранную дату"
    )
    parser.add_argument("--date", required=True, help="Дата одной записи (YYYY-MM-DD)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Только показать, что будет сделано"
    )
    args = parser.parse_args()

    try:
        target = date.fromisoformat(args.date)
    except ValueError:
        print("Ошибка: дата должна быть в формате YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import create_app
    from app.extensions import db
    from app.models import Work, WorkProgress

    app = create_app()
    with app.app_context():
        works = Work.query.filter(Work.volume != None, Work.volume > 0).all()
        added = 0
        skipped = 0
        for w in works:
            base = float(w.initial_executed or 0)
            # Если по работе уже есть хотя бы одна запись в work_progress — пропускаем
            has_progress = bool(w.progress)
            if base > 0 or has_progress:
                skipped += 1
                continue
            vol = float(w.volume or 0)
            if vol <= 0:
                skipped += 1
                continue
            if args.dry_run:
                print(
                    f'  [dry-run] work_id={w.id} "{w.name}": добавить запись {target} с объёмом {vol}'
                )
                added += 1
                continue
            db.session.add(WorkProgress(work_id=w.id, date=target, daily_execution=vol))
            added += 1
        if not args.dry_run and added:
            db.session.commit()
        print(
            f"Обработано: добавлено/обновлено {added}, пропущено (уже есть выполнение) {skipped}."
        )
        if args.dry_run and added:
            print("Запустите без --dry-run, чтобы записать в БД.")


if __name__ == "__main__":
    main()
