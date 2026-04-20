# VCPToolBox 蓝绿部署方案计划

## 1. 现状与问题分析

### 1.1 当前部署架构
- **单目录部署**：`F:/AI_Study_studio/VCPToolBox` 既是代码库也是运行时目录
- **更新策略**：`git stash → reset --hard → reconcile → pm2 restart`（当前 updater 逻辑）
- **服务中断**：PM2 restart 期间服务不可用，且硬重置可能因文件锁或状态冲突失败

### 1.2 运行时状态文件（关键）
通过 `git status` 实测，VCPToolBox 运行时在代码树内产生以下状态类文件：

| 文件 | 类型 | 位置特点 |
|:---|:---|:---|
| `Plugin/ImageProcessor/multimodal_cache.sqlite` (+shm, wal) | SQLite WAL 数据库 | 与 `image-processor.js` 等代码文件混存于同一目录 |
| `Plugin/RAGDiaryPlugin/folding_store.db` (+shm, wal) | SQLite WAL 数据库 | 与 `FoldingStore.js` 等代码文件混存 |
| `Plugin/SkillBridge/skill-index.txt` | 文本索引 | 与代码混存 |
| `Plugin/UserAuth/code.bin` | 二进制数据 | 与代码混存 |
| `Plugin/VCPTaskAssistant/task-center-data.json` | JSON 数据 | 运行时新增，与代码混存 |
| `Plugin/VCPTavern/presets/Gemini-fix.json` | JSON 配置/数据 | 运行时新增，与代码混存 |
| `sarprompt.json` | JSON 数据 | 根目录，与代码混存 |

**核心矛盾**：状态文件与代码文件高度耦合（混存于同一目录），无法通过简单的"整个目录 junction/symlink 到共享卷"来解决，否则 git pull 会失效。

### 1.3 蓝绿部署目标
- 使用 **APISIX**（Docker 部署）作为统一流量入口
- 维护 **blue / green** 两套独立的代码目录与 PM2 进程组
- 更新时：**预热 inactive 环境 → 状态同步 → 健康检查 → APISIX 切流 → 停止旧环境**
- 切换过程 **零停机**

---

## 2. 架构设计

### 2.1 物理拓扑（Windows 宿主）

```
用户请求
    ↓
[APISIX Gateway]  ←── Docker / WSL2 (监听宿主机端口 80/443)
    │
    ├── Route: /api/*  → Upstream: vcp-backend
    │
    └── Upstream "vcp-backend" (动态切换权重)
            ├── 127.0.0.1:3001  (blue)  权重 100 / 0
            └── 127.0.0.1:3002  (green) 权重 0 / 100

[Blue Environment]
    目录: F:/AI_Study_studio/VCPToolBox-blue
    PM2:  vcp-main-blue  (PORT=3001), vcp-admin-blue (PORT=3003)

[Green Environment]
    目录: F:/AI_Study_studio/VCPToolBox-green
    PM2:  vcp-main-green (PORT=3002), vcp-admin-green (PORT=3004)

[Auto-Updater Service] (本 Python 项目改造)
    负责: 检测更新、管理 blue/green 生命周期、状态同步、调用 APISIX Admin API
```

### 2.2 部署流程（单次更新周期）

```
1. Updater 检测到 remote 有新 commit
        ↓
2. 确定 inactive color（如 blue active → green inactive）
        ↓
3. 在 inactive 目录执行 git fetch + reset --hard（独立代码，不干扰 active）
        ↓
4. 【关键】状态同步：将 active 环境的运行时状态文件复制到 inactive
        ↓
5. 启动 inactive 环境的 PM2 进程（新端口），执行健康检查
        ↓
6. 调用 APISIX Admin API，将流量 100% 切换到 inactive
        ↓
7. 等待 30s（观察期），确认稳定后停止 old active 的 PM2 进程
        ↓
8. 持久化新的 active_color 标记到磁盘（下次更新参考）
```

---

## 3. 状态同步方案（核心问题）

### 3.1 方案总览："在线备份 + 清单复制"

由于状态文件与代码混存，且 VCPToolBox 使用硬编码的 `path.join(__dirname, 'xxx.db')` 路径，**在不修改 VCPToolBox 源码的前提下**，采用以下双层同步策略：

