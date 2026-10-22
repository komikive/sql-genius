# 三个演示数据库总览与读库指南

这份文档的目标不是列出所有字段，而是帮你快速建立“这三个库分别在讲什么业务故事、哪些表最重要、应该从哪里开始问问题”的心智模型。

当前三个业务库分别是：

- `lab_retail_analytics` — 零售全渠道运营实验库
- `lab_healthcare_claims` — 医疗理赔风控实验库
- `lab_manufacturing_iot` — 制造物联网质量实验库

另外还有：

- `sql_agent` — 平台自己的元数据库，不是业务分析库

也就是说：

- `sql_agent` 负责存系统配置、datasource、skill、memory、history 等元信息
- 真正用于业务提问、生成 SQL、做演示的是三个 `lab_*` 数据库

---

## 1. 怎么理解这三个库

最简单的理解方式是：

### 1.1 零售库在讲“卖货与经营”

关键词：

- 门店
- 顾客
- 商品
- 订单
- 促销
- 库存
- 物流
- 退货
- 会员积分
- 售后工单

适合回答的问题：

- 哪些地区/门店营收最好
- 哪些商品类目表现更强
- 哪些活动带来了更高净销售额
- 哪些门店缺货风险高
- 哪些客户流失风险更高
- 哪些退货原因最常见

### 1.2 医疗库在讲“就诊到理赔”

关键词：

- 医院
- 科室
- 医生
- 患者
- 就诊
- 诊断
- 处置
- 理赔
- 拒付
- 事前授权
- 药房
- 照护管理

适合回答的问题：

- 哪些 payer 拒付更多
- 哪些科室 denied amount 更高
- 哪类 prior auth 最难通过
- 高风险患者是否需要更多 care management
- 某类检验异常是否和理赔表现相关

### 1.3 制造库在讲“生产与设备”

关键词：

- 工厂
- 产线
- 机器
- 传感器
- 工单
- 工序
- 停机
- 维修
- 质检
- 缺陷
- 物料批次
- 能耗
- 出货

适合回答的问题：

- 哪条产线效率最低
- 哪些机器停机最严重
- 哪种 defect 成本最高
- 哪些 sensor 经常越阈值
- 能耗最高的 plant / line 是谁
- 质量问题和停机、维修是否相关

---

## 2. 三个库的共同阅读方法

虽然业务不一样，但你可以用统一的方法读库：

1. 先找“维表”
   - 谁是谁：区域、门店、医院、产线、设备、付款方等

2. 再找“核心事实表”
   - 真正承载业务事件的表，例如 order、encounter、work_order

3. 再找“明细表 / 扩展表”
   - 比如 order_items、claim_lines、work_order_operations

4. 最后找“异常 / 风险 / 运营表”
   - 比如 returns、denials、downtime_events、care_management_events

你几乎可以把任何复杂业务问题分解成：

- 主事件是谁
- 它挂在哪些维度上
- 有哪些下钻明细
- 有哪些风险/异常/后续动作

---

## 3. 零售库：怎么读

数据库：`lab_retail_analytics`

一句话理解：

“这是一个围绕商品销售、促销、库存、会员和售后的全渠道零售运营库。”

### 3.1 主要表分层

#### 维度层

- `regions`
  - 大区
- `stores`
  - 门店
- `suppliers`
  - 供应商
- `categories`
  - 商品类目（带父子层级）
- `products`
  - 商品
- `customers`
  - 顾客
- `promotions`
  - 活动

#### 主事实层

- `orders`
  - 订单头
- `order_items`
  - 订单明细行

#### 支付/履约/退货层

- `payments`
  - 支付与退款
- `shipments`
  - 发货与配送
- `returns`
  - 退货记录

#### 运营扩展层

- `inventory_snapshots`
  - 库存快照
- `loyalty_ledger`
  - 积分流水
- `customer_service_cases`
  - 客服工单

### 3.2 业务主线怎么记

你可以把零售库记成一条消费链路：

1. 顾客 `customers`
2. 在某个门店 `stores`
3. 买了某些商品 `products`
4. 形成订单 `orders`
5. 拆成明细 `order_items`
6. 支付 `payments`
7. 发货 `shipments`
8. 可能退货 `returns`
9. 可能产生库存变化、积分变化、售后工单

### 3.3 最常用 join 路径

#### 营收分析

- `orders`
- `order_items`
- `stores`
- `regions`
- `customers`
- `products`
- `categories`
- `promotions`

#### 商品与供应链分析

- `products`
- `categories`
- `suppliers`
- `inventory_snapshots`
- `order_items`
- `returns`

#### 用户运营分析

