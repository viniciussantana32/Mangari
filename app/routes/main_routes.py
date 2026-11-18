import re
from flask import Blueprint, jsonify, render_template, request, url_for
from sqlalchemy import or_

from app.models.manga import Manga
from app.routes.manga_routes import GENRE_MAP
from app.services.anilist_service import get_popular_manga, get_recent_manga

main_bp = Blueprint('main', __name__)


def _clean_synopsis(raw_text):
    if not raw_text:
        return 'Sem sinopse disponível no momento.'
    # Remove tags HTML
    clean = re.sub(r'<[^>]+>', '', raw_text)
    return ' '.join(clean.split())


@main_bp.route('/api/search')
def api_search():
    query_str = (request.args.get('q') or '').strip()
    if not query_str:
        return jsonify([])

    search_term = f"%{query_str}%"
    mangas = (
        Manga.query.filter(
            Manga.is_visible == True,
            or_(
                Manga.title.ilike(search_term),
                Manga.alternative_titles.ilike(search_term)
            )
        )
        .order_by(Manga.is_featured.desc(), Manga.updated_at.desc())
        .limit(6)
        .all()
    )

    results = []
    for m in mangas:
        target_id = m.anilist_id or m.id
        results.append({
            'id': m.id,
            'anilist_id': target_id,
            'title': m.title,
            'cover_url': m.cover_image or '',
            'status': m.publication_status or 'RELEASING',
            'detail_url': url_for('manga.detail', manga_id=target_id),
        })

    return jsonify(results)


@main_bp.route('/')
def index():
    popular_manga, popular_error = get_popular_manga(per_page=8)
    recent_manga, recent_error = get_recent_manga(per_page=8)

    # Buscar até 5 destaques
    featured_items = []
    seen_ids = set()

    # 1. Mangás locais marcados manualmente como destaque (is_featured=True e is_visible=True)
    local_featured = (
        Manga.query.filter_by(is_featured=True, is_visible=True)
        .order_by(Manga.updated_at.desc(), Manga.created_at.desc())
        .limit(5)
        .all()
    )

    for m in local_featured:
        target_id = m.anilist_id or m.id
        seen_ids.add(target_id)
        cover = m.cover_image or ''
        banner = m.banner_url
        is_cover_fallback = m.is_cover_banner
        featured_items.append({
            'id': target_id,
            'title': m.title,
            'cover_url': cover,
            'banner_url': banner,
            'banner_position': m.banner_position or 'center',
            'is_cover_fallback': is_cover_fallback,
            'score': None,
            'synopsis': _clean_synopsis(m.synopsis),
            'badge': 'DESTAQUE MANGARI',
        })

    # 2. Fallback: Se tiver menos de 5, completar com outros mangás locais visíveis
    if len(featured_items) < 5:
        remaining = 5 - len(featured_items)
        other_locals = (
            Manga.query.filter_by(is_visible=True)
            .filter(~Manga.id.in_([m.id for m in local_featured]) if local_featured else True)
            .order_by(Manga.created_at.desc())
            .limit(remaining)
            .all()
        )
        for m in other_locals:
            target_id = m.anilist_id or m.id
            if target_id not in seen_ids:
                seen_ids.add(target_id)
                cover = m.cover_image or ''
                banner = m.banner_url
                is_cover_fallback = m.is_cover_banner
                featured_items.append({
                    'id': target_id,
                    'title': m.title,
                    'cover_url': cover,
                    'banner_url': banner,
                    'banner_position': m.banner_position or 'center',
                    'is_cover_fallback': is_cover_fallback,
                    'score': None,
                    'synopsis': _clean_synopsis(m.synopsis),
                    'badge': 'NO CATÁLOGO',
                })

    # 3. Fallback inteligente final: Se ainda tiver menos de 5, completar com populares da AniList
    if len(featured_items) < 5 and popular_manga:
        for p in popular_manga:
            p_id = p.get('id')
            if p_id not in seen_ids:
                seen_ids.add(p_id)
                t = p.get('title') or {}
                manga_title = t.get('romaji') or t.get('english') or t.get('native') or 'Mangá sem título'
                cover_obj = p.get('coverImage') or {}
                cover_url = cover_obj.get('extraLarge') or cover_obj.get('large') or ''
                banner_url = p.get('bannerImage') or cover_url
                is_cover_fallback = not bool(p.get('bannerImage'))
                score = round(p.get('averageScore') / 10, 1) if p.get('averageScore') else None

                featured_items.append({
                    'id': p_id,
                    'title': manga_title,
                    'cover_url': cover_url,
                    'banner_url': banner_url,
                    'banner_position': 'center',
                    'is_cover_fallback': is_cover_fallback,
                    'score': score,
                    'synopsis': _clean_synopsis(p.get('description')),
                    'badge': f"POPULAR #{len(featured_items) + 1}",
                })
                if len(featured_items) >= 5:
                    break

    return render_template(
        'index.html',
        popular_manga=popular_manga,
        popular_error=popular_error,
        recent_manga=recent_manga,
        recent_error=recent_error,
        genre_list=GENRE_MAP,
        featured_carousel=featured_items,
    )
