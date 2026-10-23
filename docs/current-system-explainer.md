# SQL Genius 当前系统说明（面向项目作者）

这份文档不是 handoff 备忘录，而是给项目作者自己看的“当前系统到底怎么工作”的解释稿。

目标：

- 用更容易讲清的方式总结当前系统设计
- 帮助你后续写论文、做答辩、准备演示话术
- 把 Skills / Memory / QA 三层关系讲顺

---

## 1. 这个系统现在到底是什么

`SQL Genius` 已经不是一个“用户提问 -> prompt -> 直接生成 SQL”的简单 Text-to-SQL 系统。

它现在更接近一个：

- 面向单个 datasource 运行的自主型数据库 Agent
- 通过工具循环自主决定什么时候看 schema、什么时候看技能、什么时候回忆历史经验、什么时候执行 SQL
- 在回答结束后，还会把高价值经验继续沉淀回系统资产层

从产品视角看，它有两条主线：

1. 在线回答主线
   - 用户提问
   - Agent 调用工具理解上下文
   - 生成并执行 SQL
   - 返回答案与可观察 trace

2. 运行后学习主线
   - 回顾本轮对话和 SQL 结果
   - 提炼稳定知识、案例或技能草稿
   - 更新主记忆 / QA 案例层 / 技能草稿层

所以你现在做的东西，本质上是：

“一个带运行时学习能力、带知识资产分层、带可观察执行轨迹的 Text-to-SQL Agent 产品。”

---

## 2. 为什么系统从 domain-centered 变成 datasource-centered

旧思路更像：

- 按领域（domain）组织知识
- 再根据问题尝试路由到某个 domain

现在的思路是：

- 每个 datasource 自己形成一套独立的知识资产
- 用户问这个 datasource 的问题时，系统优先使用该 datasource 的上下文、技能、记忆和历史

这样做的好处是：

1. 更符合真实使用场景
   - 用户通常是在“某个具体数据库”上问问题，而不是先声明一个抽象领域

2. 上下文更精准
   - schema、口径、历史问法、技能，都天然带 datasource 边界

3. 更适合持续学习
   - 某个 datasource 里积累出来的经验，不会污染另一个 datasource

所以现在系统里最重要的作用域单位不是 domain，而是 datasource。

---

## 3. 当前主运行链路

可以把当前运行链路理解成下面这条主线：

1. 用户在 Workbench 提问
2. 请求进入 autonomous database agent
3. Agent 在一个 LLM + Tool Loop 中自主决定动作
4. 它会按需要调用工具，例如：
   - `introspect_schema`
   - `search_skills`
   - `search_skill_documents`
   - `recall_memory`
   - `search_history`
   - `search_qa_examples`
   - `execute_query`
   - `save_memory`
5. Agent 组织信息后生成 SQL
6. SQL 经安全约束检查后执行
7. 返回答案、SQL、解释与 trace
8. 本轮结束后进入 learning review
9. 高价值内容被沉淀到对应资产层

你可以把它理解为：

“主回答链路负责当前正确回答，学习链路负责让下一次更容易答对。”

---

## 4. Skills / Memory / QA 三层到底怎么分工

这是当前系统里最关键、也最值得在答辩时重点讲清的一部分。

### 4.1 Skills：领域知识文档层

Skills 更像“给 Agent 读的结构化领域说明文档”。

它主要承载：

- 业务概述
- 核心表与关键字段
- schema notes
- 指标口径
- 业务规则
- 访谈确认事实

它不应该主要承载：

- 杂乱的历史结论
- 一次性的查询结果
- 一堆示例问答日志

一句话理解：

Skills 是“某个 datasource 下可复用的领域知识说明书”。

### 4.2 Memory：长期稳定知识层

主记忆现在是：

- 每个 datasource 一份 Agent-maintained Markdown document
- 真实 source of truth 是 document metadata 里的 `memory_items`
- Markdown 更偏展示和可观察产物

它主要保存：

- 长期稳定的全局业务口径
- 关键表关系
- 查询注意事项
- 跨会话仍然有效的事实结论

它不应该保存：

- 临时结果
- 只对某一次问题成立的结论
- 原始问答日志

一句话理解：

Memory 是“该 datasource 的长期稳定背景知识前缀”。

### 4.3 QA：运行时案例层

QA 现在已经从 Skills 中独立出来。

它主要保存：

- 来自真实运行中的高价值问答对
- 相似问题的参考问法
- 可复用 SQL 案例
- 一些补充 note 与 scenario tags

它的来源是：

- 真实问答运行后，learning review 高置信自动沉淀
- 或审批通过后沉淀

它不是：

- onboarding 预造的模板案例
- 技能文档正文的一部分

