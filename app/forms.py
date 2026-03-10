# app/forms.py — StroyBase
# Формы: проекты, корпуса, этажи, материалы, документы. SelectField с пустыми значениями — coerce в None.

from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    SubmitField,
    TextAreaField,
    FloatField,
    SelectField,
    DateField,
    IntegerField,
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange


def _coerce_int_optional(val):
    """Для SelectField с опциональным целым: пустая строка -> None."""
    if val is None or (isinstance(val, str) and not str(val).strip()):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class ProjectForm(FlaskForm):
    name = StringField(
        "Название объекта",
        validators=[DataRequired(message="Введите название объекта"), Length(max=300)],
        render_kw={"placeholder": "Например: ЖК «Красная Горка»"},
    )
    contract_number = StringField(
        "Номер договора",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Например: 123/2025"},
    )
    address = TextAreaField(
        "Адрес объекта",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "Полный адрес стройплощадки"},
    )
    type_construction = StringField(
        "Вид строительства / работ",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Например: Капитальный ремонт, Новое строительство"},
    )
    start_date = DateField(
        "Дата начала работ", validators=[Optional()], format="%Y-%m-%d"
    )
    end_date = DateField(
        "Плановая дата окончания", validators=[Optional()], format="%Y-%m-%d"
    )
    submit = SubmitField("Сохранить")


class MaterialForm(FlaskForm):
    name = StringField(
        "Название материала", validators=[DataRequired(), Length(max=255)]
    )
    brand = StringField("Бренд", validators=[Optional(), Length(max=255)])
    gost = StringField("ГОСТ", validators=[Optional(), Length(max=255)])

    unit = SelectField(
        "Единица измерения",
        choices=[
            ("", "— не выбрано —"),
            ("м", "Метры (м)"),
            ("м²", "Квадратные метры (м²)"),
            ("м³", "Кубические метры (м³)"),
            ("шт", "Штуки (шт)"),
            ("л", "Литры (л)"),
            ("кг", "Килограммы (кг)"),
            ("т", "Тонны (т)"),
            ("пог.м", "Погонные метры (пог.м)"),
            ("упак", "Упаковки (упак)"),
            ("комплект", "Комплекты (комплект)"),
            ("набор", "Наборы (набор)"),
        ],
        validators=[Optional()],
    )

    color = StringField("Цвет", validators=[Optional(), Length(max=100)])
    price_per_unit = FloatField(
        "Цена за единицу", validators=[Optional(), NumberRange(min=0)]
    )

    planned_quantity = FloatField(
        "Плановый объём", validators=[Optional(), NumberRange(min=0)]
    )
    actual_quantity = FloatField(
        "Фактический объём", validators=[Optional(), NumberRange(min=0)]
    )

    status = SelectField(
        "Статус",
        choices=[
            ("", "— не выбрано —"),
            ("Запланировано", "Запланировано"),
            ("Закуплено", "Закуплено"),
            ("На объекте", "На объекте"),
            ("Смонтировано", "Смонтировано"),
            ("Демонтировано", "Демонтировано"),
        ],
        validators=[Optional()],
    )

    purchase_date = DateField(
        "Дата закупки", validators=[Optional()], format="%Y-%m-%d"
    )
    delivery_date = DateField(
        "Дата доставки", validators=[Optional()], format="%Y-%m-%d"
    )
    arrival_date = DateField(
        "Дата прибытия", validators=[Optional()], format="%Y-%m-%d"
    )
    install_date = DateField("Дата монтажа", validators=[Optional()], format="%Y-%m-%d")
    demolition_date = DateField(
        "Дата демонтажа", validators=[Optional()], format="%Y-%m-%d"
    )

    # Изменено: coerce=str + пустое значение как строка
    category_id = SelectField("Категория", coerce=str, validators=[Optional()])

    certificate_document_id = SelectField(
        "Сертификат (документ)", coerce=str, validators=[Optional()]  # ← тоже лучше str
    )

    note = TextAreaField("Заметка", validators=[Optional()])

    submit = SubmitField("Сохранить материал")


class FloorEquipmentForm(FlaskForm):
    """Форма для оборудования этажа с привязкой к паспорту."""

    name = StringField(
        "Наименование",
        validators=[DataRequired(message="Укажите наименование"), Length(max=255)],
        render_kw={"placeholder": "Например: Насос, Кран балка"},
    )
    brand = StringField("Бренд / марка", validators=[Optional(), Length(max=255)])
    passport_document_id = SelectField(
        "Паспорт (документ)", coerce=str, validators=[Optional()]
    )
    note = TextAreaField("Примечание", validators=[Optional()], render_kw={"rows": 2})
    submit = SubmitField("Сохранить")


class FloorQuantityForm(FlaskForm):
    """Форма для площадей и величин этажа (потолок, стены, погонные/куб. метры)."""

    name = StringField(
        "Наименование",
        validators=[DataRequired(message="Укажите наименование"), Length(max=255)],
        render_kw={"placeholder": "Например: Площадь потолка, Плинтус, Шпатлёвка стен"},
    )
    quantity = FloatField(
        "Значение",
        validators=[DataRequired(message="Укажите значение"), NumberRange(min=0)],
        render_kw={"placeholder": "Число"},
    )
    unit = SelectField(
        "Единица измерения",
        choices=[
            ("м²", "м² (квадратные метры)"),
            ("п.м", "п.м (погонные метры)"),
            ("м³", "м³ (кубические метры)"),
            ("шт", "шт (штуки)"),
            ("м", "м (метры)"),
        ],
        validators=[Optional()],
        default="м²",
    )
    note = TextAreaField(
        "Примечание",
        validators=[Optional()],
        render_kw={"rows": 2, "placeholder": "По необходимости"},
    )
    submit = SubmitField("Сохранить")


