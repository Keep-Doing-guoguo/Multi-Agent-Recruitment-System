# 多 Agent 项目产品需求分析

这份文档用于沉淀 **简历筛选 + 面试辅助系统** 的产品需求分析和技术路线设计。  
目标是把招聘初筛、匹配分析、面试辅助和结果汇总拆成多个职责清晰的 Agent，形成一个工程化的多 Agent 招聘辅助系统。

---

## 当前实现状态 / Current Implementation

当前代码已按 **LangGraph + Multi-Agent + Tools** 的组织架构实现了可运行 workflow。  
The current implementation uses a **LangGraph + Multi-Agent + Tools** architecture.

```text
上传/输入简历文件或文本 + JD 文件或文本
Upload/input resume file or text + JD file or text
  ↓
LangGraph Workflow Orchestrator
LangGraph 工作流编排器
  ↓
message_router / 消息路由器
  ├─ answer_from_state / 基于已有状态回答
  │  Answer follow-up questions from existing state without rerunning agents
  ├─ resume_intake / 简历接收与解析入口
  │  Handle new resume upload or resume re-parsing
  ├─ job_matching / 岗位匹配
  │  Rerun matching when JD or matching criteria changes
  ├─ screening / 初筛判断
  │  Rerun screening when screening criteria changes
  ├─ interview / 面试计划生成
  │  Generate or refine interview questions
  ├─ supervisor / 总控复核
  │  Produce final review, recommendation, or risk validation
  └─ direct_answer / 直接回答
     Answer general questions without entering business agents
  ↓
Resume Intake Agent / 简历接收 Agent
  ├─ 决策 / Decision: 判断文件类型、选择解析工具、判断是否像简历
  │  Decide file type, choose extraction tool, classify whether content is a resume
  ├─ Text Parser Tool / 文本解析工具
  ├─ PDF Parser Tool / PDF 解析工具
  ├─ DOCX Parser Tool / DOCX 解析工具
  └─ Multimodal Tool / 多模态解析工具
  ↓
Resume Parsing Agent / 简历结构化解析 Agent
  ├─ 决策 / Decision: 是否使用 LLM、LLM 输出是否有效、是否 fallback
  │  Decide whether to use LLM, validate output, and fallback when needed
  └─ Resume Field Extractor Tool / 简历字段抽取工具
  ↓
Job Matching Agent / 岗位匹配 Agent
  ├─ 决策 / Decision: 匹配分、命中项、缺失项和风险解释
  │  Decide match score, matched requirements, missing requirements, and risk explanation
  ├─ JD Parser Tool / JD 解析工具
  └─ Match Scoring Tool / 匹配评分工具
  ↓
Screening Agent / 初筛 Agent
  ├─ 决策 / Decision: 推荐面试、人工复核或暂不推荐
  │  Decide recommend interview, manual review, or not recommended
  └─ Screening Rule Engine / 初筛规则引擎
  ↓
Interview Agent / 面试计划 Agent
  ├─ 决策 / Decision: 选择面试策略、关注点和追问方向
  │  Decide interview strategy, focus areas, and follow-up directions
  └─ Question Generation Tool / 面试问题生成工具
  ↓
Supervisor Agent / 复核 Agent
  ├─ 决策 / Decision: 最终建议、是否需要人工复核
  │  Decide final recommendation and whether human review is required
  └─ Review / Decision Policy / 复核与决策策略
  ↓
输出匹配报告 / 初筛建议 / 面试计划 / 最终复核建议
Output matching report / screening advice / interview plan / final review
```

### 架构分层 / Architecture Layers

