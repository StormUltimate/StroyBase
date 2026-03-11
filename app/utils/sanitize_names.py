# app/utils/sanitize_names.py — StroyBase
# Единая логика санитизации названий (здания, этажи, отображение в API).
# Используется в material_movement API и в скрипте очистки БД.
import re

# Допустимые символы: кириллица, латиница, цифры, пробелы, -.,()/№
_RE_ALLOWED = re.compile(r"[а-яА-ЯёЁa-zA-Z0-9\s\-.,()\/№]+", re.UNICODE)
_MIN_LENGTH = 2
_JUNK_ONLY_DIGITS = re.compile(r"^[\d\s\-.,()\/]+$")

# Шаблоны сломанных префиксов (после санитизации): «Строение» / «Этаж» в неправильной кодировке или латиницей.
# Результат санитизации «Љ®аЇгб 6» → «а гб 6» (кириллица а, г, б проходят regex).
_RE_BROKEN_KORPUS = re.compile(
    r"^(?:а\s*г\s*б|а\s*гб|jb\s*@?\s*air|korpus|корпус|stroenie|строение)\s*(\d*)\s*$",
    re.UNICODE,
)
_RE_BROKEN_ETAZH = re.compile(
    r"^(?:т\s*аж|аж|этаж|etazh)\s*(\d*)\s*$", re.IGNORECASE | re.UNICODE
)


def normalize_name(s, fallback=""):
    """
    Санитизация названия для сохранения в БД и отображения.
    Удаляются управляющие символы и всё, кроме букв (кириллица/латиница), цифр, пробелов, -.,()/№.
    Если результат пустой или только цифры/пунктуация — возвращается fallback.
    """
    if s is None:
        return fallback
    try:
        s = str(s)
    except (UnicodeDecodeError, TypeError):
        return fallback
    s = "".join(c for c in s if ord(c) >= 32 or c in "\t\n\r")
    s = s.strip()
    if not s:
        return fallback
    parts = _RE_ALLOWED.findall(s)
    out = " ".join(parts).strip()
    out = re.sub(r"\s+", " ", out)
    if len(out) < _MIN_LENGTH:
        return fallback
    if _JUNK_ONLY_DIGITS.match(out):
        return fallback
    if not any(c.isalpha() for c in out):
        return fallback
    return out


def restore_known_patterns(cleaned_name, prefix_type, entity_id=None):
    """
    Восстановление известных сломанных префиксов «Строение N» / «Этаж N» после санитизации.
    cleaned_name — уже результат normalize_name (или строка после удаления мусора).
    prefix_type — 'building' или 'floor'.
    entity_id — id записи (building.id / floor.id), подставляется, если в строке нет числа.
    Возвращает восстановленную строку (например, «Строение 6») или None, если шаблон не подошёл.
    """
    if not cleaned_name or not isinstance(cleaned_name, str):
        return None
    s = cleaned_name.strip()
    if not s:
        return None
    num = None
    if prefix_type == "building":
        m = _RE_BROKEN_KORPUS.match(s)
        if m:
            num = m.group(1).strip()
            n = int(num) if num else (entity_id if entity_id is not None else None)
            return f"Строение {n}" if n is not None else "Строение"
    elif prefix_type == "floor":
        m = _RE_BROKEN_ETAZH.match(s)
        if m:
            num = m.group(1).strip()
            n = int(num) if num else (entity_id if entity_id is not None else None)
            return f"Этаж {n}" if n is not None else "Этаж"
    return None


def normalized_key_for_dedup(name):
    """Ключ для дедупликации: нормализованное имя в нижнем регистре."""
    n = normalize_name(name, "")
    return n.lower().strip() if n else ""
