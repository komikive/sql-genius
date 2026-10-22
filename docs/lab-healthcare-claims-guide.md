# 测试数据库说明与医疗理赔库详解

本文档用于说明当前本地测试库的组织方式，并重点讲清 `lab_healthcare_claims`（医疗理赔风控实验库）的业务语义、表关系和适合提问的问题。

## 1. 先回答你的疑问：这些库是不是“都在同一个数据库里”？

不是“都在同一个业务数据库里”，而是：

- 它们都运行在 **同一个 PostgreSQL 实例 / 集群** 里
- 但彼此是 **不同的 database**
- 可以把它理解成：
  - 同一台数据库服务器
  - 上面挂了多个彼此独立的业务库

当前本地实例里有这些非模板数据库：

- `sql_agent`
  - 这是产品自己的元数据库
  - 里面存的是数据源注册信息、技能包、记忆、线程摘要、学习审核等系统数据
- `lab_retail_analytics`
  - 零售实验库
- `lab_healthcare_claims`
  - 医疗理赔实验库
- `lab_manufacturing_iot`
  - 制造业物联网实验库
- `postgres`
  - PostgreSQL 自带的默认数据库

所以要点是：

- `sql_agent` 不是业务分析库，它更像“平台控制面数据库”
- 三个 `lab_*` 才是拿来提问、跑 SQL、做演示的业务库
- 当前医疗理赔库并不是 `sql_agent` 里的某些表，而是一个单独的业务 database：`lab_healthcare_claims`

## 2. 医疗理赔库定位

`lab_healthcare_claims` 是一个围绕“患者就诊 -> 诊断/处置 -> 理赔 -> 拒付 -> 事前授权 -> 药房 -> 照护管理”的综合实验库。

它并不是单纯的“医保结算表”，而是试图覆盖以下几个分析主题：

- 医院和科室运营
- 医生与专科服务供给
- 患者风险分层
- encounter 粒度的临床活动
- claim / claim line 粒度的理赔与拒付
- prior auth（事前授权）审批
- pharmacy fills（药房配药）
- care management（照护管理事件）
- lab results（检验结果）

这个库很适合做的，不只是“查费用”，还包括：

- 哪些 payer 拒付更多
- 哪些科室的 denied amount 更高
- 哪类 prior auth 最容易被拒
- 高风险患者是否有更多 open care events
- 哪些 provider 的理赔回款效率更差

## 3. 当前库的真实规模

这是当前本地已生成实例里的大致量级：

- 5 家医院
- 20 个科室
- 80 个 provider
- 4 个 payer
- 9 个 plan
- 240 个患者
- 960 次 encounter
- 720 张 claim
- 1440 条 claim line
- 48 条 denial
- 280 条 prior auth
- 520 条 pharmacy fill
- 320 条 care management event
- 2880 条 lab result

当前一些关键分布：

- encounter 类型：
  - `outpatient`: 576
  - `inpatient`: 192
  - `ed`: 192
- claim 状态：
  - `paid`: 576
  - `pending`: 96
  - `denied`: 48
- denial 类别：
  - `administrative`: 32
  - `clinical`: 16
- 高风险或复杂患者：
  - `45` 人
- 未关闭 care event：
  - `91` 条
- 未 overturn 的 denial：
  - `48` 条

## 4. 表结构怎么理解

可以把它分成 6 层。

### 4.1 医疗机构层

- `hospitals`
  - 医院主数据
- `departments`
  - 科室
- `providers`
  - 医生或服务提供者

这层回答的问题是：

- 哪家医院
- 哪个科室
- 哪位 provider
- 属于什么 specialty

### 4.2 支付方层

- `payers`
  - 付款方，例如商业险、政府险、雇主计划
- `plans`
  - 付款方下的具体保险计划

这层回答的问题是：

- 这笔业务最终向谁理赔
- 挂在哪个保险计划下
- 属于什么合同模式

### 4.3 患者与就诊层

- `patients`
  - 患者主数据
- `encounters`
  - 一次完整就诊事件
- `diagnoses`
  - encounter 下的诊断
- `procedures`
  - encounter 下的处置 / 手术 / 服务
- `lab_results`
  - encounter 下的检验结果

这一层是临床活动主线：

1. 一个 `patient`
2. 发生一次 `encounter`
3. encounter 下面有若干 `diagnoses`
4. 也有若干 `procedures`
5. 还可能伴随若干 `lab_results`

如果你问：

- “某类患者最近有哪些就诊”
- “某科室做了哪些高费用 procedure”
- “某类 abnormal lab 结果对应哪些风险患者”

通常都要从这一层开始。

### 4.4 理赔层

- `claims`
  - 理赔头
- `claim_lines`
  - 理赔行
- `denials`
  - 被拒付的理赔行事件

这是医疗财务/风控最核心的一层。

推荐把这三张表理解成：

- `claims`：一张理赔单的整体状态与金额
- `claim_lines`：理赔单里每一条收费项目
- `denials`：某条理赔行为什么被拒

常见 join 路径：

- `claims -> claim_lines`
- `claim_lines -> denials`
- `claims -> encounters`
- `encounters -> patients / providers / departments / hospitals`

