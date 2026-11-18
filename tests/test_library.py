def test_library_entry_management(client):
    client.post('/auth/register', data={
        'name': 'Reader',
        'email': 'reader@example.com',
        'password': 'secret123',
        'confirm_password': 'secret123',
    })
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    response = client.post('/library/add', data={
        'anilist_id': '1',
        'manga_title': 'Test Manga',
        'cover_image': 'https://example.com/cover.jpg',
        'reading_status': 'Reading',
        'current_chapter': '12',
        'personal_rating': '8.5',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Manga added to your library' in response.data