| 层级 | Layer | 职责 |
|---|---|---|
| LangGraph Workflow Orchestrator | LangGraph 工作流编排器 | 控制节点顺序、条件分支、提前结束和最终状态汇总 |
| Message Router | 消息路由器 | 判断用户新消息是否进入 Agent workflow，以及从哪个节点开始 |
| Agent | Agent / 智能体节点 | 在自己的职责边界内做局部决策，并组织工具或 LLM 调用 |
| Tool | Tool / 工具 | 执行具体能力，例如文档提取、PDF 解析、DOCX 解析、JD 解析、评分、问题生成 |
| LLM Client | LLM 客户端 | 负责 prompt 调用、结构化 JSON 返回和错误兜底 |
| State | 状态对象 | 在节点之间传递 `candidate_profile`、`match_result`、`screening_result` 等结构化结果 |

核心原则 / Core principle:

```text
Workflow 决定流程走向
Agent 决定局部业务策略
Tool 执行具体动作

Workflow controls the process.
Agent makes local business decisions.
Tool performs concrete actions.
```

这一版默认支持 `.txt` / `.md` / `.csv` / `.json` 等文本文件和直接输入文本；PDF、图片、DOCX 等文件类型已经预留 `MultimodalExtractor` 适配器接口，后续可以接入多模态大模型、OCR 或文档解析服务。

默认实现不依赖外部 LLM API，方便先验证 workflow、状态对象和结构化输出。后续可以在不改变 workflow 契约的前提下，把 `Document Extraction Agent` 或其他单个 Agent 内部替换成模型调用。

编排层已由 LangGraph 实现，`RecruitmentWorkflow` 只是兼容包装器。当前图节点包括：

```text
resume_intake → resume_parsing → jd_extraction → job_matching → screening → interview → supervisor
```

其中 `resume_intake`、`resume_parsing` 和 `jd_extraction` 后有条件边：如果文件解析失败、不是简历或 JD 为空，会直接结束并返回 `errors`。

### 多轮消息路由 / Multi-turn Message Routing

多轮对话时，用户的新消息不应该默认重跑完整 workflow。系统应先进入 `message_router` 判断路由。  
For multi-turn conversations, a new user message should not automatically rerun the full workflow. It should first enter `message_router`.

```text
message_router / 消息路由器
├─ answer_from_state / 基于已有状态回答
├─ resume_intake / 简历接收与解析入口
├─ job_matching / 岗位匹配
├─ screening / 初筛判断
├─ interview / 面试计划生成
├─ supervisor / 总控复核
└─ direct_answer / 直接回答
```

路由含义 / Route meaning:

| Route | 中文 | 什么时候使用 |
|---|---|---|
| `answer_from_state` | 基于已有状态回答 | 用户询问已有结论原因，例如“为什么建议人工复核？” |
| `resume_intake` | 简历接收与解析入口 | 用户上传新简历，或要求重新解析简历 |
| `job_matching` | 岗位匹配 | 用户修改 JD、调整匹配条件、要求重新匹配 |
| `screening` | 初筛判断 | 用户修改筛选标准，要求重新初筛 |
| `interview` | 面试计划生成 | 用户要求生成、调整、细化面试问题 |
| `supervisor` | 总控复核 | 用户要求最终建议、风险复核、是否人工复核 |
| `direct_answer` | 直接回答 | 普通说明性问题，不进入业务 Agent |

Router 输出建议 / Suggested router output:

```json
{
  "route": "answer_from_state",
  "reason": "用户询问已有筛选结论原因，不需要重新运行 Agent",
  "requires_agent": false,
  "required_nodes": [],
  "requires_new_input": false
}
```

重新进入局部 workflow 的例子 / Partial workflow examples:

```text
新简历 / New resume:
message_router → resume_intake → resume_parsing → jd_extraction → job_matching → screening → interview → supervisor

重新匹配 / Rematch:
message_router → jd_extraction → job_matching → screening → interview → supervisor

重新生成面试题 / Regenerate interview plan:
message_router → interview → supervisor

解释已有结论 / Explain existing result:
message_router → answer_from_state
```

职责边界 / Responsibility boundary:

```text
Resume Intake Agent 负责判断文件类型、选择解析方法、判断是否像简历
DocumentExtractionTool 只负责执行被选中的文档提取动作

Resume Intake Agent detects source type, chooses extraction method, and classifies resume-likeness.
DocumentExtractionTool only performs the selected document extraction action.
```

`DocumentExtractionAgent` 仅作为旧代码兼容别名保留，新代码应使用 `DocumentExtractionTool`。
`DocumentExtractionAgent` is kept only as a backward-compatible alias. New code should use `DocumentExtractionTool`.

### 配置 / Configuration

复制 `.env.example` 为 `.env` 后可按需配置：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `ENABLE_LLM` | `false` | 是否在支持的 Agent 中启用 Ark LLM 推理 |
| `LLM_API_KEY` | 空 | Ark API Key；为空时使用规则和工具 fallback |
| `LLM_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | Ark API 基础地址 |
| `LLM_RESPONSES_PATH` | `/responses` | Responses API 路径 |
| `LLM_FILES_PATH` | `/files` | Files API 路径 |
| `LLM_MODEL` | `doubao-seed-2-0-lite-260428` | 结构化推理模型 |
| `MULTIMODAL_MODEL` | 同 `LLM_MODEL` | 文档、图片或 URL 多模态解析模型 |
| `RECRUITMENT_DB_PATH` | `data/recruitment.sqlite3` | API 会话和消息持久化 SQLite 路径 |

### 运行示例

```bash
python -m recruitment_system.cli --resume examples/resume.txt --jd examples/jd.txt
```

使用 Ark 多模态模型解析图片 URL 或本地图片：

```bash
python -m recruitment_system.cli \
  --multimodal \
  --resume "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png" \
  --jd examples/jd.txt
```

启用 Ark LLM 驱动的 Agent 推理：

```bash
python -m recruitment_system.cli \
  --llm \
  --resume examples/resume.txt \
  --jd examples/jd.txt
```

`--llm` 会让支持的 Agent 走：

```text
prompt → LLM call → JSON schema validate → fallback to rule/tool result
```

当前接入：

- `Resume Parsing Agent`：LLM 结构化抽取，失败回退到规则字段抽取
- `Job Matching Agent`：规则评分 + LLM 解释和风险补充
- `Screening Agent`：LLM 初筛决策 + 规则 guardrail
- `Interview Agent`：LLM 面试策略和问题生成
- `Supervisor Agent`：LLM 汇总复核 + human_review policy

输出包含：

- `resume_document` / `jd_document`：文档提取结果、置信度、版面块、表格、警告和错误
- `candidate_profile`：结构化简历解析结果
- `job_profile`：结构化 JD 摘要
- `match_result`：匹配分、命中项、缺失项、风险点和摘要
- `screening_result`：初筛建议、置信度、理由、风险点和是否需要人工复核
- `interview_plan`：面试类型、策略、问题、风险验证问题和关注点
- `supervisor_review`：最终建议、决策原因、关键理由、风险和是否需要人工复核
- `run_events`：LangGraph 节点事件，用于可观察性，包括 `node_started`、`node_completed`、耗时、决策、警告和错误
- `warnings` / `errors`：流程警告和错误

### 可观察性 / Observability

每次 workflow run 都会产生结构化事件 `run_events`。  
Each workflow run emits structured `run_events`.

事件由 LangGraph 节点中的 tracer 统一记录：

```text
node_started  → 节点开始执行
node_completed → 节点完成，记录 duration_ms、decision、metadata
node_failed   → 节点异常，记录 error
```

事件示例 / Event example:

```json
{
  "run_id": "xxx",
  "node": "screening",
  "event_type": "node_completed",
  "timestamp": "2026-05-17T10:00:00+00:00",
  "duration_ms": 12,
  "status": "completed",
  "decision": "recommend_interview",
  "metadata": {
    "confidence": 0.82,
    "requires_human_review": true
  },
  "warnings": [],
  "errors": []
}
```

这部分回答：

```text
哪个节点执行了？
执行耗时多久？
做了什么决策？
有没有 fallback、warning 或 error？
最终建议是从哪些节点结果推导出来的？
```

### 多模态扩展点

PDF、图片或 DOCX 这类文件建议通过多模态适配器接入：

```python
from pathlib import Path