- `customers`
- `orders`
- `loyalty_ledger`
- `customer_service_cases`

### 3.4 最值得记住的核心口径

零售库里最容易混的口径是：

- `gross_amount`
  - 毛销售额
- `discount_amount`
  - 折扣金额
- `net_amount`
  - 净销售额
- `payment_status`
  - 支付状态
- `status`
  - 订单业务状态（completed / returned / cancelled）

所以如果你要算“真实营收”，通常不能只看订单数，往往要结合：

- 订单状态
- 支付状态
- 退货情况
- 支付退款金额

### 3.5 适合演示的问题

- 最近 30 天各区域净销售额排名
- 哪些商品类目退货率最高
- 哪些门店库存周转压力最大
- 哪些活动带来的净销售额最高
- 高价值客户主要集中在哪些区域和渠道

---

## 4. 医疗库：怎么读

数据库：`lab_healthcare_claims`

一句话理解：

“这是一个围绕患者、就诊、处置、理赔、拒付和照护管理的医疗支付与风控分析库。”

### 4.1 主要表分层

#### 医疗机构层

- `hospitals`
- `departments`
- `providers`

#### 支付方层

- `payers`
- `plans`

#### 患者与临床事件层

- `patients`
- `encounters`
- `diagnoses`
- `procedures`
- `lab_results`

#### 理赔与拒付层

- `claims`
- `claim_lines`
- `denials`

#### 前置审批与运营层

- `prior_auth_requests`
- `pharmacy_fills`
- `care_management_events`

### 4.2 业务主线怎么记

医疗库最好记的一条主线是：

1. 患者 `patients`
2. 发生一次就诊 `encounters`
3. 这次就诊包含诊断 `diagnoses` 和处置 `procedures`
4. 这次就诊对应一张理赔 `claims`
5. 理赔拆成多条费用行 `claim_lines`
6. 某些费用行可能被拒付 `denials`
7. 高成本服务可能需要事前授权 `prior_auth_requests`
8. 患者后续还可能出现在 `pharmacy_fills` 和 `care_management_events`

这条链路是整个医疗库最核心的业务故事。

### 4.3 最常用 join 路径

#### 理赔风控

- `claims`
- `claim_lines`
- `denials`
- `encounters`
- `patients`
- `providers`
- `departments`
- `hospitals`
- `payers`
- `plans`

#### 临床到财务联动

- `encounters`
- `diagnoses`
- `procedures`
- `claims`
- `claim_lines`

#### 患者运营

- `patients`
- `pharmacy_fills`
- `care_management_events`
- `lab_results`

### 4.4 最值得记住的核心口径

医疗库里最关键的金额字段是：

- `encounters.total_charge`
  - 医院侧总收费
- `encounters.total_allowed`
  - 付款方认可金额
- `claims.billed_amount`
  - 理赔申报金额
- `claims.allowed_amount`
  - 理赔认可金额
- `claims.paid_amount`
  - 最终支付金额
- `claims.denied_amount`
  - 被拒金额

医疗问题里经常会混淆“收费”、“认可”、“支付”、“拒付”四种口径。

### 4.5 适合演示的问题

- 哪些 payer 的拒付金额最高
- 哪些科室的 denied amount 更高
- 哪类 prior auth 最容易被拒
- 哪类就诊 encounter_type 的收费和认可差距更大
- 高风险患者是否有更多 open care management events

### 4.6 进一步阅读

如果你想更深入看医疗库，可以继续读：

- `docs/lab-healthcare-claims-guide.md`
- `docs/lab-healthcare-claims-test-questions.md`

这两份文档已经把 healthcare 讲得更细了。

---

## 5. 制造库：怎么读

数据库：`lab_manufacturing_iot`

一句话理解：

“这是一个围绕工厂、产线、机器、传感器、工单、停机、维修、质检和能耗的制造物联网分析库。”

### 5.1 主要表分层

#### 组织与设备层

- `plants`
- `production_lines`
- `machines`
- `sensors`

#### 生产执行层

- `work_orders`
- `work_order_operations`

#### 设备状态与维护层

- `sensor_readings`
- `downtime_events`
- `maintenance_work_orders`

#### 质量层

- `quality_inspections`
- `defects`

#### 物料与成本层

- `material_lots`
- `bom_components`

#### 能耗与交付层

- `energy_usage_hourly`
- `shipments`

### 5.2 业务主线怎么记

制造库最好记的链路是：

