from flask import Blueprint, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from datetime import datetime
from app.models import User
from .forms import LoginForm
from app.extensions import db

from . import bp


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Чистая отдельная страница входа StroyBase"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(login=form.login.data).first()
        if user and user.check_password(form.password.data):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            flash("Добро пожаловать в StroyBase!", "success")
            return redirect(url_for("main.index"))
        flash("Неверный логин или пароль", "danger")
    return render_template("auth/login.html", form=form)


@bp.route("/logout")
def logout():
    """Выход из системы — полная очистка"""
    logout_user()
    session.clear()
    flash("Вы успешно вышли из системы", "info")
    return redirect(url_for("auth.login"))
