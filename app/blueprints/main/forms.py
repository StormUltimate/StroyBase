# app/blueprints/main/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired
from wtforms import DateField

class CreateProjectForm(FlaskForm):
    name = StringField('Название площадки', validators=[DataRequired()])
    contract_number = StringField('Номер договора', validators=[DataRequired()])
    address = StringField('Адрес')
    type_construction = SelectField('Тип строительства', choices=[('Капитальный ремонт', 'Капитальный ремонт'), ('Новостройка', 'Новостройка'), ('Реконструкция', 'Реконструкция')])
    submit = SubmitField('Создать')


class ProjectForm(FlaskForm):   # ← лучше переименовать в ProjectForm
    name = StringField('Название объекта', validators=[DataRequired()])
    contract_number = StringField('Номер договора')
    address = StringField('Адрес')
    type_construction = SelectField(
        'Тип строительства',
        choices=[
            ('', '— выберите —'),
            ('Капитальный ремонт', 'Капитальный ремонт'),
            ('Новостройка', 'Новостройка'),
            ('Реконструкция', 'Реконструкция')
        ],
        validators=[DataRequired()]
    )
    start_date = DateField('Дата начала', format='%Y-%m-%d')
    end_date   = DateField('Дата окончания', format='%Y-%m-%d')
    submit = SubmitField('Сохранить')    