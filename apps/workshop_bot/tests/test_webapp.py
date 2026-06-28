"""Web app: the Discord-markdown line formatter and the Tailscale identity gate."""

import unittest

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from apps.workshop_bot.webapp import routes, server


class FormatTests(unittest.TestCase):
    def test_bold_code_italic_and_escape(self):
        self.assertEqual(routes._fmt("**WT350** [build]"), "<strong>WT350</strong> [build]")
        self.assertEqual(routes._fmt("on `weekly.thingelstad.com`"),
                         "on <code>weekly.thingelstad.com</code>")
        self.assertEqual(routes._fmt("*(no in-flight tracker yet)*"),
                         "<em>(no in-flight tracker yet)</em>")
        # raw HTML is escaped before formatting
        self.assertIn("&lt;script&gt;", routes._fmt("<script>"))


async def _ok(request):
    return web.Response(text="ok")


class IdentityGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_header_is_forbidden(self):
        resp = await server._identity_mw(make_mocked_request("GET", "/"), _ok)
        self.assertEqual(resp.status, 403)

    async def test_allowed_login_passes(self):
        req = make_mocked_request("GET", "/", headers={server.IDENTITY_HEADER: "jthingelstad@github"})
        resp = await server._identity_mw(req, _ok)
        self.assertEqual(resp.status, 200)

    async def test_foreign_login_is_forbidden(self):
        req = make_mocked_request("GET", "/", headers={server.IDENTITY_HEADER: "someone@else"})
        resp = await server._identity_mw(req, _ok)
        self.assertEqual(resp.status, 403)

    async def test_healthz_bypasses_identity(self):
        resp = await server._identity_mw(make_mocked_request("GET", "/healthz"), _ok)
        self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
