from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, ValidationError


class MangaForm(FlaskForm):
    title = StringField('Título principal', validators=[DataRequired(), Length(max=255)])
    alternative_titles = StringField('Títulos alternativos', validators=[Optional(), Length(max=500)])
    anilist_id = IntegerField('ID AniList', validators=[Optional(), NumberRange(min=1, max=999999999)])
    synopsis = TextAreaField('Sinopse', validators=[Optional()])
    cover_image = StringField('URL da Capa', validators=[Optional(), Length(max=500)])
    banner_image = StringField('URL do Banner', validators=[Optional(), Length(max=500)])
    banner_file = FileField(
        'Upload de Banner Local',
        validators=[
            Optional(),
            FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Apenas imagens JPG, PNG ou WEBP são permitidas.')
        ]
    )
    banner_position = SelectField(
        'Enquadramento Vertical',
        choices=[
            ('top', 'Topo (Top)'),
            ('center', 'Centro (Center)'),
            ('bottom', 'Base (Bottom)'),
        ],
        default='center',
        validators=[Optional()]
    )
    genres = StringField('Gêneros (separados por vírgula)', validators=[Optional(), Length(max=255)])
    author = StringField('Autor(es)', validators=[Optional(), Length(max=255)])
    publication_status = SelectField(
        'Status de publicação',
        choices=[
            ('RELEASING', 'Em publicação (Releasing)'),
            ('FINISHED', 'Finalizado (Finished)'),
            ('NOT_YET_RELEASED', 'Não lançado (Not yet released)'),
            ('CANCELLED', 'Cancelado (Cancelled)'),
            ('HIATUS', 'Em hiato (Hiatus)'),
        ],
        default='RELEASING',
    )
    anilist_chapters = IntegerField('Capítulos (AniList)', validators=[Optional(), NumberRange(min=0)])
    start_date = StringField('Data de início', validators=[Optional(), Length(max=50)])
    end_date = StringField('Data de término', validators=[Optional(), Length(max=50)])
    is_visible = BooleanField('Visível no catálogo', default=True)
    is_featured = BooleanField('Destacar na página inicial', default=False)
    submit = SubmitField('Salvar mangá')


class ChapterPDFUploadForm(FlaskForm):
    manga_id = SelectField('Mangá', coerce=int, validators=[Optional()])
    anilist_id = IntegerField('ID AniList', validators=[DataRequired(), NumberRange(min=1, max=999999999)])
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
    pdf_file = FileField(
        'Arquivo PDF',
        validators=[
            FileRequired('Selecione um arquivo PDF para upload.'),
            FileAllowed(['pdf'], 'Apenas arquivos com extensão .pdf são aceitos.'),
        ],
    )
    status = SelectField(
        'Status do capítulo',
        choices=[('published', 'Publicado'), ('draft', 'Rascunho')],
        default='published',
    )
    is_available = BooleanField('Disponível para leitura pública', default=True)
    authorization_confirmed = BooleanField(
        'Confirmo que possuo autorização ou direitos para disponibilizar este arquivo PDF.',
        validators=[DataRequired('Você deve confirmar a autorização do conteúdo.')],
    )
    submit = SubmitField('Fazer Upload do PDF')

    def validate_chapter_number(self, field):
        if field.data is not None and not Decimal(str(field.data)).is_finite():
            raise ValidationError('Informe um número de capítulo válido.')


class ChapterPDFEditForm(FlaskForm):
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
    pdf_file = FileField(
        'Substituir PDF (opcional)',
        validators=[
            Optional(),
            FileAllowed(['pdf'], 'Apenas arquivos com extensão .pdf são aceitos.'),
        ],
    )
    status = SelectField(
        'Status do capítulo',
        choices=[('published', 'Publicado'), ('draft', 'Rascunho')],
        default='published',
    )
    is_available = BooleanField('Disponível para leitura pública')
    submit = SubmitField('Salvar alterações')


class UserAdminEditForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=180)])
    role = SelectField(
        'Papel / Nível de acesso',
        choices=[('user', 'Usuário comum'), ('admin', 'Administrador')],
        default='user',
    )
    is_active = BooleanField('Conta ativa (desmarque para bloquear)', default=True)
    new_password = PasswordField('Nova senha (deixe em branco para não alterar)', validators=[Optional(), Length(min=6, max=128)])
    submit = SubmitField('Salvar usuário')


class CommentForm(FlaskForm):
    content = TextAreaField(
        'Deixe seu comentário',
        validators=[DataRequired('O comentário não pode ser vazio.'), Length(min=1, max=2000)],
    )
    submit = SubmitField('Publicar comentário')


class CommentReportForm(FlaskForm):
    reason = StringField(
        'Motivo da denúncia',
        validators=[DataRequired('Informe o motivo da denúncia.'), Length(min=3, max=255)],
    )
    submit = SubmitField('Enviar denúncia')