class MaterialMovementForm(FlaskForm):
    """Форма создания/редактирования записи о движении материала (привязка к объекту + данные движения)."""

    project_id = SelectField(
        "Проект (объект)",
        coerce=_coerce_int_optional,
        validators=[DataRequired(message="Выберите проект")],
    )
    building_id = SelectField(
        "Корпус", coerce=_coerce_int_optional, validators=[Optional()]
    )
    floor_id = SelectField("Этаж", coerce=_coerce_int_optional, validators=[Optional()])
    material_name = StringField(
        "Наименование материала",
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "Например: Кирпич керамический"},
    )
    brand = StringField(
        "Бренд / производитель",
        validators=[Optional(), Length(max=255)],
        render_kw={"placeholder": "Бренд или производитель"},
    )
    quantity = FloatField("Количество", validators=[Optional(), NumberRange(min=0)])
    unit = SelectField(
        "Ед. изм.",
        choices=[
            ("", "— не выбрано —"),
            ("м", "м"),
            ("м²", "м²"),
            ("м³", "м³"),
            ("шт", "шт"),
            ("л", "л"),
            ("кг", "кг"),
            ("т", "т"),
            ("пог.м", "пог.м"),
            ("упак", "упак"),
            ("комплект", "комплект"),
        ],
        validators=[Optional()],
    )
    volume_m3 = FloatField(
        "Объём, м³",
        validators=[Optional(), NumberRange(min=0)],
        render_kw={"placeholder": "0", "step": "0.0001"},
    )
    length_m = FloatField(
        "Длина, м",
        validators=[Optional(), NumberRange(min=0)],
        render_kw={"placeholder": "0", "step": "0.01"},
    )
    weight_kg = FloatField(
        "Вес, кг",
        validators=[Optional(), NumberRange(min=0)],
        render_kw={"placeholder": "0", "step": "0.01"},
    )
    movement_type = SelectField(
        "Тип движения",
        choices=[
            ("", "— не выбрано —"),
            ("Приход", "Приход"),
            ("Расход", "Расход"),
            ("Перемещение", "Перемещение"),
        ],
        validators=[Optional()],
    )
    movement_date = DateField(
        "Дата движения", validators=[Optional()], format="%Y-%m-%d"
    )
    note = TextAreaField(
        "Примечание",
        validators=[Optional()],
        render_kw={"rows": 3, "placeholder": "Комментарий к операции"},
    )
    submit = SubmitField("Сохранить")


class OrderForm(FlaskForm):
    supplier_name = StringField(
        "Поставщик", validators=[DataRequired(), Length(max=255)]
    )

    quantity = FloatField(
        "Количество", validators=[DataRequired(), NumberRange(min=0.0001)]
    )

    price_per_unit = FloatField(
        "Цена за единицу", validators=[DataRequired(), NumberRange(min=0)]
    )

    expected_delivery_date = DateField(
        "Ожидаемая дата доставки", validators=[Optional()], format="%Y-%m-%d"
    )

    status = SelectField(
        "Статус заказа",
        choices=[
            ("Запланировано", "Запланировано"),
            ("Оформлен", "Оформлен"),
            ("Оплачен", "Оплачен"),
            ("Доставлено", "Доставлено"),
            ("Частично", "Частично доставлено"),
            ("Отменён", "Отменён"),
        ],
        default="Запланировано",
    )

    note = TextAreaField("Примечание", validators=[Optional()], render_kw={"rows": 3})

    submit = SubmitField("Создать / Сохранить заказ")


class ScheduleWorkForm(FlaskForm):
    """Форма работы в графике (для уровня проекта/корпуса). Корпус и этаж — опциональны."""

    project_id = IntegerField("Проект (объект)", validators=[Optional()])
    building_id = SelectField(
        "Корпус", coerce=_coerce_int_optional, validators=[Optional()]
    )
    floor_id = SelectField("Этаж", coerce=_coerce_int_optional, validators=[Optional()])
    name = TextAreaField(
        "Название работы", validators=[DataRequired(message="Введите название работы")]
    )
    planned_start = DateField(
        "Плановая дата начала", validators=[Optional()], format="%Y-%m-%d"
    )
    planned_end = DateField(
        "Плановая дата окончания", validators=[Optional()], format="%Y-%m-%d"
    )
    fact_start = DateField(
        "Фактическая дата начала", validators=[Optional()], format="%Y-%m-%d"
    )
    fact_end = DateField(
        "Фактическая дата окончания", validators=[Optional()], format="%Y-%m-%d"
    )
    percent_complete = FloatField(
        "% выполнения", validators=[Optional(), NumberRange(min=0, max=100)]
    )
    status = SelectField(
        "Статус",
        choices=[
            ("", "— не выбрано —"),
            ("Запланировано", "Запланировано"),
            ("В работе", "В работе"),
            ("Завершено", "Завершено"),
            ("Просрочено", "Просрочено"),
        ],
        validators=[Optional()],
    )
    notes = TextAreaField("Примечания", validators=[Optional()])
    submit = SubmitField("Сохранить работу")
