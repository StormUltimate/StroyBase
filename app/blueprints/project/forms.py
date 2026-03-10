# Path: app/blueprints/clients/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Optional

class ClientForm(FlaskForm):
    full_name = StringField('ФИО', validators=[Optional()])
    phone = StringField('Телефон', validators=[Optional()])
    address = StringField('Адрес', validators=[Optional()])
    representative_name = StringField('Представитель', validators=[Optional()])
    representative_phone = StringField('Телефон представителя', validators=[Optional()])
    role = StringField('Роль', validators=[Optional()])
    email = StringField('Email', validators=[Optional()])
    submit = SubmitField('Сохранить')

class ClientDeleteForm(FlaskForm):
    client_id = IntegerField('ID клиента', validators=[DataRequired()])
    submit = SubmitField('Удалить')