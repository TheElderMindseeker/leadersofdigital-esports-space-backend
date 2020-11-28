from datetime import datetime, time
import functools
import os
from enum import Enum, auto
from uuid import uuid4
from http import HTTPStatus

from sqlalchemy import Column, Integer, String, Enum as SQLEnum, DateTime, ForeignKey
from flask import Flask, current_app, g, request, abort, send_from_directory, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, backref

from vk import is_valid

app = Flask(__name__, static_folder=None)
script_path = os.path.dirname(os.path.abspath(__file__))

app.config['VK_SECRET_KEY'] = os.environ['VK_SECRET_KEY']
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['ESPORTS_DATABASE_URI']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(script_path, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

CORS(app)
db = SQLAlchemy(app)


class DisciplineType(Enum):
    solo = auto()
    team = auto()


class TournamentType(Enum):
    play_off = auto()


class TournamentState(Enum):
    planned = auto()
    check_in = auto()
    in_progress = auto()
    finished = auto()


class TeamState(Enum):
    registered = auto()
    checked_in = auto()
    playing = auto()
    won = auto()
    lost = auto()


class User(db.Model):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    vk_id = Column(Integer, unique=True, nullable=False)
    rating = Column(Integer, nullable=False, default=0)
    coins = Column(Integer, nullable=False, default=0)


class Tournament(db.Model):
    __tablename__ = 'tournaments'

    id = Column(Integer, primary_key=True)
    title = Column(String(1024), nullable=False)
    logo = Column(String(1024))
    discipline = Column(String(256), nullable=False)
    discipline_type = Column(SQLEnum(DisciplineType), nullable=False)
    type = Column(SQLEnum(TournamentType), nullable=False)
    start_time = Column(DateTime, nullable=False)
    state = Column(SQLEnum(TournamentState), nullable=False)

    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    creator = relationship('User')


players = db.Table(  # noqa
    'players',
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True),
)


class Team(db.Model):
    __tablename__ = 'teams'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    tournament_id = Column(Integer, ForeignKey('tournaments.id', nullable=False))
    state = Column(SQLEnum(TeamState), nullable=False, default=TeamState.registered)
    title = Column(String)
    place = Column(Integer)

    captain = relationship('User', backref=backref('c_teams'))
    tournament = relationship('Tournament', backref=backref('participants'))
    players = relationship('User', secondary=players, backref=backref('teams'))


@app.route('/images', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'GET':
        return send_from_directory(app.config['UPLOAD_FOLDER'], request.args['filename'])
    # POST
    image_file = request.files['image']
    name, ext = os.path.splitext(image_file.filename)
    file_name = str(uuid4()) + ext
    image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], file_name))
    return jsonify(filename=file_name)


def with_user(callee):
    @functools.wraps(callee)
    def wrapper(*args, **kwargs):
        if not is_valid(query=request.args, secret=current_app.config['VK_SECRET_KEY']):
            abort(401)
        vk_id = int(request.args['vk_user_id'])
        user = User.query.filter_by(vk_id=vk_id).one_or_none()
        if user is None:
            user = User(vk_id=vk_id)
            db.session.add(user)
            db.session.commit()
        g.user = user
        return callee(*args, **kwargs)
    return wrapper


@app.route('/tournaments', methods=['GET', 'POST'])
@with_user
def manage_tournaments():
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

        return jsonify(tournaments=[
            {
                'id': tour.id,
                'title': tour.title,
                'logo': tour.logo,
                'discipline': tour.discipline,
                'discipline_type': tour.discipline_type.name,
                'type': tour.type.name,
                'start_time': tour.start_time.isoformat(),
                'state': tour.state.name,
                'creator': tour.creator.vk_id,
            }
            for tour in tournaments
        ])
    # POST
    new_tournament = Tournament(
        title=request.json['title'],
        logo=request.json.get('logo'),
        discipline=request.json['discipline'],
        discipline_type=DisciplineType[request.json['discipline_type']],
        type=TournamentType[request.json['type']],
        start_time=datetime.fromisoformat(request.json['start_time']),
        state='planned',
        user_id=g.user.id,
    )
    db.session.add(new_tournament)
    db.session.commit()
    return '', HTTPStatus.CREATED


@app.route('/tournaments/info')
@with_user
def get_info_on_tournament():
    tournament = Tournament.query.get_or_404(request.args['tournament_id'])
    tour_info = {
        'id': tournament.id,
        'title': tournament.title,
        'logo': tournament.logo,
        'discipline': tournament.discipline,
        'discipline_type': tournament.discipline_type.name,
        'start_time': tournament.start_time.isoformat(),
        'state': tournament.state.name,
    }
    if tournament.discipline_type == DisciplineType.solo:
        participants = [team.captain.vk_id for team in tournament.participants]
    else:
        participants = [
            {
                'title': team.title,
                'captain': team.captain.vk_id,
                'players': [
                    player.vk_id for player in team.players
                ]
            }
            for team in tournament.team_participants
        ]
    tour_info['participants'] = participants
    return jsonify(tournament=tour_info)


@app.route('/tournaments/register', methods=['POST'])
@with_user
def sign_up_for_tournament():
    tournament_id = request.json['tournament_id']
    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.state != TournamentState.planned:
        abort(400)

    signed_up = [team.captain.id for team in tournament.participants]
    if tournament.discipline_type == DisciplineType.team:
        for team in tournament.participants:
            signed_up.extend([player.id for player in team.players])
    if g.user.id in signed_up or g.user.id == tournament.creator.id:
        abort(400)

    team_id = request.json.get('team_id')
    if tournament.discipline_type == DisciplineType.solo:
        new_team = Team(user_id=g.user.id, tournament_id=tournament_id)
        db.session.add(new_team)
    elif team_id is not None:
        existing_team = Team.query.filter_by(id=team_id, tournament_id=tournament_id).first_or_404()
        existing_team.players.append(g.user)
    else:
        title = request.json['title']
        new_team = Team(user_id=g.user.id, tournament_id=tournament_id, title=title)
        db.session.add(new_team)
        db.session.commit()
        return jsonify(team_id=new_team.id)

    db.session.commit()
    return '', HTTPStatus.NO_CONTENT


@app.route('/tournaments/check_in', methods=['POST'])
@with_user
def check_in_to_tournament():
    tournament_id = request.json['tournament_id']
    tournament = Tournament.query.get_or_404(tournament_id)
    if tournament.state != TournamentState.check_in:
        abort(400)
    team = Team.query.filter_by(user_id=g.user.id, tournament_id=tournament_id).first_or_404()
    team.state = TeamState.checked_in
    db.session.commit()
    return '', HTTPStatus.NO_CONTENT


@app.route('/tournaments/state', methods=['POST'])
@with_user
def change_tournament_state():
    tournament = Tournament.query.get_or_404(request.json['tournament_id'])
    if tournament.creator.id != g.user.id:
        abort(403)

    if tournament.state == TournamentState.planned:
        tournament.state = TournamentState.check_in
    elif tournament.state == TournamentState.check_in:
        tournament.state = TournamentState.in_progress
        Team.query.filter_by(tournament_id=tournament.id, state=TeamState.registered).delete()
    elif tournament.state == TournamentState.in_progress:
        # TODO: Add winners
        tournament.state = TournamentState.finished

    db.session.commit()
    return '', HTTPStatus.NO_CONTENT
