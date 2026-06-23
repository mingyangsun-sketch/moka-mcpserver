# Moka MCP Server — 需求分析与技术调研

> 文档版本：v0.1（初稿）  
> 日期：2026-06-10  
> 状态：需求规划阶段，尚未进入开发

---

## 一、项目背景与目标

### 1.1 背景

Moka 是国内主流的 HR SaaS 招聘管理系统，提供候选人管理、职位管理、面试流程、Offer 管理、人才库等核心招聘能力。Moka 目前**没有官方的 MCP Server**（已于 2026-06-10 确认），也没有社区第三方实现。

本项目的目标是基于 Moka 开放 API，搭建一个 MCP（Model Context Protocol）Server，使 AI 助手（如 Claude、Cursor 等）能够直接与 Moka 系统交互，实现招聘流程的智能化辅助。

### 1.2 目标用户

- HR 团队：通过 AI 助手快速查询候选人状态、职位进展
- 面试官/用人经理：通过自然语言查询自己负责的职位和候选人
- 管理层：通过对话获取招聘数据概览

### 1.3 第一阶段定位

**只做基础读取类操作**，不涉及高危写入（如删除候选人、修改 Offer）。优先保证数据安全，降低接入风险。

---

## 二、Moka API 技术调研

### 2.1 API 体系概览

Moka 提供三套 API 文档，面向不同场景：

| 文档 | 端点 | 适用场景 |
|------|------|----------|
| **v1（主力）** | `api.mokahr.com/api-platform/v1` | 企业客户集成，覆盖全部招聘模块 |
| **v2** | 同上，部分接口路径不同 | 候选人信息获取、组织架构/用户同步、Offer 字段（偏 eHR 场景） |
| **Open Platform** | 同上 | 第三方供应商接入（考试、背调、视频面试），**本项目不使用** |

**本项目主要使用 v1 API。**

### 2.2 认证机制

Moka 企业版 API 支持两种认证方式：

#### 方式 A：Basic Auth（推荐，v1 主力接口）

```
Authorization: Basic base64(api_key + ":")
```

- API Key 由 CSM（客户成功经理）发放
- 无过期时间，适合服务端长期使用
- 大部分 v1 接口使用此方式

#### 方式 B：OAuth2（Open Platform 接口）

```
Authorization: Bearer {accessToken}
```

- 需要 clientId + clientSecret，通过 OAuth 流程获取 accessToken
- accessToken 有效期 2 小时，需定期用 refreshToken 刷新
- refreshToken 有效期 60 天

**MCP Server 建议使用 Basic Auth**，实现简单且无需处理 token 刷新。

### 2.3 API 环境

| 环境 | Base URL |
|------|----------|
| 正式 | `https://api.mokahr.com/api-platform/v1` |
| 测试 | `https://api-staging-3.mokahr.com/api-platform/v1` |

### 2.4 通用约束

- 响应格式：JSON，UTF-8 编码
- 空值返回 `null`，空数组返回 `[]`
- 分页：大部分列表接口使用 `next` 游标分页，单次最多 20-100 条
- 频率限制：部分接口有频率限制（如 HC 写入 1 分钟 30 次）
- Webhook 推送：支持事件驱动的主动推送（候选人阶段变化等）

### 2.5 API 能力全景

以下是 Moka v1 API 提供的全部模块：

| 模块 | 读取 | 写入 | 备注 |
|------|------|------|------|
| 候选人（Candidate） | ✅ 丰富 | ✅ 部分 | 核心模块，字段极多 |
| 职位（Job） | ✅ | ✅ 创建/更新 | 支持查询、创建、更新 |
| 面试（Interview） | ✅ | ✅ | 面试安排与反馈 |
| Offer | ✅ | ✅ | 自定义字段、审批状态 |
| 入职（Onboarding） | ✅ | ✅ | 入职流程 |
| 人才库（Talent Pool） | ✅ | ✅ | 查询、归档、导入 |
| 组织架构（Department） | ✅ | ✅ 全量/增量同步 | |
| 用户（User） | ✅ | ✅ 同步 | HR/面试官/用人经理 |
| 内推（Referral） | ✅ | — | 内推账户 |
| 猎头（Agency） | ✅ | — | 猎头渠道 |
| HC（Headcount） | ✅ | ✅ 批量导入 | 编制管理 |
| BI 报表 | ✅ | — | 招聘数据分析 |
| Webhooks | — | — | 被动接收事件推送 |