from recruitment_system import DocumentExtractionTool, RecruitmentWorkflow
from recruitment_system.models import DocumentExtractionResult


class MyMultimodalExtractor:
    def extract(self, file_path: Path, purpose: str) -> DocumentExtractionResult:
        # 在这里调用多模态模型、OCR 或文档解析服务
        return DocumentExtractionResult(
            source=str(file_path),
            purpose=purpose,
            file_type=file_path.suffix.lstrip("."),
            extracted_text="模型提取出的标准化文本",
            confidence=0.9,
        )


workflow = RecruitmentWorkflow(
    document_tool=DocumentExtractionTool(multimodal_extractor=MyMultimodalExtractor())
)
state = workflow.run("resume.pdf", "jd.txt")
```

项目也内置了 Ark Responses API 适配器：

- 图片 URL：作为 `input_image.image_url` 传入
- 本地图片：转成 base64 data URL 后作为 `input_image.image_url` 传入
- 本地 PDF / DOCX / 其他文档：先通过 Files API 上传，再作为 `input_file.file_id` 传入
- 远程 PDF / DOCX / 其他文档 URL：作为 `input_file.file_url` 传入

```python
from recruitment_system import ArkMultimodalExtractor, DocumentExtractionTool, RecruitmentWorkflow

workflow = RecruitmentWorkflow(
    document_tool=DocumentExtractionTool(multimodal_extractor=ArkMultimodalExtractor())
)
state = workflow.run(
    "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png",
    "examples/jd.txt",
)
```

### 运行测试

```bash
python -m unittest discover -s tests
```

### API 接口

启动 API 服务：

```bash
uvicorn recruitment_system.api:app --reload
```

message 接口启用大模型：

```bash
ENABLE_LLM=true LLM_API_KEY=your_api_key uvicorn recruitment_system.api:app --reload
```

也可以在 `.env` 中配置 `ENABLE_LLM=true` 和 `LLM_API_KEY`。如果 `ENABLE_LLM=true` 但没有配置 `LLM_API_KEY`，message 接口会直接返回配置错误，避免静默退回规则解析。

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

上传简历并解析：

```bash
curl -X POST http://127.0.0.1:8000/api/resume/parse \
  -F "file=@examples/resume.txt"
```

创建空会话：

```bash
curl -X POST "http://127.0.0.1:8000/api/conversations?title=招聘会话"
```

查看最近会话：

```bash
curl "http://127.0.0.1:8000/api/conversations?limit=20"
```

查看某个会话及消息历史：

```bash
curl http://127.0.0.1:8000/api/conversations/{conversation_id}
```

第一次文件上传 + JD 分析：

```bash
curl -X POST http://127.0.0.1:8000/api/conversation/message \
  -F "message=请分析这份简历是否匹配这个岗位" \
  -F "jd_input=$(cat examples/jd.txt)" \
  -F "resume_file=@examples/resume.txt"
```

后续基于已有会话更新 JD：

```bash
curl -X POST http://127.0.0.1:8000/api/conversation/message/json \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "上一次返回的 conversation_id",
    "message": "JD 改了，请重新匹配",
    "jd_input": "职位: 算法工程师\n要求: Python, PyTorch, 机器学习, 深度学习\n本科及以上，3 年以上算法经验"
  }'
