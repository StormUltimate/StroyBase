# Path: app/blueprints/equipment/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, DateField, FileField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional

class EquipmentForm(FlaskForm):
    type = StringField('Тип', validators=[DataRequired()])
    serial_number = StringField('Серийный номер', validators=[DataRequired()])
    brand = StringField('Бренд', validators=[Optional()])
    model = StringField('Модель', validators=[Optional()])
    parent_id = SelectField('Родительское оборудование', coerce=int, validators=[Optional()])
    latitude = FloatField('Широта', validators=[Optional()])
    longitude = FloatField('Долгота', validators=[Optional()])
    kind = StringField('Вид', validators=[Optional()])
    power = StringField('Мощность', validators=[Optional()])
    depth = IntegerField('Глубина', validators=[Optional()])
    height = IntegerField('Высота', validators=[Optional()])
    width = IntegerField('Ширина', validators=[Optional()])
    installation_type = SelectField('Тип установки', choices=[('wall', 'На стене'), ('floor', 'На полу')], validators=[Optional()])
    production_year = IntegerField('Год производства', validators=[Optional()])
    service_interval = IntegerField('Интервал обслуживания (месяцы)', validators=[Optional()])
    service_life = IntegerField('Срок службы (годы)', validators=[Optional()])
    service_price = FloatField('Цена обслуживания', validators=[Optional()])
    last_service_date = DateField('Дата последнего обслуживания', validators=[Optional()])
    next_service_date = DateField('Дата следующего обслуживания', validators=[Optional()])
    warranty_start_date = DateField('Дата начала гарантии', validators=[Optional()])
    warranty_end_date = DateField('Дата окончания гарантии', validators=[Optional()])
    warranty_conditions = TextAreaField('Условия гарантии', validators=[Optional()])
    photo_path = FileField('Фото', validators=[Optional()])
    document_path = FileField('Документ', validators=[Optional()])
    submit = SubmitField('Сохранить')

class EquipmentTemplateForm(FlaskForm):
    type = StringField('Тип', validators=[DataRequired()])
    kind = StringField('Вид', validators=[Optional()])
    brand = StringField('Бренд', validators=[Optional()])
    model = StringField('Модель', validators=[Optional()])
    power = StringField('Мощность', validators=[Optional()])
    depth = IntegerField('Глубина', validators=[Optional()])
    height = IntegerField('Высота', validators=[Optional()])
    width = IntegerField('Ширина', validators=[Optional()])
    installation_type = SelectField('Тип установки', choices=[('wall', 'На стене'), ('floor', 'На полу')], validators=[Optional()])
    production_year = IntegerField('Год производства', validators=[Optional()])
    service_interval = IntegerField('Интервал обслуживания (месяцы)', validators=[Optional()])
    service_life = IntegerField('Срок службы (годы)', validators=[Optional()])
    service_price = FloatField('Цена обслуживания', validators=[Optional()])
    photo_path = FileField('Фото', validators=[Optional()])
    document_path = FileField('Документ', validators=[Optional()])
    submit = SubmitField('Сохранить')

class ImportForm(FlaskForm):
    file = FileField('Файл', validators=[DataRequired()])
    submit = SubmitField('Импорт')