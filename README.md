# Moka MCP Server

基于 [Moka](https://www.mokahr.com) 开放 API 的 [MCP](https://modelcontextprotocol.io) Server。让 Claude、Cursor 等 AI 助手能够直接查询 Moka 招聘系统中的候选人、职位、招聘流程、组织架构、Offer 字段与人才库等信息。

> **第一阶段：只读。** 仅提供查询类能力，不涉及任何写入 / 删除等高危操作。

## 功能（Tool 一览）

> 下表的端点与版本均已对**生产环境实测校准**。Moka API 实际分布在三套基础路径上：
> `v1`（多数）、`v2`（招聘流程/阶段）、`candidate/v1`（候选人申请记录）。

| 模块 | Tool | 真实端点 | 方法/版本 |
|------|------|----------|-----------|
| 候选人 | `search_candidates` | `/data/ehrApplications` | GET v1 |
| 候选人 | `get_candidate_detail` | `/data/ehrApplications?applicationId=` | GET v1 |
| 候选人 | `get_candidate_applications` | `/getApplicationStates`（body: candidateId） | POST candidate/v1 |
| 候选人 | `get_candidate_stage` | 复用候选人详情的 `stageName` | GET v1 |
| 职位 | `list_jobs` | `/jobs/{orgId}`（**mode 必填**：social/campus） | GET v1 |
| 职位 | `get_job_detail` | `/jobs/{orgId}/{jobId}` | GET v1 |
| 职位 | `get_job_custom_fields` | 取自职位详情的 `customFields` | GET v1 |
| 流程 | `list_pipelines` | `/pipelines/getPipelinesList` | GET **v2** |
| 流程 | `list_stages` | `/stage/getStagesList` | GET **v2** |
| 组织 | `list_departments` | `/departments` | GET v1 |
| Offer | `get_offer_custom_fields` | `/offers/custom_fields`（返回 social/campus） | GET v1 |
| 人才库 | `list_talent_pools` | `/talentPool/list` | GET v1 |
| 人才库 | `list_talent_pool_candidates` | `/talentPool/candidates`（需 archivedAt 范围 + talentPoolIds） | GET v1 |

> **环境说明**：当前 API Key 仅在**生产环境**有效（CSM 未开通 staging），故 `MOKA_ENV` 请用 `production`。所有 Tool 均为只读，首阶段不涉及任何写操作。

## 安装

要求 Python 3.10+。

```bash
# 推荐用 uv
uv pip install -e .

# 或者用标准 venv + pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env` 并填入真实值：

```bash
cp .env.example .env
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `MOKA_API_KEY` | ✅ | Moka API Key（Basic Auth），由 CSM 发放 |
| `MOKA_ORG_ID` | 职位接口需要 | 组织标识，由 CSM 提供 |
| `MOKA_ENV` | | `production`（默认）/ `staging` |
| `MOKA_BASE_URL` | | 显式覆盖 Base URL，一般留空 |
| `MOKA_MASK_SENSITIVE` | | 是否脱敏手机号/身份证，默认 `true` |
| `MOKA_TIMEOUT` | | HTTP 超时（秒），默认 30 |
| `MOKA_MAX_ITEMS` | | 自动翻页累计上限，默认 200 |

## 运行

```bash
# 直接以 stdio 方式启动（供 MCP 客户端拉起）
moka-mcp-server

# 或
python -m moka_mcp.server
```

## 接入 Claude Desktop

编辑 `claude_desktop_config.json`（macOS 路径：
`~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "moka": {
      "command": "/绝对路径/到/.venv/bin/moka-mcp-server",
      "env": {
        "MOKA_API_KEY": "your_api_key_here",
        "MOKA_ORG_ID": "your_org_id",
        "MOKA_ENV": "production",
        "MOKA_MASK_SENSITIVE": "true"
      }
    }
  }
}
```

## 接入 Cursor

在 `.cursor/mcp.json` 中加入相同结构的配置即可。

## 自托管 HTTP 端点（Hermes / mcporter 接入）

除本地 stdio 外，本服务支持以 **streamable-http** 方式部署成一个 HTTP 端点，供
Hermes Agent 等通过 `url` + `X-API-Key` 请求头接入（与团队现有自研 MCP server 一致）。

### 1）以 http 方式启动

在 `.env` 中设置：

```env
MOKA_TRANSPORT=http
MOKA_HTTP_HOST=0.0.0.0
MOKA_HTTP_PORT=8000
MOKA_HTTP_PATH=/mcp
MOKA_MCP_API_KEY=请设置一个足够随机的访问密钥   # agent 接入凭证
```

然后启动：

```bash
moka-mcp-server
# 端点即为 http://<部署机IP>:8000/mcp
```

> 鉴权：开启 `MOKA_MCP_API_KEY` 后，所有请求必须携带请求头 `X-API-Key: <该值>`，
> 否则返回 401。留空表示不校验（仅限完全可信的内网）。生产环境务必设置，
> 并在外层用 HTTPS（反向代理）保护。

### 2）mcporter / Hermes 配置

在 mcporter 配置（如 `~/.mcporter/mcporter.json` 或项目 `config/mcporter.json`）中添加，
结构与团队其他 server 完全一致：

```json
{
  "mcpServers": {
    "moka-mcp": {
      "url": "https://<你的域名>/mcp",
      "headers": {
        "X-API-Key": "与 MOKA_MCP_API_KEY 相同的值"
      }
    }
  }
}
```

验证连通与工具列表：

```bash
mcporter list moka-mcp --schema
mcporter call moka-mcp.list_pipelines
```

> 注意区分两套凭证：`MOKA_API_KEY` 是「本服务 → Moka」的认证；`MOKA_MCP_API_KEY`
> 是「agent → 本服务」的认证（对应请求头 `X-API-Key`），两者互不相同。

## 通过 uvx 作为 stdio 包接入（推荐）

本服务可作为标准 **stdio MCP 包**，由 agent（Hermes/mcporter）以子进程方式拉起，
无需常驻 HTTP 服务。宿主机需有 Python / uv。

mcporter（stdio 形式）配置示例：

```json
{
  "mcpServers": {
    "moka-mcp": {
      "command": "uvx",
      "args": ["--from", "git+ssh://git@github.com/mingyangsun-sketch/moka-mcpserver.git", "moka-mcp-server"],
      "env": {
        "MOKA_API_KEY": "组织级 Moka Key",
        "MOKA_ORG_ID": "Antalpha",
        "MOKA_ENV": "production",
        "MOKA_ACTING_EMAIL": "该 Slack 用户的可信邮箱（Hermes 校验后注入）"
      }
    }
  }
}
```

> 每个用户用各自的 `env`（角色 + 身份）拉起一个实例，即可实现按用户限权（见下）。

## 权限控制（面向企业内部用户）

由于 Moka 的 API Key 是**组织级**的（能读全量数据），按用户限权只能在本服务层实现。
身份模型为**模型 A**：Hermes 解析 Slack 用户 → 决定角色/部门 → 用对应 env 拉起该
用户的 MCP 实例。因此 stdio 下**每个实例即一个调用者**，角色由启动 env 决定。

### 角色

| 角色 | 对应人群 | 可用工具 | 数据范围 |
|------|----------|----------|----------|
| `hr_admin` | HR/招聘团队负责人 | 全部 | 全量 |
| `recruiter` | 招聘专员 | 候选人/职位/流程/Offer/人才库/组织（读） | 全量 |
| `hiring_manager` | 用人经理/部门负责人 | 候选人/职位/流程/组织（无人才库） | **仅本部门** |
| `interviewer` | 面试官 | 候选人状态/详情/阶段 + 职位/流程（无人才库/Offer） | **仅自己参与面试的候选人** |
| `viewer` | 普通员工 | 职位/流程/组织（**不含候选人 PII**） | 全量（公开信息） |

### 身份与角色的确定方式（两种）

**① 按邮箱自动派生（推荐）**：Hermes 校验 Slack 用户后，注入其可信邮箱
`MOKA_ACTING_EMAIL`。本服务用组织 key 在 Moka 解析该用户（`POST /users/list`
按 email 精确查询），再按其 Moka `role` 与 `department` 自动定档：

| Moka role | 自动派生角色 |
|-----------|--------------|
| ≥30（HR / 管理员 / 超级管理员） | `hr_admin`（全量） |
| 20 / 25（用人经理 / 高级用人经理） | `hiring_manager`（仅其所在部门） |
| 10（面试官） | `interviewer`（仅自己参与面试的候选人） |
| 5 / 0（前台 / 内推人） | `viewer` |

> 邮箱在 Moka 找不到 → 退化为 `viewer`（最小权限）。无需手工维护角色表，
> 人员/部门在 Moka 一改，权限自动跟随。

**② 静态配置（兜底，未配 `MOKA_ACTING_EMAIL` 时生效）**：

| env | 说明 |
|-----|------|
| `MOKA_ROLE` | 上表角色之一；默认 `hr_admin` |
| `MOKA_DEPARTMENTS` | `hiring_manager` 必填：逗号分隔的本部门名 |
| `MOKA_SCOPE` | 数据范围覆盖：`all` / `department` |
| `MOKA_ALLOWED_TOOLS` | 工具白名单覆盖（逗号分隔，`*` 表示全部） |

控制分两层：
- **工具级**：角色决定可调用哪些 Tool（如 `viewer` 不能调用 `search_candidates`）。
- **数据行级**：`hiring_manager` 的候选人/职位结果按其部门过滤到本部门。

> ⚠️ `MOKA_ACTING_EMAIL` 必须是 **Hermes 校验过的可信邮箱**，不能由 LLM 或用户
> 随意填入，否则可冒充他人。

### 权限模型边界（重要）

本服务的权限是**我们自行设计的近似管控**，**不等同于**用户登录 Moka 后台时的真实数据权限：

- Moka 只提供**组织级**访问控制：这把 API Key 是全权的、不区分调用者，Moka 不会按用户过滤。
- Moka 也**未开放**「查询某用户有效数据权限范围」的接口（`/users/*`、`/userGroup/*` 只给
  角色、部门、分组成员等属性，不含数据可见范围规则）。
- 因此本服务只能用用户的 **Moka `role` + `department`** 两个属性，套**我们自己定的规则**做近似——
  可能与该用户在 Moka 实际能看到的范围有出入（看多或看少）。

> 若业务/合规要求「AI 中看到的 = 本人在 Moka 能看到的」强一致，Moka 现有 API 无法支持
> （用户级 OAuth 亦不可行，Moka 仅支持组织级）。当前定位为**面向可信内部场景的近似管控**。

> ⚠️ **安全前提**：组织级 Key 会随实例分发，因此按用户限权只有在**可信后端
> （Hermes）统一持有 Key、并为每个用户 spawn 对应角色 env 的实例**时才真正有效；
> 终端用户不能自行查看/修改 env，否则可拿全量 Key 绕过限制。

## 设计要点

- **认证**：Basic Auth（`Authorization: Basic base64(api_key + ":")`），无需处理 token 刷新。
- **错误处理**：统一映射 401/403/404/429/500 为友好提示；特别地，按 `stage` 查询且该阶段无候选人时 Moka 返回 500，本服务会将其作为「空结果」处理。
- **分页**：基于 `next` 游标自动翻页，受 `MOKA_MAX_ITEMS` 上限保护。
- **脱敏**：默认对手机号、身份证号掩码（`138****1234` / `4103**********2910`）。
- **重试**：429 与网络错误做有限次指数退避重试。

## 项目结构

```
src/moka_mcp/
├── server.py          # FastMCP 入口，注册全部 Tool
├── config.py          # 配置（pydantic-settings）
├── client.py          # Moka HTTP 客户端（Basic Auth / 错误 / 重试）
├── errors.py          # 统一异常与状态码映射
├── tools/             # 各模块 Tool
│   ├── candidates.py
│   ├── jobs.py
│   ├── pipelines.py
│   ├── departments.py
│   ├── offers.py
│   └── talent_pools.py
└── utils/
    ├── pagination.py  # next 游标自动翻页
    └── sanitize.py    # 敏感字段脱敏
```

## 待办（第二阶段）

写入类能力（推进阶段、归档、创建职位、人才库导入、组织/人事同步等）暂未实现，详见需求文档第 3.3 节。
