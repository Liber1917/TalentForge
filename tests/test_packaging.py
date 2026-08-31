"""打包契约回归测试。

历史事故：talentforge.spec 曾为 pathex=[] 且 hiddenimports 未含 'talentforge'。
在"只装第三方依赖、不安装本项目"的构建环境（正是 CI 的装法，也是用户
Windows 新机的实况）里，PyInstaller 静默漏收 talentforge 包，产出必炸 exe
（ModuleNotFoundError: talentforge）——CI 曾连续发布三平台坏产物而无人察觉，
因为从不运行产物。本文件把两条防线固化为可回归验证的契约：
  ① spec 契约：pathex 自举可发现包 + hiddenimports 兜底；
  ② CI 契约：构建后必须先冒烟（跑产物、探 /api/health、验静态页 200）
     再进入安装器/上传步骤（fail-fast）。
"""
import ast
import importlib.machinery
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "talentforge.spec"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build.yml"


def _analysis_kwargs() -> dict[str, ast.expr]:
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ):
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    pytest.fail("talentforge.spec 中找不到 Analysis(...) 调用")


def _literal_str_list(node: ast.expr) -> list[str]:
    assert isinstance(node, ast.List), "期望 spec 中使用字符串字面量列表"
    return [
        elt.value
        for elt in node.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]


def test_spec_pathex_alone_discovers_talentforge_package():
    """pathex 必须让 Analysis 在未安装本项目的环境里也能从源码树发现 talentforge。

    PathFinder 限定在 pathex 解析出的路径内搜索，不借道 sys.path——
    这正是 PyInstaller 在"只装依赖"的构建环境中的处境。pathex 回退为
    空列表时本测试失败，即原 ModuleNotFoundError 事故的回归信号。
    """
    pathex = _literal_str_list(_analysis_kwargs()["pathex"])
    assert pathex, "pathex 为空：未安装本项目的构建环境将漏收 talentforge 包"
    search_paths = [str(SPEC_PATH.parent / p) for p in pathex]
    spec = importlib.machinery.PathFinder.find_spec("talentforge", search_paths)
    assert spec is not None, (
        f"pathex={pathex} 无法定位 talentforge 包（ModuleNotFoundError 事故回归）"
    )


def test_spec_hiddenimports_include_talentforge():
    """兜底契约：即便 entry.py 的静态分析未来失效（如改动态导入），hiddenimports 强制收录包本体。"""
    hidden = _literal_str_list(_analysis_kwargs()["hiddenimports"])
    assert "talentforge" in hidden, f"hiddenimports={hidden} 缺 'talentforge' 兜底"


def _build_app_steps() -> dict[str, int]:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("  build-app:")), None
    )
    if start is None:
        pytest.fail("build.yml 缺少 build-app job")
    steps: dict[str, int] = {}
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("  ") and not line.startswith("   "):
            break
        if line.startswith("      - name: "):
            steps[line.split("- name: ", 1)[1].strip()] = i
    return steps


def test_ci_smokes_artifact_after_build_before_packaging():
    """产物冒烟必须紧跟 PyInstaller 构建、先于安装器/上传步骤（fail-fast）。

    移除或后置冒烟 = 回到"构建成功即发布"的老路，坏产物事故将重演。
    """
    steps = _build_app_steps()
    required = [
        "Build exe with PyInstaller",
        "Smoke test exe (unix)",
        "Smoke test exe (windows)",
    ]
    for name in required:
        if name not in steps:
            pytest.fail(f"build.yml build-app 缺少步骤「{name}」")
    packaging_names = {
        "Install Inno Setup",
        "Build Windows installer",
        "Upload Windows artifacts",
        "Build macOS dmg",
        "Upload macOS artifacts",
        "Build Linux tarball",
        "Upload Linux artifacts",
    }
    packaging_positions = [i for name, i in steps.items() if name in packaging_names]
    assert packaging_positions, "build-app 中未找到打包/上传步骤，无法校验顺序"
    first_packaging = min(packaging_positions)
    assert steps["Build exe with PyInstaller"] < steps["Smoke test exe (unix)"] < first_packaging
    assert steps["Build exe with PyInstaller"] < steps["Smoke test exe (windows)"] < first_packaging