---

## 三、第一阶段功能规划

### 3.1 功能选型原则

1. **只读优先**：第一阶段以查询为主，避免误操作风险
2. **高频场景**：优先覆盖 HR 和面试官日常最常用的查询场景
3. **低耦合**：每个 Tool 独立，不依赖复杂的上下文状态
4. **数据脱敏意识**：敏感字段（身份证号、手机号）需在返回时考虑脱敏策略

### 3.2 第一阶段 Tool 清单

#### 模块一：候选人查询（最高优先级）

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `search_candidates` | `GET /v1/data/ehrApplications` | 按条件搜索候选人 | stage, email, phone, movedAtStartTime, movedAtEndTime, limit |
| `get_candidate_detail` | `GET /v1/data/ehrApplications?applicationId={id}` | 获取单个候选人完整信息 | applicationId |
| `get_candidate_applications` | `GET /v1/candidates/{id}/applications` | 查询某候选人的所有申请记录 | candidateId |
| `get_candidate_stage` | `GET /v1/applications/{id}/stage` | 查询候选人当前所处阶段 | applicationId |

**返回数据要点：** 候选人信息非常丰富，包括基本信息（姓名/电话/邮箱）、教育经历、工作经历、自定义字段、所在阶段、职位信息、Offer 信息、面试官信息、内推人、附件等。

#### 模块二：职位查询

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `list_jobs` | `GET /v1/jobs/{orgId}` | 查询职位列表 | orgId, 分页参数 |
| `get_job_detail` | `GET /v1/jobs/{orgId}/{jobId}` | 获取单个职位详情 | orgId, jobId |
| `get_job_custom_fields` | `GET /v1/jobs/custom_fields` | 获取职位自定义字段定义 | — |

#### 模块三：招聘流程查询

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `list_pipelines` | `GET /v1/pipelines` | 获取招聘流程列表 | — |
| `list_stages` | `GET /v1/stages` | 获取阶段信息列表 | pipelineId |

#### 模块四：组织架构查询

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `list_departments` | `GET /v1/departments` | 查询部门列表（树形） | — |

#### 模块五：Offer 查询

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `get_offer_custom_fields` | `GET /v1/offers/custom_fields` | 获取 Offer 自定义字段定义（社招/校招） | — |

#### 模块六：人才库查询

| Tool 名称 | Moka API 端点 | 功能描述 | 输入参数 |
|-----------|---------------|----------|----------|
| `list_talent_pools` | `GET /v1/talent_pools` | 查询所有人才库 | — |
| `list_talent_pool_candidates` | `GET /v1/talent_pools/{id}/candidates` | 查询指定人才库下的候选人 | talentPoolId |

### 3.3 第二阶段预留（写入操作，暂不实现）

以下功能在第一阶段做接口调研但不实现，待需求确认后进入第二阶段：

| Tool 名称 | 功能 | 风险等级 |
|-----------|------|----------|
| `move_candidate_stage` | 将候选人推进到下一阶段 | ⚠️ 中（可回退） |
| `update_candidate_custom_fields` | 更新候选人自定义字段 | ⚠️ 中 |
| `archive_application` | 归档/淘汰候选人（可配置是否发拒信） | 🔴 高 |
| `create_job` | 创建新职位 | ⚠️ 中 |
| `add_to_talent_pool` | 将候选人移入人才库 | ⚠️ 低 |
| `import_talent` | 批量导入人才库 | 🔴 高 |
| `sync_departments` | 同步组织架构 | 🔴 高 |
| `sync_users` | 同步人事信息 | 🔴 高 |

---

## 四、核心接口详细分析

### 4.1 获取候选人信息（最核心接口）

**端点：** `GET /v1/data/ehrApplications`

**认证：** Basic Auth

**查询参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| applicationId | 二选一 | 候选人申请 ID，多个用逗号分隔（如 81,82,83） |
| stage | 二选一 | `offer`（Offer 阶段）/ `pending_checkin`（待入职）/ `all`（两者都有） |
| email | 否 | 按邮箱筛选 |
| phone | 否 | 按手机号筛选 |
| movedAtStartTime | 否 | 移动到当前阶段的开始时间 |
| movedAtEndTime | 否 | 移动到当前阶段的结束时间 |
| limit | 否 | 每页条数，默认 20，最大 20 |
| order | 否 | `DESC`（默认，从新到旧）/ `ASC`（从旧到新） |
| next | 否 | 分页游标 |

