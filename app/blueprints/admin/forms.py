# app/blueprints/admin/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Optional

class UserForm(FlaskForm):
    login = StringField('Логин', validators=[DataRequired(), Length(min=3, max=64)])
    full_name = StringField('ФИО', validators=[DataRequired(), Length(max=120)])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    role = SelectField('Роль', choices=[
        ('viewer', 'Просмотр'),
        ('editor', 'Редактирование'),
        ('pto', 'ПТО'),
        ('foreman', 'Прораб'),
        ('admin', 'Администратор')
    ], default='viewer')
    is_active = BooleanField('Активен', default=True)
    submit = SubmitField('Сохранить')