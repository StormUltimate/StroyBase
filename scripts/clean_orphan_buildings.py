#!/usr/bin/env python
# scripts/clean_orphan_buildings.py — StroyBase
# Поиск и очистка корпусов-сирот: building.project_id указывает на несуществующий проект.
# Запуск: python scripts/clean_orphan_buildings.py [--dry-run] [--delete] [--reassign-to-project N]
#
# Политика: миграции не используются. Скрипт только данные (UPDATE/DELETE). Рекомендуется снимок БД.

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _parse_args():
    p = argparse.ArgumentParser(
        description="Найти корпуса-сироты (project_id нет в projects) и удалить или переназначить."
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Только вывести список, без изменений в БД.",
    )
    p.add_argument(
        "--delete",
        action="store_true",
        help="Удалить корпуса-сироты (каскад: этажи, связи, затем корпус).",
    )
    p.add_argument(
        "--reassign-to-project",
        type=int,
        metavar="ID",
        help="Переназначить всех сирот на проект с указанным id.",
    )
    return p.parse_args()


def run(app, dry_run=False, delete=False, reassign_project_id=None):
    from sqlalchemy import text
    from app.extensions import db
    from app.models import (
        Project,
        Building,
        Floor,
        Document,
        MaterialMovement,
        BuildingParticipant,
    )

    with app.app_context():
        project_ids = {p.id for p in Project.query.all()}
        if not project_ids:
            orphans = Building.query.order_by(Building.id).all()
        else:
            orphans = (
                Building.query.filter(~Building.project_id.in_(project_ids))
                .order_by(Building.id)
                .all()
            )
        if not orphans:
            print(
                "Корпусов-сирот не найдено (все building.project_id существуют в projects)."
            )
            return
        print(f"Найдено корпусов-сирот: {len(orphans)}")
        for b in orphans:
            floors = Floor.query.filter_by(building_id=b.id).count()
            print(
                f"  id={b.id}, project_id={b.project_id} (нет в БД), name={b.name!r}, этажей={floors}"
            )
        if dry_run:
            print("[DRY-RUN] Завершено без изменений.")
            return
        if delete:
            for b in orphans:
                _delete_building_cascade(
                    db,
                    Building,
                    Floor,
                    Document,
                    MaterialMovement,
                    BuildingParticipant,
                    b.id,
                )
            db.session.commit()
            print(f"Удалено корпусов-сирот: {len(orphans)}")
            return
        if reassign_project_id is not None:
            target = Project.query.get(reassign_project_id)
            if not target:
                print(
                    f"Ошибка: проект id={reassign_project_id} не найден.",
                    file=sys.stderr,
                )
                sys.exit(1)
            for b in orphans:
                b.project_id = reassign_project_id
            db.session.commit()
            print(
                f"Переназначено корпусов на проект id={reassign_project_id} («{target.name}»): {len(orphans)}"
            )
            return
        print("Укажите --delete или --reassign-to-project ID для выполнения действий.")


def _delete_building_cascade(
    db, Building, Floor, Document, MaterialMovement, BuildingParticipant, building_id
):
    from sqlalchemy import text

    Document.query.filter(Document.building_id == building_id).update(
        {Document.building_id: None}, synchronize_session=False
    )
    MaterialMovement.query.filter(MaterialMovement.building_id == building_id).update(
        {MaterialMovement.building_id: None}, synchronize_session=False
    )
    try:
        db.session.execute(
            text(
                "UPDATE schedule_works SET building_id = NULL WHERE building_id = :bid"
            ),
            {"bid": building_id},
        )
    except Exception:
        pass
    for floor in Floor.query.filter(Floor.building_id == building_id).all():
        db.session.delete(floor)
    BuildingParticipant.query.filter(
        BuildingParticipant.building_id == building_id
    ).delete(synchronize_session=False)
    db.session.execute(
        text("DELETE FROM buildings WHERE id = :id"), {"id": building_id}
    )


if __name__ == "__main__":
    args = _parse_args()
    if args.delete and args.reassign_to_project is not None:
        print(
            "Укажите только один из вариантов: --delete или --reassign-to-project.",
            file=sys.stderr,
        )
        sys.exit(1)
    from app import create_app

    app = create_app()
    run(
        app,
        dry_run=args.dry_run,
        delete=args.delete,
        reassign_project_id=args.reassign_to_project,
    )