**返回数据结构（关键字段）：**

```
{
  "data": [{
    "applicationId": 47151744,        // 申请 ID
    "candidateId": 28739723,          // 候选人 ID
    "name": "张三",                    // 姓名
    "phone": "138****1111",           // 电话
    "email": "zhang@example.com",     // 邮箱
    "gender": "男",                    // 性别
    "stageName": "沟通offer",          // 当前阶段
    "source": "BOSS直聘",             // 渠道
    "academicDegree": "本科",          // 学历
    "experience": 5,                  // 工作年限
    "hireMode": 1,                    // 1=社招, 2=校招
    "job": {                          // 关联职位
      "title": "前端工程师",
      "department": "产品部",
      "jobId": "uuid..."
    },
    "offer": {                        // Offer 信息
      "approvalStatus": "APPROVED",
      "checkinDate": "2026-07-01",
      "customFields": [...]
    },
    "educationInfo": [...],           // 教育经历
    "experienceInfo": [...],          // 工作经历
    "customFields": [...],            // 自定义字段
    "interviewers": [...],            // 面试官
    "referrer": {...},                // 内推人
    "attachments": [...]              // 附件
  }],
  "next": "47168265"                  // 分页游标
}
```

**注意事项：**
- applicationId 和 stage 必须传其一
- stage 查询如果当前阶段没有候选人，会返回服务器异常（需做异常处理）
- 附件 URL 有效期为 1 小时
- 候选人头像 URL 有效期为 1 小时

### 4.2 职位查询接口

**端点：** `GET /v1/jobs/{orgId}/{jobId}`

- orgId 为组织标识
- 支持列表查询和单个查询
- 已关闭的职位如果没勾选"取消在官网显示"仍会返回
- 已删除的职位不会返回

### 4.3 组织架构同步接口

**端点（全量）：** `PUT /v1/departments`  
**端点（增量）：** `POST /v1/departments/sync/incremental`

- 全量同步：请求中未提供的部门会被标记删除
- 增量同步：只处理请求中的部门，不影响其他
- 不允许同步同名组织

### 4.4 Webhooks 推送机制

Moka 支持 Webhook 主动推送，当以下事件发生时会 POST 到配置的 URL：

- 候选人阶段变更（pushCandidate 事件）
- 候选人信息更新
- 面试安排变更

**Webhook 数据格式：**
```json
{
  "id": "uuid",
  "event": "pushCandidate",
  "triggeredAt": 1505296287,
  "data": {
    "applicationId": 12798,
    "candidateId": 8030,
    "name": "张三",
    "stageName": "面试",
    ...
  }
}
```

**安全验证：** 支持签名验证（sign = sha1(clientId + clientSecret + appId + time + body)）

> Webhook 在第一阶段可作为 MCP Resource 的数据源（实时感知候选人状态变化），但需要额外部署一个 HTTP 服务接收推送，架构复杂度较高，建议第二阶段再引入。

---

## 五、技术方案建议

### 5.1 技术栈选型

| 层级 | 推荐方案 | 备选 |
|------|----------|------|
| 语言 | TypeScript | Python |
| MCP SDK | `@modelcontextprotocol/sdk` | `mcp` (Python) |
| HTTP Client | `axios` / `node-fetch` | `httpx` (Python) |
| 运行方式 | stdio（本地）或 SSE（远程） | — |
| 配置管理 | `.env` + `dotenv` | — |

### 5.2 项目结构（建议）

```
moka-mcp-server/
├── src/
│   ├── index.ts                 # MCP Server 入口，注册所有 Tools
│   ├── config.ts                # 配置（API Key, Base URL, orgId 等）
│   ├── moka-client.ts           # Moka HTTP 客户端封装
│   │                            #   - Basic Auth 处理
│   │                            #   - 统一错误处理
│   │                            #   - 分页封装
│   │                            #   - 响应类型定义
│   ├── tools/
│   │   ├── candidates.ts        # 候选人相关 Tools
│   │   ├── jobs.ts              # 职位相关 Tools
│   │   ├── pipelines.ts         # 招聘流程 Tools
│   │   ├── departments.ts       # 组织架构 Tools
│   │   ├── offers.ts            # Offer 相关 Tools
│   │   └── talent-pools.ts      # 人才库 Tools
│   ├── types/
│   │   ├── candidate.ts         # 候选人数据类型
│   │   ├── job.ts               # 职位数据类型
│   │   └── common.ts            # 通用类型（分页、错误等）
│   └── utils/
│       ├── pagination.ts        # 分页工具（自动翻页）
│       └── sanitize.ts          # 数据脱敏（手机号、身份证）
├── package.json
├── tsconfig.json
├── .env.example                 # 配置模板
└── README.md
```