| 文件类型 | 同步方式 | 一致性保证 |
|:---|:---|:---|
| **SQLite 数据库** (.db, .sqlite 及 -wal, -shm) | Python `sqlite3` 在线热备份 (`Connection.backup()`) | SQLite 原生在线备份 API，读取快照不阻塞写入，备份结果事务一致 |
| **普通状态文件** (.json, .txt, .bin 等) | `robocopy /MIR`（Windows 原生，支持权限与增量复制） | 复制期间文件可能短暂变化，但因文件小、复制快，风险可控 |

### 3.2 SQLite 热备份机制

```python
import sqlite3

def backup_sqlite(src_path: Path, dst_path: Path) -> None:
    """在线备份 SQLite 数据库，无需停止源服务。"""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src_path))
    dst_conn = sqlite3.connect(str(dst_path))
    with dst_conn:
        src_conn.backup(dst_conn)  # 读取一致性快照，不锁库
    dst_conn.close()
    src_conn.close()
```

- **better-sqlite3 使用 WAL 模式**：`backup()` 会正确读取 WAL 中的未提交数据，生成完整的数据库副本
- **备份后目标环境独立**：inactive 启动后写入自己的数据库副本，切换后新数据自然进入新 active
- **下次更新**：从新 active 再次热备份到新的 inactive，数据持续"接力"

### 3.3 状态文件清单配置

在 `config.yaml` 中增加 `state_sync` 配置段，明确定义需要跨环境同步的文件/目录模式：

```yaml
blue_green:
  enabled: true
  colors:
    blue:
      repo_path: "F:/AI_Study_studio/VCPToolBox-blue"
      port_offset: 0        # vcp-main=3001, vcp-admin=3003
    green:
      repo_path: "F:/AI_Study_studio/VCPToolBox-green"
      port_offset: 1        # vcp-main=3002, vcp-admin=3004
  active_color: "blue"      # 持久化标记，updater 维护

  apisix:
    admin_url: "http://127.0.0.1:9180"
    admin_key: "edd1c9f034335f136f87ad84b625c8f1"  # APISIX default key
    upstream_id: "vcp-backend"

  state_sync:
    # SQLite 数据库模式：自动匹配主库 + WAL + SHM
    sqlite_databases:
      - "Plugin/ImageProcessor/multimodal_cache.sqlite"
      - "Plugin/RAGDiaryPlugin/folding_store.db"
    # 普通文件/目录模式（robocopy 支持 glob）
    file_patterns:
      - "Plugin/SkillBridge/skill-index.txt"
      - "Plugin/UserAuth/code.bin"
      - "Plugin/VCPTaskAssistant/task-center-data.json"
      - "Plugin/VCPTavern/presets/Gemini-fix.json"
      - "sarprompt.json"
      # 可按需新增目录级同步，如："Plugin/XXX/data/*"
```

### 3.4 同步时序与一致性

```
        Active 运行中          Inactive 准备中
        ├─ 接受用户请求
        ├─ SQLite WAL 写入
        └─ 状态文件更新

Step 1: 关闭 old active 的写入（graceful shutdown preparation）
        → PM2 发送 SIGINT，让 Node.js 优雅关闭连接、flush WAL
        → 但**不立即停止服务**，只是让 active 进入"只读收尾"状态
        → 实际策略：直接热备份，无需停止 active（SQLite backup 不阻塞）

Step 2: 执行热备份 + robocopy
        → 耗时通常 < 5s（数据库不大）

Step 3: 启动 Inactive
        → Inactive 加载复制来的最新状态
        → 执行自身初始化

Step 4: 健康检查通过 → APISIX 切流
        → 用户请求路由到 Inactive
        → Old Active 停止（此时已没有新流量，可安全停止）
```

**关于回滚**：若切换后发现新环境异常，APISIX 可立即切回 old active。由于 old active 在切换后**已停止接受新请求且未删除**，其数据库状态冻结在切换前一刻。切换后产生的新数据在 inactive 中，回滚会丢失这部分数据。这是蓝绿部署的固有权衡。缓解措施：
- 切换后观察期（如 60s）内保留 old active 运行
- 观察期内新写入同时热备份回 old active（双向预热），实现真正的双活

---

## 4. Updater 项目改造计划

### 4.1 新增模块

| 模块 | 职责 |
|:---|:---|
| `src/vcptoolbox_updater/blue_green.py` | `BlueGreenDeployer` 核心类：管理 color 状态、执行完整蓝绿部署流程 |
| `src/vcptoolbox_updater/state_sync.py` | `StateSyncOperator`：SQLite 热备份 + robocopy 文件同步 |
| `src/vcptoolbox_updater/apisix_client.py` | `ApisixAdminClient`：封装 APISIX Admin API 调用（get/set upstream nodes） |
| `src/vcptoolbox_updater/health_check.py` | `HealthChecker`：HTTP 健康检查（调用 inactive 的 /health 或根路径） |