一句话理解：

QA 是“来源于真实使用的案例资产层”。

---

## 5. 为什么不能把这三层混在一起

如果把 Skills / Memory / QA 混在一起，会出现三个问题。

### 5.1 如果把 QA 塞进 Skills

问题：

- 技能文档会越来越像杂乱案例堆
- 领域知识和案例检索目标不同
- 技能文档会越来越膨胀，不利于 Agent 稳定读取

### 5.2 如果把所有稳定知识都塞进 QA

问题：

- QA 是案例，不是全局口径
- 案例更适合相似问法召回，不适合作为稳定前缀知识

### 5.3 如果把所有历史结论都塞进 Memory

问题：

- 主记忆会膨胀
- 容易被一次性结果污染
- 会变成“杂乱日志库”而不是“长期稳定知识前缀”

所以三层分工的核心逻辑是：

- Skills：规则与说明
- Memory：长期稳定事实
- QA：真实案例

---

## 6. 当前记忆设计为什么更像 Hermes，但又不是照搬 Hermes

Hermes 给你的启发主要有三个：

1. 持久记忆应该是稳定前缀，不是临时聊天噪声
2. 会话历史检索要和主记忆区分开
3. 学习闭环应该是系统行为的一部分，而不是全靠人工维护

但你的系统和 Hermes 不同在于：

- Hermes 的 `MEMORY.md` 偏短、偏人为策展
- 你的 datasource memory 更动态、和业务数据库绑定更强
- 你的系统还要兼顾 SQL 生成与表结构理解

所以你现在采用的是更适合当前产品的折中方案：

- `memory_items` 做 source of truth
- recall 走 item-level
- Markdown 负责展示与产品化观察
- memory context 用 fenced block 注入，避免被误当成用户新输入

这其实是一个很合理的演进版本。

---

## 7. 当前 learning loop 怎么理解

当前 learning loop 可以理解成四层：

1. 回答前学习
   - recall memory
   - recall history
   - activate skills

2. 回答中学习
   - Agent 在工具循环里根据问题逐步判断该看什么

3. 回答后学习
   - learning review 判断这轮有没有稳定事实、案例、技能草稿可沉淀

4. 跨会话学习
   - 下次遇到相似问题时，这些沉淀会重新被召回

所以它不是“训模型”，而是“让系统资产变得越来越有用”。

---

## 8. 当前前端为什么要强调 observability

因为你的系统已经不是一个黑盒 SQL 生成器了。

它在演示时最强的地方不是“能写 SQL”，而是：

- 它能展示自己做了什么
- 它能说明自己为什么这么做
- 它能展示技能激活、记忆命中、证据检索、SQL 生成、主记忆维护

这对答辩非常重要，因为它让系统看起来：

- 可解释
- 可观察
- 可验证
- 有持续学习能力

所以 Workbench trace 其实是产品的一部分，不只是 debug 面板。

---

## 9. 你在答辩时可以怎么概括这套架构

你可以用下面这段比较自然的话来讲：

“我的系统已经从传统的一次性 Text-to-SQL 生成器，演进为一个面向 datasource 的自主型数据库 Agent。它不仅能结合 schema、技能文档、历史记忆和历史对话来生成 SQL，还能在运行后自动沉淀长期稳定知识与高价值问答案例，从而形成一个持续进化的知识闭环。为了避免不同类型知识互相污染，我把系统资产明确分成 Skills、Memory 和 QA 三层：Skills 负责领域规则与文档说明，Memory 负责稳定全局知识，QA 负责来自真实运行的案例资产。”

这个说法基本能把你现在最核心的系统价值讲出来。

---

## 10. 当前最值得继续做的事

如果后面继续推进，我觉得优先级最高的是：

1. 用真实问题压测三个 lab datasource
   - 看主记忆是否过度写入
   - 看 QA 是否沉淀得太多或太少
   - 看 history / memory / QA / skills 是否分工清晰

2. 补论文和答辩材料
   - 把这份文档里的逻辑转成更正式的论文章节
   - 配上架构图、流程图、学习闭环图

3. 继续打磨 Workbench observability
   - 让“技能激活 / 记忆命中 / 历史命中 / QA 命中 / SQL 生成”更容易一眼读懂

---

## 11. 推荐搭配阅读

如果你接下来要继续理解项目，建议按这个顺序读：

1. `docs/agent-architecture-reference.md`
   - 看 deepagents / hermes 给你的架构启发

2. `docs/skill-studio-rollout.md`
   - 看从旧架构迁移到当前 datasource-centered 架构的历史脉络

3. `docs/lab-databases-overview.md`
   - 看三个演示数据库的业务语义和表关系
