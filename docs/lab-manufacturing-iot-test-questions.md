# 制造物联网质量实验库测试题库（按难度分级）

本文档用于验证当前 `lab_manufacturing_iot` 数据库上的 Text-to-SQL / Agent 能力。

说明：

- 以下“标准答案”基于当前本地实际数据库内容整理，而不是按造数脚本手工推断。
- 如果你重新 `restore`、`recreate`，或多次执行不同版本的 seed 流程，答案可能变化。
- 每道题后都附了“验证 SQL”，方便你人工复核 Agent 输出是否正确。

建议使用方式：

- 简单题：验证 Agent 是否能正确找表、字段、状态分布与基础聚合
- 中等题：验证跨 plant / line / work order 的分组分析与排序能力
- 困难题：验证设备可靠性、维修成本、质量问题与传感器异常的联合理解

---

## 简单

### 1. 制造库当前有多少个工厂、多少条产线、多少台机器？

标准答案：

- `plant_count = 3`
- `line_count = 12`
- `machine_count = 60`

验证 SQL：

```sql
SELECT count(*) AS plant_count FROM plants;
SELECT count(*) AS line_count FROM production_lines;
SELECT count(*) AS machine_count FROM machines;
```

### 2. 当前工单状态分布是怎样的？

标准答案：

- `completed`: `252`
- `delayed`: `46`
- `scrapped`: `22`

验证 SQL：

```sql
SELECT work_order_status, count(*) AS work_order_count
FROM work_orders
GROUP BY work_order_status
ORDER BY work_order_status;
```

### 3. 当前产线自动化等级分布是怎样的？

标准答案：

- `fully_auto`: `3`
- `manual`: `3`
- `semi_auto`: `6`

验证 SQL：

```sql
SELECT automation_level, count(*) AS line_count
FROM production_lines
GROUP BY automation_level
ORDER BY automation_level;
```

### 4. 当前质检状态分布和平均 defect rate 是怎样的？

标准答案：

- `fail`: `count = 22`，`avg_defect_rate = 0.1800`
- `pass`: `252`，`0.0080`
- `warning`: `46`，`0.0450`

验证 SQL：

```sql
SELECT
  quality_status,
  count(*) AS inspection_count,
  round(avg(defect_rate), 4) AS avg_defect_rate
FROM quality_inspections
GROUP BY quality_status
ORDER BY quality_status;
```

### 5. 维修工单按 maintenance type 和 maintenance status 的分布是怎样的？

标准答案：

- `corrective / closed`: `61`
- `corrective / in_progress`: `15`
- `corrective / open`: `11`
- `predictive / closed`: `60`
- `predictive / in_progress`: `16`
- `predictive / open`: `11`
- `preventive / closed`: `61`
- `preventive / in_progress`: `15`
- `preventive / open`: `10`

验证 SQL：

```sql
SELECT maintenance_type, maintenance_status, count(*) AS work_order_count
FROM maintenance_work_orders
GROUP BY maintenance_type, maintenance_status
ORDER BY maintenance_type, maintenance_status;
```

---

## 中等

### 6. 各工厂的能耗和碳排放总量排名如何？

标准答案：

- `Suzhou Precision Plant`: `kwh_used = 248430.00`，`co2_kg = 111000.00`
- `Shenzhen Smart Plant`: `229950.00`，`104280.00`
- `Chengdu Assembly Plant`: `211470.00`，`117720.00`

说明：

- 苏州工厂总能耗最高
- 成都工厂总能耗最低，但 CO2 总量反而更高，说明这个库里“能耗”和“碳排”不是完全同趋势

验证 SQL：

```sql
SELECT
  p.plant_name,
  round(sum(e.kwh_used), 2) AS kwh_used,
  round(sum(e.co2_kg), 2) AS co2_kg
FROM energy_usage_hourly e
JOIN plants p ON p.id = e.plant_id
GROUP BY p.plant_name
ORDER BY kwh_used DESC;
```

### 7. 当前停机事件里，哪些 downtime reason 造成的总 minutes lost 最多？

标准答案：

- `power_fluctuation`: `count = 12330`，`minutes_lost = 941190`
- `changeover`: `12330`，`928860`
- `sensor_drift`: `12330`，`916530`
- `jam`: `12330`，`915160`

验证 SQL：

```sql
SELECT
  downtime_reason,
  count(*) AS event_count,
  sum(minutes_lost) AS minutes_lost
FROM downtime_events
GROUP BY downtime_reason
ORDER BY minutes_lost DESC;
```

### 8. 哪些产线的计划产量与实际产量差距最大？

标准答案（前 5）：

- `Shenzhen Smart Plant Line 4`: `planned_units = 52000`，`actual_units = 49390`，`unit_gap = 2610`
- `Suzhou Precision Plant Line 3`: `47520`，`45000`，`2520`
- `Suzhou Precision Plant Line 4`: `55120`，`52650`，`2470`
- `Chengdu Assembly Plant Line 2`: `41040`，`38790`，`2250`
- `Chengdu Assembly Plant Line 3`: `48880`，`46670`，`2210`

验证 SQL：