### 4.2 配置模型扩展（`config.py`）

新增 `BlueGreenConfig`、`ApisixConfig`、`StateSyncConfig` Pydantic 模型，并整合进 `ServiceConfig`。

### 4.3 调度器与 CLI 改造

- `scheduler.py` / `cli.py`：当 `blue_green.enabled=true` 时，调用 `BlueGreenDeployer.deploy()` 替代原有的直接 `git reset + pm2 restart`
- 保留原有的单目录模式作为 fallback（`blue_green.enabled=false` 时行为不变）

### 4.4 PM2 进程命名空间隔离

- Blue 的进程名：`vcp-main-blue`, `vcp-admin-blue`
- Green 的进程名：`vcp-main-green`, `vcp-admin-green`
- 通过 PM2 `name` 前缀区分，避免冲突
- `Pm2Operator` 扩展：支持指定进程名前缀和端口环境变量注入

---

## 5. Traefik 部署与配置（Windows 原生）

### 5.1 Traefik 二进制部署

在项目根目录新增 `traefik/` 目录，放置 Windows 可执行文件与配置：

```
traefik/
├── traefik.exe              # 官方 Windows 二进制
├── traefik.yaml             # 静态配置（入口点、Provider、API）
└── dynamic/
    └── vcp-upstream.yaml    # 动态配置（Upstream、Router），Updater 修改此文件实现切流
```

### 5.2 静态配置（traefik.yaml）

```yaml
entryPoints:
  web:
    address: ":80"

providers:
  file:
    directory: "./dynamic"
    watch: true              # 关键：监控文件变化并热重载

api:
  insecure: true             # 开发/内网使用，生产建议启用认证
  dashboard: true
```

### 5.3 动态配置（dynamic/vcp-upstream.yaml）

Updater 在切换时直接覆写此文件，Traefik 自动热重载：

```yaml
http:
  services:
    vcp-backend:
      weighted:
        services:
          - name: blue
            weight: 100
          - name: green
            weight: 0

    blue:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:3001"
        healthCheck:
          path: "/health"
          interval: "10s"

    green:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:3002"
        healthCheck:
          path: "/health"
          interval: "10s"

  routers:
    vcp-main:
      rule: "PathPrefix(`/`)"
      service: "vcp-backend"
      entryPoints:
        - "web"
```

### 5.4 蓝绿切换机制

Updater 无需调用 HTTP API，只需修改 `dynamic/vcp-upstream.yaml` 并保存：

```python
# traefik_client.py 示意（实际为文件操作）
def switch_traffic(active_color: Literal["blue", "green"]) -> None:
    config = {
        "http": {
            "services": {
                "vcp-backend": {
                    "weighted": {
                        "services": [
                            {"name": "blue", "weight": 100 if active_color == "blue" else 0},
                            {"name": "green", "weight": 100 if active_color == "green" else 0},
                        ]
                    }
                }
            }
        }
    }
    yaml.dump(config, open("traefik/dynamic/vcp-upstream.yaml", "w"))
    # Traefik watch 自动感知，通常在 1s 内生效
```

---

## 6. 可选方案对比

### 方案 A：在线热备份 + 清单复制（Plan 主推方案）
- **特点**：不修改 VCPToolBox 源码，通过 Python updater 在蓝绿环境间复制状态文件
- **SQLite 同步**：`sqlite3.backup()` 在线热备份，事务一致
- **文件同步**：`robocopy` 按清单复制
- **优势**：改动集中在本项目（updater），实施周期短，风险可控
- **劣势**：切换后回滚会丢失切换期间产生的新数据；需维护状态文件清单

### 方案 B：共享数据卷（类 Android A/B 分区更新）
- **特点**：将代码与数据彻底分离——blue/green 是两个独立的代码目录（类似 Android 的 A/B 系统分区），所有运行时状态文件集中存放在一个**共享数据目录**（类似 Android 的 `/data` 用户数据分区，独立于系统分区）
- **实现方式**：(1) 修改 VCPToolBox 核心代码与插件，通过环境变量（如 `VCP_DATA_ROOT`）将数据库/状态文件重定向到共享目录；(2) 推动插件作者将运行时文件加入 `.gitignore`，使其彻底脱离 git 管辖
- **同步机制**：**零复制**。切换时只需要切换 Traefik 的 upstream 权重，无需复制任何状态文件。回滚时数据完全一致
- **优势**：最接近 Android 的 Seamless Update（A/B 分区更新）模型——系统分区独立更新，用户数据分区始终共享
- **劣势**：需要侵入式修改 VCPToolBox 的插件加载逻辑和数据库初始化代码；需要协调插件生态

