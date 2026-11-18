from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired
from wtforms import BooleanField, DecimalField, IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


class ChapterUploadForm(FlaskForm):
    manga_id = IntegerField('Mangá', validators=[Optional()])
    anilist_id = IntegerField(
        'AniList ID',
        validators=[Optional(), NumberRange(min=1, max=999999999)],
    )
    chapter_number = DecimalField(
        'Número do capítulo',
        places=3,
        validators=[DataRequired(), NumberRange(min=0, max=9999999.999)],
    )
    chapter_title = StringField('Título do capítulo', validators=[Optional(), Length(max=255)])
    volume_number = DecimalField(
        'Volume',
        places=3,
        validators=[Optional(), NumberRange(min=0, max=9999999.999)],
    )
    archive = FileField('Arquivo ZIP/CBZ', validators=[FileRequired()])
    authorization_confirmed = BooleanField(
        'Confirmo que tenho autorização para armazenar e disponibilizar este conteúdo.',
        validators=[DataRequired()],
    )
    submit = SubmitField('Importar capítulo')

    def validate_anilist_id(self, field):
        if not field.data and not self.manga_id.data:
            raise ValidationError('Selecione uma obra cadastrada no catálogo.')

    def validate_archive(self, field):
        filename = (field.data.filename or '').lower()
        if not filename.endswith(('.zip', '.cbz')):
            raise ValidationError('Selecione um arquivo .zip ou .cbz.')

    def validate_chapter_number(self, field):
        if field.data is not None and not Decimal(str(field.data)).is_finite():
            raise ValidationError('Informe um número de capítulo válido.')


class ChapterMetadataForm(FlaskForm):
    chapter_title = StringField('Título do capítulo', validators=[Optional(), Length(max=255)])
    volume_number = DecimalField(
        'Volume',
        places=3,
        validators=[Optional(), NumberRange(min=0, max=9999999.999)],
    )
    is_available = BooleanField('Capítulo disponível para leitura')
    submit = SubmitField('Salvar alterações')

    def validate_volume_number(self, field):
        if field.data is not None and not Decimal(str(field.data)).is_finite():
            raise ValidationError('Informe um número de volume válido.')
