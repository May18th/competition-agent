# tests/probes —— 一次性探针与手工校验脚本

本目录存放开发期的一次性验证脚本和浏览器探针壳，不属于自动化测试套件。
正式回归测试请放在 `tests/` 根下（例如 `test_repository_layout.py`）。

## 约定

- 文件名以 `_` 开头的是**手工执行**的探针脚本，不参与 `unittest` 自动发现。
- `probe_*.html` 是浏览器探针壳，需本地起服务后打开，或直接用绝对路径访问。
- 输出文件写到 `_outputs/`（已在 `.gitignore` 中忽略），跑完自行清理。

## 执行方式

脚本内部会自行 `chdir` 到仓库根或上溯计算根目录，可在任意目录执行：

```bash
python tests/probes/_check_startup.py     # 校验启动块位置（防回归）
python tests/probes/_check_kb_match.py    # 赛事下拉与 data/*.txt 覆盖比对
python tests/probes/_wbcheck.py           # 首页 DOM 闭合与内联脚本语法
python tests/probes/_verify_kb.py         # 知识库检索层自测
```

依赖 HTTP 的脚本（`_time_bench.py`、`_rich_test.py`、`_verify_err.py`、`_probe_live.py`）
需要先启动本地服务：`python run.py`（默认 8080）。

`_wbcheck.py` 需要 Node，可用环境变量 `NODE_BIN` 指定，否则回退到 PATH 中的 `node`。
