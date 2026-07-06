from src.services.site_seo_service import build_robots_txt


def test_robots_txt_allows_public_and_disallows_admin():
    text = build_robots_txt()
    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert "Disallow: /login" in text
    assert "Disallow: /api/" in text