```sql
SELECT
  l.line_name,
  count(*) AS work_order_count,
  sum(wo.planned_units) AS planned_units,
  sum(wo.actual_units) AS actual_units,
  sum(wo.planned_units - wo.actual_units) AS unit_gap
FROM work_orders wo
JOIN production_lines l ON l.id = wo.line_id
GROUP BY l.line_name
ORDER BY unit_gap DESC, work_order_count DESC, l.line_name
LIMIT 5;
```

### 9. 当前晚到（on_time_flag = false）的出货主要集中在哪些目的区域？

标准答案：

- `East`: `19`
- `West`: `19`
- `North`: `18`
- `South`: `18`
- `Central`: `17`

说明：

- 当前 `East` 和 `West` 并列最多
- 这类题适合验证 Agent 是否能正确处理并列第一

验证 SQL：

```sql
SELECT destination_region, count(*) AS shipment_count
FROM shipments
WHERE on_time_flag IS FALSE
GROUP BY destination_region
ORDER BY shipment_count DESC, destination_region;
```

---

## 困难

### 10. 哪些产线同时表现出更多 fail / warning 质检结果？

标准答案（前 5）：

- `Chengdu Assembly Plant Line 2`: `fail_count = 4`，`warning_count = 23`，`avg_defect_rate = 0.0650`
- `Shenzhen Smart Plant Line 2`: `4`，`0`，`0.0335`
- `Suzhou Precision Plant Line 1`: `4`，`0`，`0.0335`
- `Suzhou Precision Plant Line 3`: `4`，`0`，`0.0335`
- `Chengdu Assembly Plant Line 4`: `3`，`23`，`0.0606`

说明：

- 这道题不是单纯看 fail 次数，而是同时结合了 warning 和平均 defect rate
- 非常适合测试 Agent 对多指标排序结果的理解能力

验证 SQL：

```sql
SELECT
  l.line_name,
  count(*) FILTER (WHERE qi.quality_status = 'fail') AS fail_count,
  count(*) FILTER (WHERE qi.quality_status = 'warning') AS warning_count,
  round(avg(qi.defect_rate), 4) AS avg_defect_rate
FROM quality_inspections qi
JOIN work_orders wo ON wo.id = qi.work_order_id
JOIN production_lines l ON l.id = wo.line_id
GROUP BY l.line_name
ORDER BY fail_count DESC, warning_count DESC, avg_defect_rate DESC, l.line_name
LIMIT 5;
```

### 11. 哪些机器的维修成本最高？

标准答案（前 5）：

- `Suzhou Precision Plant Line 2 Machine 3`: `total_cost = 14220.00`，`work_order_count = 4`
- `Suzhou Precision Plant Line 4 Machine 5`: `14220.00`，`4`
- `Shenzhen Smart Plant Line 2 Machine 3`: `13840.00`，`4`
- `Shenzhen Smart Plant Line 4 Machine 5`: `13840.00`，`4`
- `Suzhou Precision Plant Line 3 Machine 2`: `13500.00`，`5`

验证 SQL：

```sql
SELECT
  m.machine_name,
  round(sum(mwo.cost_amount), 2) AS total_cost,
  count(*) AS work_order_count
FROM maintenance_work_orders mwo
JOIN machines m ON m.id = mwo.machine_id
GROUP BY m.machine_name
ORDER BY total_cost DESC, work_order_count DESC, m.machine_name
LIMIT 5;
```

### 12. 从传感器读数质量看，哪类 sensor 的异常读数更多？

标准答案：

- `temperature`: `reading_count = 197280`，`bad_or_suspect = 8220`，`avg_reading = 47.67`
- `vibration`: `197280`，`8220`，`3.25`
- `power_draw`: `197280`，`0`，`12.97`

说明：

- 当前数据里 `temperature` 和 `vibration` 都有明显异常读数
- `power_draw` 没有 bad/suspect，适合拿来和前两类做对比

验证 SQL：

```sql
SELECT
  s.sensor_type,
  count(*) AS reading_count,
  count(*) FILTER (WHERE sr.reading_quality <> 'good') AS bad_or_suspect,
  round(avg(sr.reading_value), 2) AS avg_reading
FROM sensor_readings sr
JOIN sensors s ON s.id = sr.sensor_id
GROUP BY s.sensor_type
ORDER BY bad_or_suspect DESC, reading_count DESC, s.sensor_type;
```

### 13. 哪些机器累计停机损失时间最高？

标准答案（前 5）：

- `Shenzhen Smart Plant Line 3 Machine 2`: `minutes_lost = 72062.00`
- `Chengdu Assembly Plant Line 2 Machine 2`: `71240.00`
- `Suzhou Precision Plant Line 2 Machine 2`: `70418.00`
- `Shenzhen Smart Plant Line 2 Machine 2`: `69596.00`
- `Chengdu Assembly Plant Line 1 Machine 4`: `69322.00`

验证 SQL：

```sql
SELECT
  m.machine_name,
  round(sum(d.minutes_lost), 2) AS minutes_lost
FROM downtime_events d
JOIN machines m ON m.id = d.machine_id
GROUP BY m.machine_name
ORDER BY minutes_lost DESC, m.machine_name
LIMIT 5;
```