```

接口行为：

- 支持上传 `.txt`、`.md`、`.csv`、`.json`、`.pdf`、`.docx`
- 如果文件内容是简历，返回 `success: true` 和 `candidate_profile`
- 如果内容不像简历，返回 `success: false` 和 `message`
- 如果文件无法提取文本，返回 `success: false` 和错误信息
- 首次招聘分析必须通过 `/api/conversation/message` 上传 `resume_file`
- `/api/conversation/message/json` 仅用于已有会话的后续消息，必须提供 `conversation_id`
- 会话状态和消息历史默认持久化到 `data/recruitment.sqlite3`，可用 `RECRUITMENT_DB_PATH` 改写
- 每轮消息返回 `conversation_id`、`run_id`、`route_decision`、`data` 和最新 `conversation_state`
- 扫描版 PDF 如果没有文本层，需要 OCR 或多模态解析

---

## 一、项目名称

简历筛选 + 面试辅助系统

---

## 二、项目背景

传统招聘流程中，简历初筛和面试准备高度依赖人工，存在以下问题：

- 简历初筛效率低
- 候选人匹配判断标准不一致
- 招聘负责人很难快速聚焦关键风险点
- 面试问题准备重复且质量不稳定
- 招聘流程缺少结构化的执行记录和复盘依据

因此，适合引入多 Agent 协作模式，把简历解析、岗位匹配、筛选判断、面试辅助和最终汇总拆成多个角色来协同完成。

---

## 三、产品目标

本项目目标是构建一个多 Agent 简历筛选系统，实现以下能力：

- 自动解析候选人简历
- 自动提取候选人教育、经历、技能、项目等关键信息
- 自动对照 JD 做匹配分析
- 自动形成初筛建议
- 自动生成面试问题和追问方向
- 记录完整的筛选过程、判断依据和最终结果

---

## 四、适用场景

适合以下招聘任务：

- 技术岗位简历初筛
- 产品岗位简历初筛
- 运营岗位简历初筛
- 管理岗候选人评估
- 面试问题生成
- 批量候选人初步排序

---

## 五、核心用户

- 招聘专员
- 用人经理
- 面试官
- HRBP

---

## 六、核心输入与输出

### 输入

系统输入通常包括：

- 候选人简历文本或文件
- 岗位 JD
- 招聘规则
- 历史筛选标准
- 企业偏好条件

### 输出

系统输出通常包括：

- 简历结构化解析结果
- 岗位匹配分析
- 初筛结论
- 风险点和不足项
- 面试问题清单
- 最终筛选建议

---

## 七、多 Agent 技术路线

本项目建议严格按照以下 5 个 Agent 来拆分。

### 1. Resume Parsing Agent

负责简历解析：

- 提取候选人基本信息
- 提取教育背景
- 提取工作经历
- 提取项目经历
- 提取技能关键词

例如：

- 学历层次
- 工作年限
- 技术栈
- 行业背景
- 项目类型

---

### 2. Job Matching Agent

负责岗位匹配：

- 对照 JD 分析匹配度
- 判断候选人的核心技能是否命中
- 判断工作经历是否符合岗位要求
- 判断项目经验是否匹配

它的目标不是最终给出录用结论，而是：  
**给出岗位匹配分析依据。**

---

### 3. Screening Agent

负责初筛判断：

- 判断是否进入下一轮
- 判断是否需要人工复核
- 输出筛选理由
- 标出明显短板和风险点

---

### 4. Interview Agent

负责面试辅助：

- 基于简历内容生成针对性问题
- 基于 JD 生成能力验证问题
- 生成项目深挖问题
- 输出建议追问方向

---

### 5. Supervisor Agent

负责总控：

- 汇总各 Agent 的输出
- 做最终筛选决策
- 输出最终筛选建议或面试建议

---

### 6. Memory Module

负责共享上下文与历史信息管理：

- 保存 `session memory`
- 保存 `recent turns`
- 保存 `conversation summary`
- 保存 `run state`
- 为各 Agent 提供统一读写接口
- 控制记忆压缩、长度上限和持久化

它的目标不是直接产出业务结果，而是：  
**为所有 Agent 提供可复用的上下文和状态支持。**

推荐采用分层设计：

- `structured memory`
- `recent turns`
- `conversation summary`
- `run state`

典型保存内容包括：

- 岗位要求摘要
- 候选人结构化画像
- 历史筛选偏好
- 已确认筛选标准
- 当前 run 中间状态

---

### 7. Tool Module

负责对外部能力和内部执行能力进行统一封装：

- 简历文件解析工具
- OCR / 文本抽取工具
- 岗位 JD 检索工具
- 历史候选人对比工具
- 面试题模板工具
- 评分规则查询工具

它的目标不是做决策，而是：  
**为各 Agent 提供标准化、可观测、可校验的调用能力。**

---

### 8. Run / Workflow Module

负责整个多 Agent 系统的执行流转与运行管理：

- 创建 `session_id`
- 创建 `run_id`
- 组织当前这一次简历筛选流程
- 记录执行状态
- 控制节点流转
- 控制重试、降级、人工复核
- 对外提供进度查询和最终结果查询

它的目标是：  
**把多个 Agent、Memory、Tool 串成一个可追踪、可恢复、可观测的运行系统。**

---

## 八、推荐工作流

推荐主流程如下：

```text
导入简历 / JD
  ↓
