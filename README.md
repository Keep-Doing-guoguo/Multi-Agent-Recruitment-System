# 多 Agent 项目产品需求分析

这份文档用于沉淀 **简历筛选 + 面试辅助系统** 的产品需求分析和技术路线设计。  
目标是把招聘初筛、匹配分析、面试辅助和结果汇总拆成多个职责清晰的 Agent，形成一个工程化的多 Agent 招聘辅助系统。

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
