from flask_wtf import FlaskForm
from wtforms import FloatField, HiddenField, IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional


class LibraryEntryForm(FlaskForm):
    anilist_id = HiddenField('AniList ID', validators=[DataRequired()])
    manga_title = StringField('Title', validators=[DataRequired()])
    cover_image = StringField('Cover image')
    reading_status = SelectField(
        'Reading status',
        choices=[
            ('Want to Read', 'Want to Read'),
            ('Reading', 'Reading'),
            ('Completed', 'Completed'),
            ('Paused', 'Paused'),
            ('Dropped', 'Dropped'),
        ],
        default='Want to Read',
    )
    current_chapter = IntegerField('Current chapter', default=0)
    personal_rating = FloatField('Your rating', validators=[Optional(), NumberRange(min=0, max=10)])
    submit = SubmitField('Save')