### 5.3 配置项

```env
# .env
MOKA_API_KEY=your_api_key_here
MOKA_BASE_URL=https://api.mokahr.com/api-platform/v1
MOKA_ORG_ID=your_org_id
MOKA_ENV=production                 # production | staging
MOKA_SENSITIVE_FIELDS_MASK=true     # 是否脱敏敏感字段
```

### 5.4 错误处理策略

| HTTP 状态码 | 含义 | MCP 层处理 |
|-------------|------|-----------|
| 200 | 成功 | 正常返回 |
| 401 | 认证失败 | 提示用户检查 API Key |
| 403 | 权限不足 | 提示联系 CSM 开通接口权限 |
| 404 | 资源不存在 | 返回友好提示 |
| 429 | 频率限制 | 等待后重试 |
| 500 | Moka 服务器异常 | 返回错误信息（注意 stage 查无人时也会 500） |

### 5.5 数据脱敏建议

| 字段 | 脱敏规则 |
|------|----------|
| phone | `138****1234` |
| citizenId | `4103**********2910` |
| email | 可选脱敏，默认不脱敏 |
| 附件 URL | URL 有时效性（1h），不存储 |

---

## 六、开通前的准备清单

在进入开发之前，需要完成以下准备工作：

| # | 事项 | 负责人 | 状态 |
|---|------|--------|------|
| 1 | 联系 Moka CSM 申请开通 API 权限 | HR / IT | ⬜ 待办 |
| 2 | 获取 API Key（Basic Auth 方式） | CSM 发放 | ⬜ 待办 |
| 3 | 确认 orgId（组织标识） | CSM 提供 | ⬜ 待办 |
| 4 | 确认已开通的 API 模块范围 | CSM 确认 | ⬜ 待办 |
| 5 | 申请测试环境访问权限 | CSM | ⬜ 待办 |
| 6 | 确认是否需要开通 Webhook | 内部讨论 | ⬜ 待办 |
| 7 | 确认数据脱敏策略（哪些字段对 AI 可见） | 安全/合规团队 | ⬜ 待办 |
| 8 | MCP Server 部署环境准备（本地 / 服务器） | IT | ⬜ 待办 |

---

## 七、风险与注意事项

1. **API 权限可能不全**：Moka 的 API 权限是按模块开通的，CSM 可能默认只开了部分接口。需要提前明确需要哪些模块并逐一确认。

2. **stage 为空时 API 报 500**：查询候选人时如果指定 stage 但该阶段没有候选人，Moka 会返回 500 而不是空数组。MCP Server 层需要做异常处理。

3. **分页限制**：单次最多 20 条（候选人接口），大量数据需要自动翻页。

4. **附件和头像 URL 有时效**：1 小时过期，不适合缓存。

5. **v1 和 v2 接口混用**：部分功能在 v1 和 v2 中有不同实现，需要统一使用一套，避免混淆。

6. **数据隐私合规**：候选人数据属于个人隐私数据，通过 AI 助手访问需要考虑数据安全和合规要求，建议与公司法务/合规团队确认。

---

## 附录 A：Moka API 文档链接

| 文档 | URL |
|------|-----|
| v1 API（主力） | https://www.mokahr.com/docs/api/index.html |
| v2 API | https://www.mokahr.com/docs/api/view/v2.html |
| Open Platform | https://www.mokahr.com/docs/api/view/openPlatform.html |
| 英文版 API | https://www.mokahr.com/docs/api/english.index.html |
| 用户中心文档 | https://mokahr.moyincloud.com/ |

## 附录 B：MCP 协议参考

| 资源 | URL |
|------|-----|
| MCP 官方规范 | https://modelcontextprotocol.io |
| MCP TypeScript SDK | https://github.com/modelcontextprotocol/typescript-sdk |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| 官方 MCP Servers 示例 | https://github.com/modelcontextprotocol/servers |