Resume Parsing Agent
  ↓
Job Matching Agent
  ↓
Screening Agent
  ↓
Interview Agent
  ↓
Supervisor Agent
  ↓
最终筛选建议 / 面试建议 / 人工复核
```

如果需要加入循环修复，可扩展为：

```text
Resume Parsing Agent
  ↓
Job Matching Agent
  ↓
Screening Agent
  ├─ pass -> Interview Agent
  ├─ retry -> Resume Parsing Agent
  └─ manual_review -> Supervisor Agent
```

---

## 九、推荐工程化能力

如果这个项目要做成工程化 Agent 系统，建议至少具备以下能力：

- `session_id`
- `run_id`
- `structured memory`
- `recent turns`
- `conversation summary`
- `run state`
- `validator`
- `retry / fallback`
- `SSE / polling`
- `observability`

---

## 十、数据库设计

建议至少包含以下数据实体：

- `sessions`
- `messages`
- `runs`
- `run_events`
- `tool_calls`
- `candidates`
- `job_descriptions`
- `screening_results`

推荐存储内容包括：

- 候选人解析结果
- JD 结构化摘要
- 匹配评分
- 筛选结论
- 面试问题记录
- 历史 run 快照

推荐数据库选择：

- 本地开发：`SQLite`
- 中小型服务：`Postgres`
- 活跃状态和事件缓存：`Redis`

---

## 十一、接口设计

推荐至少提供以下接口。

### 1. 创建简历筛选任务

```http
POST /api/resume/runs
```

### 2. 查询任务状态

```http
GET /api/resume/runs/{run_id}
```

### 3. 获取事件流

```http
GET /api/resume/runs/{run_id}/events
```

### 4. 获取最终结果

```http
GET /api/resume/runs/{run_id}/result
```

### 5. 重新筛选或追加要求

```http
POST /api/resume/review
```

---

## 十二、可观测性设计

建议至少记录以下内容：

- `session_id`
- `run_id`
- 候选人 ID
- 岗位 ID
- 每个 Agent 的执行日志
- Tool 调用日志
- 模型调用日志
- 匹配得分与最终结论
- 平均筛选耗时

---

## 十三、风控与安全设计

简历筛选属于敏感人力场景，必须补足以下能力：

- 隐私数据脱敏
- 简历内容最小化暴露
- 筛选理由可解释
- 避免歧视性判断
- 高风险结论人工复核
- 最大重试次数和死循环保护

---

## 十四、为什么这份设计符合工程化

这份多 Agent 方案不只是“让模型读简历并给建议”，而是包含了完整工程要素：

- 明确的 Agent 分工
- 共享记忆模块
- 工具层封装
- run / workflow 执行模型
- 数据持久化设计
- 状态与事件流接口
- 可观测性设计
- 隐私与风控设计

因此它既适合作为产品需求分析，也适合作为后续工程实施蓝图。
