# 零售全渠道运营实验库测试题库（按难度分级）

本文档用于验证当前 `lab_retail_analytics` 数据库上的 Text-to-SQL / Agent 能力。

说明：

- 以下“标准答案”基于当前本地实际数据库内容整理，而不是按造数脚本手工推断。
- 如果你重新 `restore`、`recreate`，或多次执行不同版本的 seed 流程，答案可能变化。
- 每道题后都附了“验证 SQL”，方便你人工复核 Agent 输出是否正确。

建议使用方式：

- 简单题：验证 Agent 是否能正确找表、字段、基础过滤和基础聚合
- 中等题：验证多表 join、分组聚合、金额口径理解
- 困难题：验证跨多层维度联动、业务口径选择和排序稳定性

---

## 简单

### 1. 零售库当前有多少个客户、多少张订单、多少家门店？

标准答案：

- `customer_count = 260`
- `order_count = 1400`
- `store_count = 20`

验证 SQL：

```sql
SELECT count(*) AS customer_count FROM customers;
SELECT count(*) AS order_count FROM orders;
SELECT count(*) AS store_count FROM stores;
```

### 2. 当前订单状态分布是怎样的？

标准答案：

- `cancelled`: `107`
- `completed`: `1149`
- `returned`: `144`

验证 SQL：

```sql
SELECT status, count(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;
```

### 3. 当前订单渠道分布是怎样的？

标准答案：

- `app`: `467`
- `online`: `466`
- `store`: `467`

验证 SQL：

```sql
SELECT channel, count(*) AS order_count
FROM orders
GROUP BY channel
ORDER BY channel;
```

### 4. 当前支付状态分布是怎样的？

标准答案：

- `paid`: `1149`
- `partial_refund`: `155`
- `refunded`: `96`

验证 SQL：

```sql
SELECT payment_status, count(*) AS order_count
FROM orders
GROUP BY payment_status
ORDER BY payment_status;
```

### 5. 当前客服工单按 case type 看，哪些类型未解决工单更多？

标准答案：

- `membership`: `total_cases = 32`，`unresolved_cases = 7`，`avg_resolution_hours = 32.65`
- `quality`: `total_cases = 32`，`unresolved_cases = 6`，`avg_resolution_hours = 32.33`
- `refund`: `total_cases = 32`，`unresolved_cases = 6`，`avg_resolution_hours = 32.00`
- `delivery`: `total_cases = 31`，`unresolved_cases = 6`，`avg_resolution_hours = 28.81`

验证 SQL：

```sql
SELECT
  case_type,
  count(*) AS total_cases,
  count(*) FILTER (WHERE resolution_status <> 'resolved') AS unresolved_cases,
  round(avg(resolution_hours), 2) AS avg_resolution_hours
FROM customer_service_cases
GROUP BY case_type
ORDER BY unresolved_cases DESC, total_cases DESC, case_type;
```

---

## 中等

### 6. 按大区统计，当前各区域净销售额（net amount）排名如何？

标准答案：

- `North Region`: `198220.10`
- `East Region`: `197551.80`
- `Central Region`: `196530.70`
- `South Region`: `195157.30`
- `West Region`: `193900.10`

验证 SQL：

```sql
SELECT
  r.region_name,
  round(sum(o.net_amount), 2) AS net_amount
FROM orders o
JOIN stores s ON s.id = o.store_id
JOIN regions r ON r.id = s.region_id
GROUP BY r.region_name
ORDER BY net_amount DESC, r.region_name;
```

### 7. 哪些门店的净销售额最高？

标准答案：

- `North Store 2`（`North Region`）：`net_amount = 52608.40`，`order_count = 70`
- `Central Store 1`（`Central Region`）：`52021.20`，`70`
- `East Store 4`（`East Region`）：`51322.80`，`70`
- `Central Store 3`（`Central Region`）：`50931.20`，`70`
- `South Store 1`（`South Region`）：`50520.80`，`70`

验证 SQL：

```sql
SELECT
  s.store_name,
  r.region_name,
  round(sum(o.net_amount), 2) AS net_amount,
  count(*) AS order_count
FROM orders o
JOIN stores s ON s.id = o.store_id
JOIN regions r ON r.id = s.region_id
GROUP BY s.store_name, r.region_name
ORDER BY net_amount DESC, order_count DESC, s.store_name
LIMIT 5;
```

