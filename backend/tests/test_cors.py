import pytest

from app.core.config import settings


@pytest.mark.parametrize("method, path", [
    ("PATCH", "/api/v1/hospital"),
    ("PUT", "/api/v1/templates/checkin_reminder/en"),
    ("PATCH", "/api/v1/clinicians/00000000-0000-0000-0000-000000000000"),
    ("PUT", "/api/v1/app-admin/hospitals/1"),
    ("DELETE", "/api/v1/app-admin/rulesets/1"),
])
async def test_the_browser_may_send_every_method_the_screens_use(client, method, path):
    """Tests call the API directly, so only a preflight check catches a method the browser would be refused."""
    origin = settings.cors_origins_list[0]
    res = await client.options(path, headers={
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert res.status_code == 200, res.text
    assert method in res.headers["access-control-allow-methods"]
