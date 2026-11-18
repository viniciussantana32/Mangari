from app.services.anilist_service import (
    get_manga_by_id,
    get_manga_search_results,
    get_popular_manga,
    get_recent_manga,
)


def test_anilist_service_returns_empty_list_for_errors(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {'errors': [{'message': 'bad'}]}

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr('requests.post', fake_post)
    results, error = get_manga_search_results('naruto')
    assert results == []
    assert error is not None


def test_anilist_service_returns_none_for_missing_media(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': {'Media': None}}

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr('requests.post', fake_post)
    media, error = get_manga_by_id(1)
    assert media is None
    assert error is None


def test_popular_and_recent_queries_request_cover_data(monkeypatch, app):
    requests_seen = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': {'Page': {'media': [{'id': 42}]}}}

    def fake_post(*args, **kwargs):
        requests_seen.append(kwargs['json'])
        return FakeResponse()

    monkeypatch.setattr('requests.post', fake_post)
    with app.app_context():
        popular, popular_error = get_popular_manga(per_page=8)
        recent, recent_error = get_recent_manga(per_page=8)

    assert popular == [{'id': 42}]
    assert popular_error is None
    assert recent == [{'id': 42}]
    assert recent_error is None
    assert 'sort: POPULARITY_DESC' in requests_seen[0]['query']
    assert 'coverImage { large extraLarge }' in requests_seen[0]['query']
    assert requests_seen[0]['variables']['perPage'] == 8
    assert 'sort: START_DATE_DESC' in requests_seen[1]['query']
    assert 'startDate_greater: $startDateGreater' in requests_seen[1]['query']


def test_manga_details_query_keeps_staff_fields(monkeypatch, app):
    requests_seen = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {'data': {'Media': {'id': 7}}}

    def fake_post(*args, **kwargs):
        requests_seen.append(kwargs['json']['query'])
        return FakeResponse()

    monkeypatch.setattr('requests.post', fake_post)
    with app.app_context():
        manga, error = get_manga_by_id(7)

    assert manga == {'id': 7}
    assert error is None
    assert 'staff {' in requests_seen[0]
    assert 'coverImage { large extraLarge }' in requests_seen[0]