### 8. 哪些商品类目带来的净销售额最高？

标准答案：

- `Small Leather Goods`: `100394.80`
- `Apparel`: `99229.40`
- `Accessories`: `98676.30`
- `Beauty`: `97484.70`
- `Sportswear`: `96794.00`

验证 SQL：

```sql
SELECT
  c.category_name,
  round(sum(oi.net_amount), 2) AS net_amount
FROM order_items oi
JOIN products p ON p.id = oi.product_id
JOIN categories c ON c.id = p.category_id
GROUP BY c.category_name
ORDER BY net_amount DESC, c.category_name
LIMIT 5;
```

### 9. 不同促销活动带来的订单和净销售额表现如何？

标准答案（前 5）：

- `无促销`: `order_count = 1050`，`net_amount = 741062.40`
- `Campaign 4`: `70`，`49681.10`
- `Campaign 8`: `70`，`48573.10`
- `Campaign 6`: `70`，`48529.10`
- `Campaign 10`: `70`，`46866.70`

说明：

- 当前数据里大多数订单并没有绑定 promotion
- 所以 `无促销` 是最主要的交易来源

验证 SQL：

```sql
SELECT
  COALESCE(p.promotion_name, '无促销') AS promotion_name,
  count(*) AS order_count,
  round(sum(o.net_amount), 2) AS net_amount
FROM orders o
LEFT JOIN promotions p ON p.id = o.promotion_id
GROUP BY COALESCE(p.promotion_name, '无促销')
ORDER BY net_amount DESC
LIMIT 5;
```

---

## 困难

### 10. 不同会员等级（tier）贡献的订单量和净销售额分别是多少？

标准答案：

- `standard`: `order_count = 758`，`net_amount = 530031.20`
- `silver`: `373`，`261651.60`
- `gold`: `189`，`132582.10`
- `platinum`: `80`，`57095.10`

验证 SQL：

```sql
SELECT
  c.tier,
  count(DISTINCT o.id) AS order_count,
  round(sum(o.net_amount), 2) AS net_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id
GROUP BY c.tier
ORDER BY net_amount DESC, c.tier;
```

### 11. 哪个区域的订单退货率最高？

标准答案：

- `Central Region`: `returned_orders = 29`，`total_orders = 280`，`return_rate_pct = 10.36`
- `North Region`: `29 / 280`，`10.36%`
- `South Region`: `29 / 280`，`10.36%`
- `West Region`: `29 / 280`，`10.36%`
- `East Region`: `28 / 280`，`10.00%`

说明：

- 当前数据里有 4 个区域并列最高
- 这类题目可以检验 Agent 是否能正确处理并列答案，而不是只返回一个区域

验证 SQL：

```sql
SELECT
  r.region_name,
  count(DISTINCT o.id) FILTER (WHERE o.status = 'returned') AS returned_orders,
  count(DISTINCT o.id) AS total_orders,
  round(
    100.0 * count(DISTINCT o.id) FILTER (WHERE o.status = 'returned') / count(DISTINCT o.id),
    2
  ) AS return_rate_pct
FROM orders o
JOIN stores s ON s.id = o.store_id
JOIN regions r ON r.id = s.region_id
GROUP BY r.region_name
ORDER BY return_rate_pct DESC, r.region_name;
```

### 12. 退货原因分布是怎样的？各原因对应的 approved refund amount 分别是多少？

标准答案：

- `size_mismatch`: `count = 72`，`approved_amount = 16328.05`
- `changed_mind`: `72`，`16061.28`
- `damaged`: `72`，`15892.37`
- `late_delivery`: `72`，`15868.69`

说明：

- 当前四类主要退货原因数量完全相同
- 区别主要体现在 approved refund amount 上

验证 SQL：

```sql
SELECT
  reason_code,
  count(*) AS return_count,
  round(sum(approved_amount), 2) AS approved_amount
FROM returns
GROUP BY reason_code
ORDER BY return_count DESC, approved_amount DESC;
```
