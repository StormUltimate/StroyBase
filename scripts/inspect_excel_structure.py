#!/usr/bin/env python3
"""
Выводит структуру Excel-файла: имена листов, первая строка (заголовки), типы колонок и пример данных.
Запуск: python scripts/inspect_excel_structure.py work1.xlsx
После запуска можно подстроить import_works_from_excel.py под реальные колонки.
"""

import sys
import os
from datetime import datetime, date


def excel_serial_to_date(serial):
    if serial is None:
        return None
    try:
        if isinstance(serial, (int, float)):
            return date(1899, 12, 30) + __import__("datetime").timedelta(
                days=int(serial)
            )
        if isinstance(serial, datetime):
            return serial.date()
        if isinstance(serial, date):
            return serial
        return date(1899, 12, 30) + __import__("datetime").timedelta(
            days=int(float(serial))
        )
    except (ValueError, TypeError):
        return None


def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/inspect_excel_structure.py work1.xlsx")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"Файл не найден: {path}")
        sys.exit(1)
    try:
        import openpyxl
    except ImportError:
        print("Установите openpyxl: pip install openpyxl")
        sys.exit(1)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    print("=== Листы ===")
    print(wb.sheetnames)
    for name in wb.sheetnames:
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))[:35]
        if not rows:
            print("\n--- %s: пустой ---" % name)
            continue
        ncols = len(rows[0]) if rows[0] else 0
        print("\n--- %s (до 20 строк, колонок: %s) ---" % (name, ncols))
        # Найти первую строку с несколькими непустыми ячейками (заголовки)
        header_row_idx = None
        for ri, row in enumerate(rows):
            non_empty = sum(1 for v in row if v is not None and str(v).strip())
            if non_empty >= 3:
                header_row_idx = ri
                break
        headers = rows[header_row_idx] if header_row_idx is not None else rows[0]
        hdr_row = header_row_idx if header_row_idx is not None else 0
        print("Строка заголовков (индекс %d):" % hdr_row)
        for i, h in enumerate(headers):
            if h is None or (isinstance(h, str) and not h.strip()):
                continue
            if isinstance(h, (int, float)) and 40000 <= float(h) <= 50000:
                d = excel_serial_to_date(h)
                print("  [%d] %s (Excel date) -> %s" % (i, h, d))
            else:
                print(
                    "  [%d] %r (%s)"
                    % (
                        i,
                        h if len(repr(h)) < 55 else repr(h)[:52] + "...",
                        type(h).__name__,
                    )
                )
        # Пример данных
        data_start = hdr_row + 1
        if data_start < len(rows):
            print("Пример данных (строка %d):" % data_start)
            row2 = rows[data_start]
            for i in range(min(15, len(row2))):
                v = row2[i] if i < len(row2) else None
                if v is not None:
                    print("  [%d] %r" % (i, v))
        # Если лист корпуса и в первых 10 колонках заголовков нет текста/чисел — сырые значения
        is_building = "корпус" in name.lower()
        has_any_header = (
            any(
                headers[i] is not None and str(headers[i]).strip()
                for i in range(min(10, len(headers)))
            )
            if headers
            else False
        )
        if is_building and not has_any_header:
            print("(Лист корпуса: строки 0-18, колонки 0-18):")
            for ri, row in enumerate(rows[:19]):
                if not row:
                    continue
                part = []
                for i in range(min(19, len(row))):
                    v = row[i]
                    if v is None:
                        part.append("-")
                    elif isinstance(v, (datetime, date)):
                        part.append(str(v)[:10])
                    elif isinstance(v, (int, float)):
                        part.append(str(v)[:8])
                    else:
                        part.append(repr(v)[:14].strip("'"))
                print("  row%d: %s" % (ri, part))
    wb.close()
    print("\nГотово.")


if __name__ == "__main__":
    main()