1. 某个工厂 `plants`
2. 下面有若干产线 `production_lines`
3. 产线上有机器 `machines`
4. 机器挂传感器 `sensors`
5. 生产任务按工单 `work_orders` 执行
6. 工单拆成工序 `work_order_operations`
7. 机器不断上报传感器读数 `sensor_readings`
8. 如果异常，可能出现停机 `downtime_events`
9. 进一步触发维修 `maintenance_work_orders`
10. 工单完成后进入质检 `quality_inspections` 和缺陷记录 `defects`
11. 还会消耗物料、产生能耗、最后出货

所以制造库的核心不是“订单”，而是“工单 + 设备状态 + 质量结果”。

### 5.3 最常用 join 路径

#### 生产效率分析

- `work_orders`
- `work_order_operations`
- `production_lines`
- `plants`

#### 设备可靠性分析

- `machines`
- `sensors`
- `sensor_readings`
- `downtime_events`
- `maintenance_work_orders`

#### 质量成本分析

- `work_orders`
- `quality_inspections`
- `defects`
- `bom_components`
- `material_lots`

#### 能耗与交付分析

- `energy_usage_hourly`
- `plants`
- `production_lines`
- `shipments`
- `work_orders`

### 5.4 最值得记住的核心口径

制造库里经常会混淆的口径包括：

- `planned_units` vs `actual_units`
- `planned_minutes` vs `actual_minutes`
- `minutes_lost`
- `defect_rate`
- `defect_cost`
- `kwh_used` / `peak_kw` / `co2_kg`
- `on_time_flag`

所以制造分析经常围绕几个主题：

- 效率差距
- 停机损失
- 缺陷损失
- 能耗成本
- 交付准时率

### 5.5 适合演示的问题

- 哪些机器停机最严重
- 哪条产线实际工时偏差最大
- 哪类 defect 成本最高
- 哪个 plant 能耗最高
- 质量 warning / fail 是否和停机或维修更相关

---

## 6. 三个库怎么对照着记

如果你怕三个库记混，可以只记“主事件”这个维度：

- 零售库主事件：`orders`
- 医疗库主事件：`encounters` / `claims`
- 制造库主事件：`work_orders`

也可以记“异常表”：

- 零售：`returns`, `customer_service_cases`
- 医疗：`denials`, `prior_auth_requests`, `care_management_events`
- 制造：`downtime_events`, `maintenance_work_orders`, `defects`

还可以记“最容易出结果的分析主题”：

- 零售：营收 / 活动 / 库存 / 退货
- 医疗：理赔 / 拒付 / 事前授权 / 高风险患者
- 制造：停机 / 维修 / 缺陷 / 能耗 / 准交

---

## 7. 如果你现在要开始自己熟悉这三个库，最好的方式是什么

我建议你不要一上来就试图记所有字段，而是按下面顺序。

### 第一步：每个库先记 5 张最关键表

零售：
- `stores`
- `products`
- `customers`
- `orders`
- `order_items`

医疗：
- `patients`
- `encounters`
- `claims`
- `claim_lines`
- `denials`

制造：
- `production_lines`
- `machines`
- `work_orders`
- `downtime_events`
- `quality_inspections`

### 第二步：理解主业务链路

你不需要一开始全记住字段，但一定要记住：

- 主事件表是谁
- 明细表是谁
- 风险/异常表是谁

### 第三步：开始练问题，而不是背 schema

比如每个库先练 5 个问题：

零售：
- 区域营收
- 门店表现
- 类目退货率
- 活动净销售额
- 库存压力

医疗：
- payer 拒付金额
- 科室 denied amount
- prior auth 通过率
- 高风险患者 open care event
- encounter 收费 vs 认可金额

制造：
- 停机最多机器
- 工单延期最多产线
- defect cost 最高类型
- plant 能耗排名
- 维修成本最高机器

这会比死记字段快得多。

---

## 8. 你接下来最值得继续补的文档

如果后面你想继续把论文/答辩材料做扎实，我建议再补两类文档：

1. 每个库一份测试题库
   - retail 一份
   - manufacturing 一份
   - healthcare 你已经有了

2. 每个库一张“业务主线 + 关键 join 路径”图
   - 对答辩非常有帮助
   - 对你自己熟悉库也很有帮助

---

## 9. 数据来源说明

这三个库当前都是由下面脚本生成的：

- `backend/provision_complex_postgres_labs.py`

其中：

- retail summary：零售订单、库存、促销、会员与售后混合场景
- healthcare summary：患者、就诊、诊断、处置、理赔、拒付、药房、prior auth
- manufacturing summary：工厂、产线、工单、设备传感器、停机、维修、质检、能源使用

所以如果以后你重新跑 `--recreate`，数据规模和分布可能略有变化，但整体业务结构不会变。
