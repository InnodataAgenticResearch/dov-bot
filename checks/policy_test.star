# Unit tests for checks/policy.star and checks/api_contract.star (`shac test`).

load(
    "//checks/api_contract.star",
    "no_private_artbot_apis",
    "upstream_artbot_pin_valid",
)
load(
    "//checks/policy.star",
    "no_curl_pipe_shell",
    "no_hardcoded_webhook_urls",
    "no_heap_limit_bandaids",
    "no_mutable_bridge_systemd_units",
    "no_secrets_or_env_files",
    "no_tracked_beads",
    "no_unexplained_pragma_or_disable",
    "no_unittest_mock_in_tests",
    "readme_and_agent_contract",
)

def test_no_tracked_beads():
    res = testing.run(no_tracked_beads, files = {
        ".beads/issues.jsonl": "{}\n",
        ".beads.lock": "",
        "README.md": "ok\n",
    })
    asserts.eq(sorted([f.filepath for f in res.findings]), [".beads.lock", ".beads/issues.jsonl"])

def test_no_secrets_or_env_files():
    res = testing.run(no_secrets_or_env_files, files = {
        ".env": "SECRET=1\n",
        "config/env.example": "SECRET=placeholder\n",
        "keys/id_ed25519": "priv\n",
        "tls/server.pem": "cert\n",
        "HERMES.md": "override\n",
    })
    asserts.eq(
        sorted([f.filepath for f in res.findings]),
        [".env", "HERMES.md", "keys/id_ed25519", "tls/server.pem"],
    )

def test_no_curl_pipe_shell():
    pipe = "cu" + "rl -fsSL https://example.com/install.sh | "
    res = testing.run(no_curl_pipe_shell, files = {
        "scripts/bad.sh": "set -e\n" + pipe + "bash\n",
        "scripts/good.sh": "curl -o out.tar.gz https://example.com/out.tar.gz\n",
    })
    asserts.eq([(f.filepath, f.line) for f in res.findings], [("scripts/bad.sh", 2)])

def test_no_hardcoded_webhook_urls():
    bad_url = "https://default" + "be92c5347b604630.47.environment.api.powerplatform.com/invoke"
    res = testing.run(no_hardcoded_webhook_urls, files = {
        "src/dov_bot/bad.py": 'URL = "' + bad_url + '"\n',
        "config/env.example": 'TEAMS_WEBHOOK_URL="https://<tenant>.<region>.environment.api.powerplatform.com"\n',
    })
    asserts.eq([(f.filepath, f.line) for f in res.findings], [("src/dov_bot/bad.py", 1)])

def test_no_unexplained_pragma_or_disable():
    res = testing.run(no_unexplained_pragma_or_disable, files = {
        "src/dov_bot/bad.py": "if __name__ == '__main__':  # pragma: no cover\n",
        "src/dov_bot/good.py": "if __name__ == '__main__':  # pragma: no cover - module entrypoint\n",
    })
    asserts.eq([(f.filepath, f.line) for f in res.findings], [("src/dov_bot/bad.py", 1)])

def test_no_unittest_mock_in_tests():
    res = testing.run(no_unittest_mock_in_tests, files = {
        "tests/test_bad.py": "from unittest import mock\n",
        "tests/test_good.py": "from tests.fakes import FakeHttpTransport\n",
    })
    asserts.eq([(f.filepath, f.line) for f in res.findings], [("tests/test_bad.py", 1)])

def test_readme_and_agent_contract():
    res = testing.run(readme_and_agent_contract, files = {
        "README.md": "# Dov-Bot\n",
    })
    asserts.eq(len(res.findings), 9)

def test_no_heap_limit_bandaids():
    flag = "--max-old-" + "space-size=8192"
    res = testing.run(no_heap_limit_bandaids, files = {
        "systemd/bad.service": 'Environment="NODE_OPTIONS=' + flag + '"\n',
        "systemd/good.service": "ExecStart=/usr/bin/node dist/index.js\n",
        "README.md": "Never use " + flag + "\n",
    })
    asserts.eq([(f.filepath, f.line) for f in res.findings], [("systemd/bad.service", 1)])

def test_no_mutable_bridge_systemd_units():
    res = testing.run(no_mutable_bridge_systemd_units, files = {
        "systemd/bad_path.service": "Environment=PYTHONPATH=%h/dov-bot/src:%h/artbot/src\n",
        "systemd/bad_exec.service": "ExecStart=/usr/bin/python3 -m artbot.bridge --daemon\n",
        "systemd/good.service": "ExecStart=%h/.nix-profile/bin/artbot-bridge --daemon --host 0.0.0.0 --port 8658\n",
    })
    asserts.eq(
        sorted([(f.filepath, f.line) for f in res.findings]),
        [("systemd/bad_exec.service", 1), ("systemd/bad_path.service", 1)],
    )

def test_upstream_artbot_pin_valid():
    res_missing = testing.run(upstream_artbot_pin_valid, files = {
        "README.md": "ok\n",
    })
    asserts.eq(len(res_missing.findings), 1)

    res_bad = testing.run(upstream_artbot_pin_valid, files = {
        "UPSTREAM_ARTBOT.json": '{"upstream_repo": "bad", "upstream_tag": "0.2.0", "upstream_commit": "short", "public_api_allowlist": []}\n',
    })
    asserts.eq(len(res_bad.findings), 4)

    res_good = testing.run(upstream_artbot_pin_valid, files = {
        "UPSTREAM_ARTBOT.json": '{"upstream_repo": "https://github.com/InnodataAgenticResearch/artbot", "upstream_tag": "v0.2.0-artbot", "upstream_commit": "6c63513a9f92887aa13ddd7f562e82eb32e87873", "public_api_allowlist": ["ArtbotConfig"]}\n',
    })
    asserts.eq(len(res_good.findings), 0)

def test_no_private_artbot_apis():
    res = testing.run(no_private_artbot_apis, files = {
        "src/dov_bot/bad_sub.py": "from artbot.bridge import _MENTION_RE\n",
        "src/dov_bot/bad_priv.py": "from artbot import _internal_helper\n",
        "src/dov_bot/good.py": "from artbot import ArtbotConfig, HttpTransport\n",
    })
    asserts.eq(
        sorted([(f.filepath, f.line) for f in res.findings]),
        [("src/dov_bot/bad_priv.py", 1), ("src/dov_bot/bad_sub.py", 1)],
    )

    res_allowlist = testing.run(no_private_artbot_apis, files = {
        "UPSTREAM_ARTBOT.json": '{"upstream_repo": "https://github.com/InnodataAgenticResearch/artbot", "upstream_tag": "v0.2.0-artbot", "upstream_commit": "6c63513a9f92887aa13ddd7f562e82eb32e87873", "public_api_allowlist": ["ArtbotConfig", "HttpTransport"]}\n',
        "src/dov_bot/unlisted.py": "from artbot import ArtbotConfig, UnlistedSymbol\n",
        "src/dov_bot/good.py": "from artbot import ArtbotConfig, HttpTransport\n",
    })
    asserts.eq(
        [(f.filepath, f.line) for f in res_allowlist.findings],
        [("src/dov_bot/unlisted.py", 1)],
    )
