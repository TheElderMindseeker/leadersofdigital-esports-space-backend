from datetime import datetime, time
import functools
import os
from enum import Enum, auto

from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime, ForeignKey
from flask import Flask, current_app, g, request, abort
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship

from vk import is_valid

app = Flask(__name__)

app.config['VK_SECRET_KEY'] = os.environ['VK_SECRET_KEY']
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['ESPORTS_DATABASE_URI']

CORS(app)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    vk_id = Column(Integer, unique=True, nullable=False)


class DisciplineType(Enum):
    solo = auto()
    team = auto()


class TournamentType(Enum):
    play_off = 'play-off'
    group = 'group'


class TournamentState(Enum):
    planned = auto()
    check_in = auto()
    in_progress = auto()
    finished = auto()


class Tournament(db.Model):
    __tablename__ = 'tournaments'

    id = Column(Integer, primary_key=True)
    title = Column(String(1024), nullable=False)
    discipline = Column(String(256), nullable=False)
    discipline_type = Column(SQLEnum(DisciplineType), nullable=False)
    type = Column(SQLEnum(TournamentType), nullable=False)
    start_time = Column(DateTime, nullable=False)
    state = Column(SQLEnum(TournamentState), nullable=False)

    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    creator = relationship('User')


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


@app.route('/tournaments', methods=['GET', 'POST'])
@with_user
def search_tournaments():
    if request.method == 'GET':
        discipline = request.args.get('discipline', '')
        tournament_type = request.args.get('type')
        lower_date = request.args.get('lower_date')
        upper_date = request.args.get('upper_date')
        lower_time = request.args.get('lower_time')
        upper_time = request.args.get('upper_time')

        discipline_filter = f'%{discipline}%'
        query = Tournament.query.filter(Tournament.discipline.ilike(discipline_filter))
        if tournament_type is not None:
            query = query.filter(Tournament.type == TournamentType[tournament_type])

        tournaments = query.all()

        if lower_date is not None:
            tournaments = [tour for tour in tournaments if tour.start_time >= datetime.fromisoformat(lower_date)]
        if upper_date is not None:
            tournaments = [tour for tour in tournaments if tour.start_time <= datetime.fromisoformat(upper_date)]
        if lower_time is not None:
            tournaments = [tour for tour in tournaments if tour.start_time.time() >= time.fromisoformat(lower_time)]
        if upper_time is not None:
            tournaments = [tour for tour in tournaments if tour.start_time.time() <= time.fromisoformat(upper_time)]

        return [
            {
                'id': tour.id,
                'title': tour.title,
                'discipline': tour.discipline,
                'discipline_type': tour.discipline_type.name,
                'type': tour.type.name,
                'start_time': tour.start_time.isoformat(),
                'state': tour.state.name,
                'creator': tour.creator.vk_id,
            }
            for tour in tournaments
        ]

    new_tournament = Tournament(
        title=request.json['title'],
        discipline=request.json['discipline'],
        discipline_type=DisciplineType[request.json['discipline_type']],
        type=TournamentType[request.json['type']],
        start_time=datetime.fromisoformat(request.json['start_time']),
        state='planned',
        user_id=g['user'].id,
    )
    db.session.add(new_tournament)
    db.session.commit()
