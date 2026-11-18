import csv
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.chapter import Chapter
from app.models.manga import Manga
from app.models.user import User


class NumberedCanvas(canvas.Canvas):
    """
    Canvas customizado que realiza duas passagens para calcular o total de páginas
    e desenhar rodapé profissional com numeração 'Página X de Y'.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#71717A"))
        page_width, page_height = self._pagesize

        # Linha e rodapé
        self.setStrokeColor(colors.HexColor("#E4E4E7"))
        self.setLineWidth(0.5)
        self.line(36, 32, page_width - 36, 32)

        self.drawString(
            36,
            20,
            "Mangari — Painel Administrativo • Relatório Institucional Gerado pelo Sistema",
        )
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(page_width - 36, 20, page_text)
        self.restoreState()


# -----------------------------------------------------------------------------
# Consultas Filtradas no Banco de Dados
# -----------------------------------------------------------------------------
def get_users_report_data(role=None, status=None, date_start=None, date_end=None):
    query = User.query

    if role in ('admin', 'user'):
        query = query.filter(User.is_admin.is_(role == 'admin'))

    if status == 'active':
        query = query.filter(User.is_active.is_(True))
    elif status == 'blocked':
        query = query.filter(User.is_active.is_(False))

    if date_start:
        try:
            dt_start = datetime.strptime(date_start, '%Y-%m-%d')
            query = query.filter(User.created_at >= dt_start)
        except (ValueError, TypeError):
            pass

    if date_end:
        try:
            dt_end = datetime.strptime(date_end, '%Y-%m-%d')
            dt_end = dt_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(User.created_at <= dt_end)
        except (ValueError, TypeError):
            pass

    return query.order_by(User.id.desc()).all()


def get_mangas_report_data(publication_status=None, visibility=None, is_featured=None, date_start=None, date_end=None):
    query = Manga.query

    if publication_status and publication_status != 'all':
        query = query.filter(Manga.publication_status == publication_status)

    if visibility == 'visible':
        query = query.filter(Manga.is_visible.is_(True))
    elif visibility == 'hidden':
        query = query.filter(Manga.is_visible.is_(False))

    if is_featured == 'yes':
        query = query.filter(Manga.is_featured.is_(True))
    elif is_featured == 'no':
        query = query.filter(Manga.is_featured.is_(False))

    if date_start:
        try:
            dt_start = datetime.strptime(date_start, '%Y-%m-%d')
            query = query.filter(Manga.created_at >= dt_start)
        except (ValueError, TypeError):
            pass

    if date_end:
        try:
            dt_end = datetime.strptime(date_end, '%Y-%m-%d')
            dt_end = dt_end.replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(Manga.created_at <= dt_end)
        except (ValueError, TypeError):
            pass

    return query.order_by(Manga.id.desc()).all()


# -----------------------------------------------------------------------------
# Exportação CSV
# -----------------------------------------------------------------------------
def generate_users_csv(users):
    """
    Gera conteúdo CSV em memória com utf-8-sig (com BOM) e separador ponto e vírgula
    para compatibilidade com Excel no Windows.
    """
    output = io.StringIO()
    # Adiciona o BOM do UTF-8
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    # Cabeçalho (nunca expor senhas/hashes)
    writer.writerow(['ID', 'Nome', 'E-mail', 'Papel', 'Status', 'Data de Cadastro'])

    for u in users:
        created_str = u.created_at.strftime('%d/%m/%Y %H:%M') if u.created_at else 'N/A'
        role_str = 'Administrador' if u.is_admin else 'Usuário'
        status_str = 'Ativo' if u.is_active else 'Bloqueado'
        writer.writerow([u.id, u.name, u.email, role_str, status_str, created_str])

    return output.getvalue().encode('utf-8')


def generate_mangas_csv(mangas):
    """
    Gera conteúdo CSV com o catálogo de mangás filtrado.
    """
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    writer.writerow([
        'ID',
        'Título',
        'Autor',
        'Status de Publicação',
        'Capítulos Locais',
        'Visibilidade',
        'Destaque na Home',
        'Data de Cadastro',
    ])

    status_labels = {
        'RELEASING': 'Em publicação',
        'FINISHED': 'Finalizado',
        'NOT_YET_RELEASED': 'Não lançado',
        'CANCELLED': 'Cancelado',
        'HIATUS': 'Em hiato',
    }

    for m in mangas:
        created_str = m.created_at.strftime('%d/%m/%Y %H:%M') if m.created_at else 'N/A'
        status_pt = status_labels.get(m.publication_status, m.publication_status or 'N/A')
        chapters_count = len(m.chapters) if m.chapters else 0
        vis_str = 'Visível' if m.is_visible else 'Oculto'
        feat_str = 'Sim' if m.is_featured else 'Não'

        writer.writerow([
            m.id,
            m.title,
            m.author or 'N/A',
            status_pt,
            chapters_count,
            vis_str,
            feat_str,
            created_str,
        ])

    return output.getvalue().encode('utf-8')


# -----------------------------------------------------------------------------
# Exportação PDF (ReportLab)
# -----------------------------------------------------------------------------
def _create_header_elements(title_text, filter_items, generated_by_name):
    """Cria o bloco padrão de cabeçalho institucional para o PDF."""
    elements = []

    # Cabeçalho institucional
    brand_style = ParagraphStyle(
        'BrandTitle',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#FF7518'),
    )
    subtitle_style = ParagraphStyle(
        'BrandSubtitle',
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#71717A'),
    )
    title_style = ParagraphStyle(
        'ReportTitle',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#19191F'),
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        'MetaText',
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#3F3F46'),
    )

    header_table_data = [
        [
            Paragraph("<b>MANGARI</b>", brand_style),
            Paragraph(
                f"<b>Data de Emissão:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}<br/>"
                f"<b>Emitido por:</b> {generated_by_name or 'Administrador'}",
                subtitle_style,
            ),
        ]
    ]
    t_header = Table(header_table_data, colWidths=['60%', '40%'])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_header)

    # Linha divisória laranja com espessura
    elements.append(Spacer(1, 4))
    elements.append(HRFlowable(width="100%", thickness=2.5, color=colors.HexColor("#FF7518"), spaceAfter=10))

    # Título do Relatório
    elements.append(Paragraph(title_text, title_style))

    # Caixa com filtros aplicados
    filters_desc = " &nbsp;•&nbsp; ".join(filter_items) if filter_items else "Nenhum filtro aplicado (Todos os registros)"
    filters_html = f"<b>Filtros aplicados:</b> {filters_desc}"
    elements.append(Paragraph(filters_html, meta_style))
    elements.append(Spacer(1, 10))

    return elements


def generate_users_pdf(users, filters_dict, generated_by_name='Administrador'):
    """
    Gera documento PDF formatado com a lista de usuários filtrados.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=45,
    )

    elements = []

    # Monta descrições dos filtros
    filter_items = []
    if filters_dict.get('role') in ('admin', 'user'):
        filter_items.append(f"Papel: {'Administrador' if filters_dict['role'] == 'admin' else 'Usuário Comum'}")
    if filters_dict.get('status') in ('active', 'blocked'):
        filter_items.append(f"Status: {'Ativos' if filters_dict['status'] == 'active' else 'Bloqueados'}")
    if filters_dict.get('date_start'):
        filter_items.append(f"Início: {filters_dict['date_start']}")
    if filters_dict.get('date_end'):
        filter_items.append(f"Término: {filters_dict['date_end']}")

    elements.extend(
        _create_header_elements(
            "RELATÓRIO DE USUÁRIOS CADASTRADOS",
            filter_items,
            generated_by_name,
        )
    )

    # Estilos de células
    th_style = ParagraphStyle(
        'TH',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=1,  # Center
    )
    td_style = ParagraphStyle(
        'TD',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#18181B'),
    )
    td_center = ParagraphStyle(
        'TDCenter',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#18181B'),
        alignment=1,
    )

    # Largura total útil em A4: 595.27 - 72 = 523.27
    col_widths = [35, 115, 160, 65, 55, 93]
    headers = [
        Paragraph("<b>ID</b>", th_style),
        Paragraph("<b>Nome</b>", th_style),
        Paragraph("<b>E-mail</b>", th_style),
        Paragraph("<b>Papel</b>", th_style),
        Paragraph("<b>Status</b>", th_style),
        Paragraph("<b>Cadastro</b>", th_style),
    ]

    table_data = [headers]

    for u in users:
        created_str = u.created_at.strftime('%d/%m/%Y %H:%M') if u.created_at else '-'
        role_label = 'Admin' if u.is_admin else 'Usuário'
        status_label = 'Ativo' if u.is_active else 'Bloqueado'

        table_data.append([
            Paragraph(str(u.id), td_center),
            Paragraph(u.name or '', td_style),
            Paragraph(u.email or '', td_style),
            Paragraph(role_label, td_center),
            Paragraph(status_label, td_center),
            Paragraph(created_str, td_center),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#19191F')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E4E4E7')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)

    # Totalizador no final
    total_style = ParagraphStyle(
        'TotalText',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#19191F'),
        spaceBefore=10,
    )
    elements.append(Paragraph(f"Total de registros listados: {len(users)}", total_style))

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()


def generate_mangas_pdf(mangas, filters_dict, generated_by_name='Administrador'):
    """
    Gera documento PDF formatado em orientação Paisagem (Landscape) para o Catálogo de Mangás.
    """
    buffer = io.BytesIO()
    # A4 em paisagem: 841.89 x 595.27. Largura útil: 841.89 - 72 = 769.89
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=45,
    )

    elements = []

    status_labels = {
        'RELEASING': 'Em publicação',
        'FINISHED': 'Finalizado',
        'NOT_YET_RELEASED': 'Não lançado',
        'CANCELLED': 'Cancelado',
        'HIATUS': 'Em hiato',
    }

    filter_items = []
    if filters_dict.get('publication_status') and filters_dict['publication_status'] != 'all':
        filter_items.append(f"Status: {status_labels.get(filters_dict['publication_status'], filters_dict['publication_status'])}")
    if filters_dict.get('visibility') in ('visible', 'hidden'):
        filter_items.append(f"Visibilidade: {'Visível' if filters_dict['visibility'] == 'visible' else 'Oculto'}")
    if filters_dict.get('is_featured') in ('yes', 'no'):
        filter_items.append(f"Destaque: {'Sim' if filters_dict['is_featured'] == 'yes' else 'Não'}")
    if filters_dict.get('date_start'):
        filter_items.append(f"Início: {filters_dict['date_start']}")
    if filters_dict.get('date_end'):
        filter_items.append(f"Término: {filters_dict['date_end']}")

    elements.extend(
        _create_header_elements(
            "RELATÓRIO DO CATÁLOGO DE MANGÁS",
            filter_items,
            generated_by_name,
        )
    )

    th_style = ParagraphStyle(
        'TH',
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=1,
    )
    td_style = ParagraphStyle(
        'TD',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#18181B'),
    )
    td_center = ParagraphStyle(
        'TDCenter',
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#18181B'),
        alignment=1,
    )

    # Larguras somam 770 pt (exatamente a largura útil de A4 Landscape)
    col_widths = [35, 220, 140, 95, 65, 65, 60, 90]
    headers = [
        Paragraph("<b>ID</b>", th_style),
        Paragraph("<b>Título</b>", th_style),
        Paragraph("<b>Autor</b>", th_style),
        Paragraph("<b>Status</b>", th_style),
        Paragraph("<b>Capítulos</b>", th_style),
        Paragraph("<b>Visível</b>", th_style),
        Paragraph("<b>Destaque</b>", th_style),
        Paragraph("<b>Cadastro</b>", th_style),
    ]

    table_data = [headers]

    for m in mangas:
        created_str = m.created_at.strftime('%d/%m/%Y %H:%M') if m.created_at else '-'
        st_pt = status_labels.get(m.publication_status, m.publication_status or 'N/A')
        chap_count = str(len(m.chapters) if m.chapters else 0)
        vis_str = 'Sim' if m.is_visible else 'Não'
        feat_str = 'Sim' if m.is_featured else 'Não'

        table_data.append([
            Paragraph(str(m.id), td_center),
            Paragraph(m.title or '', td_style),
            Paragraph(m.author or 'N/A', td_style),
            Paragraph(st_pt, td_center),
            Paragraph(chap_count, td_center),
            Paragraph(vis_str, td_center),
            Paragraph(feat_str, td_center),
            Paragraph(created_str, td_center),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#19191F')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E4E4E7')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)

    total_style = ParagraphStyle(
        'TotalText',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#19191F'),
        spaceBefore=10,
    )
    elements.append(Paragraph(f"Total de mangás listados: {len(mangas)}", total_style))

    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