def _step_run_script(step_name: str) -> str:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    idx = next(
        (i for i, line in enumerate(lines) if line.strip() == f"- name: {step_name}"),
        None,
    )
    if idx is None:
        pytest.fail(f"build.yml 缺少步骤「{step_name}」")
    run_idx = next(
        (
            i
            for i in range(idx, min(idx + 10, len(lines)))
            if lines[i].strip() == "run: |"
        ),
        None,
    )
    if run_idx is None:
        pytest.fail(f"步骤「{step_name}」没有 run: | 脚本块")
    base_indent = len(lines[run_idx]) - len(lines[run_idx].lstrip())
    script_lines: list[str] = []
    for line in lines[run_idx + 1 :]:
        if line.strip() == "":
            script_lines.append("")
            continue
        if len(line) - len(line.lstrip()) <= base_indent:
            break
        script_lines.append(line)
    return "\n".join(script_lines)


def test_ci_unix_smoke_script_parses_and_asserts():
    """unix 冒烟脚本体须通过 bash 语法解析，且包含真实断言（health ok + 静态页 200）。

    只启动产物不检查结果不算冒烟；脚本语法错误则三平台 CI 全红。
    """
    script = _step_run_script("Smoke test exe (unix)")
    result = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, f"bash -n 解析失败：{result.stderr}"
    assert "api/health" in script, "冒烟脚本未探测 /api/health"
    assert "200" in script, "冒烟脚本未断言静态首页 HTTP 200"


_PWSH_READONLY_AUTO_VARS = (
    "home",
    "pid",
    "host",
    "pwd",
    "args",
    "input",
    "profile",
    "myinvocation",
    "error",
    "matches",
    "psstyle",
    "psitem",
    "true",
    "false",
    "null",
)


def test_ci_windows_smoke_script_avoids_readonly_auto_variables():
    """pwsh 冒烟脚本不得给只读自动变量赋值（本机无 pwsh，用静态契约兜底）。

    历史事故：`$home = 0` 撞上 PowerShell 只读自动变量 $HOME，
    Windows 冒烟必炸（Cannot overwrite variable HOME because it is
    read-only or constant）。赋值形如 `$var =`（含 `+=`/`-=` 前置形式）
    命中黑名单即失败。
    """
    import re

    script = _step_run_script("Smoke test exe (windows)")
    assignment_re = re.compile(r"\$(\w+)\s*(?:=[^=]|-=|\+=)")
    assigned = {m.group(1).lower() for m in assignment_re.finditer(script)}
    collisions = sorted(assigned & set(_PWSH_READONLY_AUTO_VARS))
    assert not collisions, (
        f"pwsh 冒烟脚本给只读自动变量赋值：{collisions}——"
        "Windows CI 将以 read-only variable 报错退出（改用普通变量名）"
    )


# ---------------- 扩展双目标打包（形态参考 OpenBiliClaw release 资产） ----------------


def _step_exists(step_name: str) -> bool:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    return any(line.strip() == f"- name: {step_name}" for line in lines)


def test_ci_packages_chrome_and_firefox_extensions_separately():
    """build-extension 必须分别打包双目标并独立上传工件。

    Chrome（dist/，service worker）与 Firefox（dist-firefox/，事件页变体）
    产物不可互换；单一 zip 无法覆盖 Firefox。命名带 manifest 版本
    （同 OpenBiliClaw 的 extension-v{ver}[-firefox].zip 惯例）。
    """
    chrome = _step_run_script("Package Chrome extension")
    assert "cd dist" in chrome, "Chrome 包必须以 dist/ 为 zip 根（manifest 在根）"
    assert "manifest.json" in chrome and "version" in chrome, "命名必须注入 manifest 版本"
    assert "-chrome.zip" in chrome
    firefox = _step_run_script("Package Firefox extension")
    assert "cd dist-firefox" in firefox, "Firefox 包必须以 dist-firefox/ 为 zip 根（自包含）"
    assert "-firefox.zip" in firefox
    assert _step_exists("Upload Chrome extension"), "缺少 Chrome 扩展独立工件上传"
    assert _step_exists("Upload Firefox extension"), "缺少 Firefox 扩展独立工件上传"


def test_ci_checks_extension_version_consistency():
    """双目标必须同版本出厂（OpenBiliClaw ci.yml 同款门禁）。

    buildFirefoxManifest 派生若丢/改版本，两 zip 将以不同版本流出。
    """
    script = _step_run_script("Check manifest version consistency")
    assert "dist/manifest.json" in script
    assert "dist-firefox/manifest.json" in script
    assert "version mismatch" in script
