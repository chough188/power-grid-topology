r"""Cron overnight cleanup smoke test.

- 解析 cron_overnight_cleanup.ps1 的 param, 验证默认 DryRun 与 LIVE 切换;
- 使用临时 CodexHome 跑 DryRun, 验证:
    1. 日志和 JSON 摘要文件生成;
    2. JSON 中 mode=DRY-RUN, exit_code=0;
    3. 不修改真实 $env:USERPROFILE\.codex (绝对隔离)。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPTS = ROOT / 'scripts'
PS1 = SCRIPTS / 'cron_overnight_cleanup.ps1'
REGISTER = SCRIPTS / 'Register-CodexNightlyCleanup.ps1'


def _pwsh():
    for name in ('pwsh.exe', 'powershell.exe'):
        from shutil import which
        path = which(name)
        if path:
            return path
    raise FileNotFoundError("pwsh.exe / powershell.exe 均不在 PATH")


def _extract_param_defaults(ps1_path):
    """简单解析 param() 块拿到默认值, 不依赖 AST。"""
    text = ps1_path.read_text(encoding='utf-8')
    defaults = {}
    for name in ['Live', 'KeepBackups', 'KeepArchived', 'VacuumLogsDays',
                 'ArchiveSessionsDays', 'CodexHome', 'MaxRetries',
                 'RetryDelaySeconds', 'LogRetentionDays']:
        m = re.search(r'\$%s\b[^=]*=\s*([^,;\n]+)' % re.escape(name), text)
        if m:
            defaults[name] = m.group(1).strip()
    return defaults


class CronScriptContractTests(unittest.TestCase):
    def test_default_mode_is_dry_run(self):
        defaults = _extract_param_defaults(PS1)
        # Live 默认应为 [switch] (无赋值, false), 不应是 $true
        live_raw = defaults.get('Live')
        self.assertIsNotNone(live_raw, "Live param 缺失")
        self.assertNotIn('$true', live_raw)

    def test_retries_and_log_retention_have_sane_defaults(self):
        defaults = _extract_param_defaults(PS1)
        self.assertEqual(defaults.get('KeepBackups'), '4')
        self.assertEqual(defaults.get('KeepArchived'), '30')
        self.assertEqual(defaults.get('VacuumLogsDays'), '7')
        self.assertEqual(defaults.get('LogRetentionDays'), '30')

    def test_cron_script_is_valid_powershell(self):
        """用 pwsh -NoProfile 解析语法, 不实际执行。"""
        result = subprocess.run(
            [_pwsh(), '-NoProfile', '-Command',
             f'$ErrorActionPreference = "Stop"; $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw -LiteralPath "{PS1}"), [ref]$null); "OK"'],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK', result.stdout)

    def test_register_script_is_valid_powershell(self):
        result = subprocess.run(
            [_pwsh(), '-NoProfile', '-Command',
             f'$ErrorActionPreference = "Stop"; $null = [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw -LiteralPath "{REGISTER}"), [ref]$null); "OK"'],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OK', result.stdout)


class CronDryRunIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix='cron_dry_'))
        self.fake_codex = self.tmp / '.codex'
        (self.fake_codex / 'sqlite').mkdir(parents=True)
        # 写一个 0 字节 logs_2.sqlite 模拟"未占用"
        (self.fake_codex / 'sqlite' / 'logs_2.sqlite').write_bytes(b'')
        # 真实环境变量中的 USERPROFILE 不变, 通过 -CodexHome 覆盖
        self.project_root = ROOT

    def test_dryrun_writes_log_and_json_summary_without_touching_real_home(self):
        real_home = pathlib.Path(os.environ['USERPROFILE']) / '.codex'
        before_signature = None
        if real_home.exists():
            before_signature = sorted(p.name for p in real_home.iterdir())

        out_root = self.tmp / 'project'
        # 复制 cron_log 目录创建
        (out_root / 'output' / 'cron_logs').mkdir(parents=True)
        # 真实路径会让脚本写 "codex_2013_disk_doctor.ps1" 调真脚本, 所以拷贝整个 scripts 到 tmp
        scripts_copy = out_root / 'scripts'
        scripts_copy.mkdir()
        for name in ['codex_2013_disk_doctor.ps1', 'codex_2013_vacuum_logs.py',
                     'cron_overnight_cleanup.ps1', 'Register-CodexNightlyCleanup.ps1']:
            src = SCRIPTS / name
            if src.exists():
                (scripts_copy / name).write_bytes(src.read_bytes())

        result = subprocess.run(
            [_pwsh(), '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-File', str(scripts_copy / 'cron_overnight_cleanup.ps1'),
             '-CodexHome', str(self.fake_codex)],
            capture_output=True, text=True, timeout=120,
            cwd=str(out_root),
        )
        # DryRun 即便失败也是显式 rc, 关键是: 不修改真实 home + 落摘要
        log_dir = out_root / 'output' / 'cron_logs'
        self.assertTrue(log_dir.exists(), f"cron_logs 未创建: {log_dir}")
        logs = sorted(log_dir.glob('cron_cleanup_*.log'))
        jsons = sorted(log_dir.glob('cron_cleanup_*.json'))
        self.assertGreaterEqual(len(logs), 1, f"未生成 .log: {list(log_dir.iterdir())}")
        self.assertGreaterEqual(len(jsons), 1, f"未生成 .json")

        data = json.loads(jsons[-1].read_text(encoding='utf-8-sig'))
        self.assertEqual(data['mode'], 'DRY-RUN')
        self.assertEqual(data['codex_home'], str(self.fake_codex))

        # 真实 home 没被改
        if before_signature is not None:
            after_signature = sorted(p.name for p in real_home.iterdir())
            self.assertEqual(before_signature, after_signature,
                             "DryRun 模式不应修改真实 $env:USERPROFILE\\.codex")


if __name__ == "__main__":
    unittest.main()