如果你要分析：

- 哪家医院 denied amount 更高
- 哪类服务最容易被拒
- 哪个 payer 的 paid / denied 结构更差

通常都会走这一层。

### 4.5 事前授权层

- `prior_auth_requests`

这张表不依赖 claim 本身，它更像“理赔前置审批”。

适合分析：

- 哪类 service type 最难获批
- 不同 payer / plan 的 auth 通过率
- denied 和 partially approved 的金额缺口

### 4.6 药房与照护层

- `pharmacy_fills`
  - 药房配药和依从性
- `care_management_events`
  - 护理 / 风险干预 / 协调事件

这层适合做：

- 高风险患者是否存在依从性缺口
- 哪些患者有 open 的 care management 任务
- 药费和慢病风险是否相关

## 5. 关键业务主线

如果你把这个库当成一个业务故事来记，最重要的是下面这条链路：

1. 患者在 `patients`
2. 患者发生一次 `encounter`
3. encounter 产生 `diagnoses` / `procedures` / `lab_results`
4. encounter 对应一张 `claim`
5. claim 拆成多条 `claim_lines`
6. 部分 claim line 会进入 `denials`
7. 高成本服务可能在事前就需要 `prior_auth_requests`
8. 患者后续还可能出现在 `pharmacy_fills` 和 `care_management_events`

这条链路是整个库最适合演示 Agent 能力的地方，因为它天然需要跨表推理。

## 6. 最常用的 join 路径

### 6.1 理赔风控分析

- `claims c`
- `claim_lines cl ON cl.claim_id = c.id`
- `denials d ON d.claim_line_id = cl.id`
- `encounters e ON e.id = c.encounter_id`
- `patients p ON p.id = e.patient_id`
- `providers pr ON pr.id = e.provider_id`
- `departments dept ON dept.id = e.department_id`
- `hospitals h ON h.id = e.hospital_id`
- `payers py ON py.id = c.payer_id`
- `plans pl ON pl.id = c.plan_id`

### 6.2 临床到财务联动分析

- `encounters`
- `diagnoses`
- `procedures`
- `claims`
- `claim_lines`

适合问：

- 哪类诊断对应更高的拒付率
- 哪类处置 billed amount 高但 paid amount 低

### 6.3 高风险患者运营分析

- `patients`
- `encounters`
- `pharmacy_fills`
- `care_management_events`
- `prior_auth_requests`

适合问：

- 高风险患者有没有更多 open event
- 依从性缺口和理赔表现是否相关

## 7. 我建议你把这些表分组记忆

如果你不想一次记 16 张表，可以先只记 5 个锚点：

- `patients`
  - 人
- `encounters`
  - 一次医疗事件
- `claims`
  - 一张理赔单
- `claim_lines`
  - 理赔单的具体收费项目
- `denials`
  - 为什么被拒

然后再把其余表当成补充维度：

- 机构维度：`hospitals` / `departments` / `providers`
- 支付维度：`payers` / `plans`
- 临床维度：`diagnoses` / `procedures` / `lab_results`
- 运营维度：`prior_auth_requests` / `pharmacy_fills` / `care_management_events`

## 8. 适合用来测试 Agent 的问题

下面这些问题很适合演示当前系统：

- 最近 90 天按 payer 统计 claim 数量、paid amount 和 denied amount
- 哪些医院或科室的 denied amount 最高
- 哪些 denial category 最常见，对应哪些 payer
- 高风险患者中，哪些人既有 open care event，又有较高的 adherence gap
- 哪类 prior auth service 最容易被拒或部分批准
- 不同 encounter type 的平均 total_charge、allowed_amount 和 paid_amount 对比
- 某个 provider 或 specialty 的理赔通过率如何

## 9. 当前数据的几个“设计性特征”

这是实验库，不是来自真实医院 HIS / claim clearinghouse，所以有一些明显的“教学型”结构：

- 它是强结构化、强主外键约束的
- 编码字段设计得比较规整，便于 Agent 学会 join
- encounter 到 claim 的关系较清晰，适合演示跨层推理
- denial 是 line-level 事件，而不是单独的 claim 备注
- prior auth、pharmacy、care management 被刻意保留下来，方便做更复杂的跨主题问题

所以这套库非常适合：

- thesis defense demo
- agent tool reasoning demo
- 多表 SQL 质量验证
- 技能包与 memory 效果验证

## 10. 现在 Agent 能不能看到注释？

在本次更新之后：

- 医疗理赔库会补上表与字段注释
- schema introspection 会把注释采集进 snapshot
- autonomous agent 的 schema overview 也会把表/字段注释带进运行上下文

这意味着：

- Agent 在运行时可以看到这些注释
- onboarding 分析也可以利用这些注释
- 后续手动查看 schema snapshot 时，也能看到更完整的业务语义

如果你后面想继续增强，我建议下一步可以做：

- 在前端 schema 树里直接显示表/字段注释
- 在 Workbench trace 中单独展示“Agent 参考了哪些 schema 注释”
- 为零售库和制造库也补齐同级别注释