### 方案 B-1：轻量版 —— 仅 `.gitignore` 治理（零代码改动）
- **思路**：不修改插件源码，仅要求插件作者将运行时文件加入 `.gitignore`。状态文件仍散落在代码树中，但 git 不再跟踪它们
- **蓝绿部署效果**：两个环境各自持有独立的数据库副本，切换前仍需通过 `state_sync`（robocopy / SQLite 热备份）同步；但由于文件已被 git 忽略，`git pull` 永远不会冲突或覆盖它们
- **适用场景**：插件作者响应快，或你们自行 fork 维护插件
- **局限**：仍需要复制同步，未能实现真正的"数据分区共享"

> **类比说明**：Android 的 A/B 系统更新之所以能做到无缝切换，核心就在于 **系统分区（slot_a / slot_b）与用户数据分区（/data）物理分离**。方案 B 正是效仿这一架构；方案 A 则更像是"每次更新都把 /data 复制一份到新系统分区"，虽然可行，但不是最优解。
>
> **建议**：
> - **短期**：选 **方案 A**，快速获得蓝绿部署能力
> - **中期**：同步推进 **方案 B-1**，推动插件作者加入 `.gitignore`，清理 git 跟踪污染
> - **长期**：对核心高频写入的 SQLite 数据库实施 **方案 B** 的共享目录改造，彻底实现 Android 式的代码/数据分离架构

---

## 8. 实施步骤（Phase 划分）

### Phase 1：基础设施准备
1. 克隆第二套代码目录：`VCPToolBox-green`（从现有 `VCPToolBox` 复制并清理）
2. 部署 APISIX Docker 容器，配置基础 Route 与 Upstream
3. 验证手动切换 Upstream 权重是否生效

### Phase 2：Updater 核心改造
4. 实现 `apisix_client.py`（Admin API 封装）
5. 实现 `state_sync.py`（SQLite 热备份 + robocopy）
6. 实现 `health_check.py`（HTTP 探活）
7. 实现 `blue_green.py`（完整部署流程编排）
8. 扩展 `config.py` 与 `cli.py` 支持蓝绿配置段

### Phase 3：集成验证
9. 在测试环境模拟更新：修改远端 commit，验证完整蓝绿流程
10. 测试状态同步：在 active 写入数据，确认 inactive 启动后数据一致
11. 测试 APISIX 切流：验证切换过程请求无中断（可用 `curl` 循环测试）
12. 测试回滚：异常场景下 APISIX 切回旧环境的能力

### Phase 4：生产切流
13. 配置正式域名指向 APISIX 端口
14. 将现有单目录模式平滑迁移到蓝绿模式（初始 clone green 目录并同步一次状态）
15. 启用 Updater 自动调度

---

## 9. 风险与缓解

| 风险 | 缓解措施 |
|:---|:---|
| SQLite 热备份时源库被删除或损坏 | 备份使用只读连接，不持有写锁；异常时回退到文件级复制 |
| 状态文件清单遗漏新插件产生的文件 | `config.yaml` 中 `file_patterns` 支持目录级通配；首次运行后通过 `git status` 巡检补充 |
| APISIX Admin API 不可达 | 部署前验证连通性；Updater 中增加重试与降级逻辑（失败时回退到传统 PM2 restart） |
| 两个环境 PM2 端口冲突 | 通过 `port_offset` 机制，蓝绿使用完全不同的端口段，由 Updater 注入 `PORT` 环境变量 |
| 回滚时数据丢失 | 切换后观察期内保留 old active 运行；关键数据通过 SQLite 热备份双向同步实现双活预热 |

---

## 10. 与现有代码的兼容性

- **100% 向后兼容**：新增 `blue_green.enabled` 开关，默认为 `false`，现有单目录部署不受影响
- **Git 策略不变**：`git_ops.py` 的 `stash → reset --hard → reconcile` 逻辑在蓝绿模式下只是**应用对象从单目录变为 inactive 目录**，逻辑本身无需改动
- **PM2 管理增强**：`pm2_ops.py` 增加进程前缀参数，不影响现有调用
