from __future__ import annotations

import re
import unittest
from pathlib import Path


class ViteProxyConfigTests(unittest.TestCase):
    def test_api_proxy_preserves_browser_host(self) -> None:
        config_path = Path(__file__).resolve().parents[1] / "vite.config.ts"
        source = config_path.read_text(encoding="utf-8")
        api_proxy = re.search(
            r'"/api"\s*:\s*\{(?P<body>.*?)\n\s*\}',
            source,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(api_proxy, "vite.config.ts must define an /api proxy")
        body = api_proxy.group("body")
        self.assertRegex(body, r"target\s*:\s*backendTarget")
        self.assertRegex(body, r"changeOrigin\s*:\s*false")


if __name__ == "__main__":
    unittest.main()
