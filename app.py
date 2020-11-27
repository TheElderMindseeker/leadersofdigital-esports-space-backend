import functools
import os

from sqlalchemy import Column, Integer, String
from flask import Flask, current_app, g, request, abort
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

from vk import is_valid

app = Flask(__name__)

app.config['VK_SECRET_KEY'] = os.environ['VK_SECRET_KEY']

CORS(app)
db = SQLAlchemy(app)


class User(db.Model):
    id = Column(Integer, primary_key=True)
    vk_id = Column(Integer, unique=True, nullable=False)


def with_user(callee):
    @functools.wraps(callee)
    def wrapper(*args, **kwargs):
        if not is_valid(query=request.args, secret=current_app.config['VK_SECRET_KEY']):
            abort(403)
        vk_id = int(request.args['vk_user_id'])
        user = User.query.filter_by(vk_id=vk_id).one_or_none()
        if user is None:
            user = User(vk_id=vk_id)
            db.session.save(user)
            db.session.commit()
        g['user'] = user
        return callee(*args, **kwargs)
    return wrapper
