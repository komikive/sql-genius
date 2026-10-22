# 医疗理赔库测试题库（按难度分级）

本文档用于验证当前 `lab_healthcare_claims` 数据库上的 Text-to-SQL / Agent 能力。

说明：

- 以下“标准答案”基于**当前本地实际数据库内容**整理，而不是按造数脚本手工推断。
- 如果你重新 `restore`、`recreate`、或多次执行不同版本的 seed 流程，答案可能变化。
- 每道题后都附了“验证 SQL”，用于人工复核 Agent 输出是否正确。

建议使用方式：

- 简单题：先验证 Agent 是否能正确找表、字段、基础聚合
- 中等题：验证多表 join、分组聚合、金额口径
- 困难题：验证多跳 join、业务口径理解、并列答案处理

---

## 简单

### 1. 医疗理赔库当前有多少个患者？

标准答案：

- `240`

验证 SQL：

```sql
SELECT count(*) AS patient_count
FROM patients;
```

### 2. 医疗理赔库当前有多少次就诊（encounter）？

标准答案：

- `960`

验证 SQL：

```sql
SELECT count(*) AS encounter_count
FROM encounters;
```

### 3. 当前就诊类型分布是怎样的？

标准答案：

- `ed`: `192`
- `inpatient`: `192`
- `outpatient`: `576`

验证 SQL：

```sql
SELECT encounter_type, count(*) AS encounter_count
FROM encounters
GROUP BY encounter_type
ORDER BY encounter_type;
```

### 4. 当前理赔单（claim）状态分布是怎样的？

标准答案：

- `denied`: `48`
- `paid`: `576`
- `pending`: `96`

验证 SQL：

```sql
SELECT claim_status, count(*) AS claim_count
FROM claims
GROUP BY claim_status
ORDER BY claim_status;
```

### 5. 当前一共有多少条拒付记录（denial）？按类别怎么分布？

标准答案：

- 总拒付记录数：`48`
- `administrative`: `32`
- `clinical`: `16`

验证 SQL：

```sql
SELECT count(*) AS denial_count
FROM denials;

SELECT denial_category, count(*) AS denial_count
FROM denials
GROUP BY denial_category
ORDER BY denial_category;
```

---

## 中等

### 6. 不同就诊类型的平均收费金额和平均认可金额分别是多少？

标准答案：

- `ed`: 平均 `total_charge = 1415.08`，平均 `total_allowed = 1102.01`
- `inpatient`: 平均 `total_charge = 1391.21`，平均 `total_allowed = 1083.65`
- `outpatient`: 平均 `total_charge = 1489.92`，平均 `total_allowed = 1161.71`

验证 SQL：

```sql
SELECT
  encounter_type,
  round(avg(total_charge), 2) AS avg_total_charge,
  round(avg(total_allowed), 2) AS avg_total_allowed
FROM encounters
GROUP BY encounter_type
ORDER BY encounter_type;
```

### 7. 按付款方（payer）统计，当前各自的 claim 数量、总申报金额、总支付金额、总拒付金额分别是多少？

标准答案：

- `Evercare Commercial`: `claim_count = 240`，`total_billed = 343623.00`，`total_paid = 191010.96`，`total_denied = 5509.66`
- `Harmony Commercial`: `claim_count = 240`，`total_billed = 352668.00`，`total_paid = 192448.87`，`total_denied = 6374.13`
- `National Resident Plan`: `claim_count = 240`，`total_billed = 353271.00`，`total_paid = 191820.09`，`total_denied = 5857.14`

说明：

- 当前 `claims` 表里实际只落到了这 3 个 payer，没有出现第 4 个 payer 的 claim。

验证 SQL：

```sql
SELECT
  p.payer_name,
  count(*) AS claim_count,
  round(sum(c.billed_amount), 2) AS total_billed,
  round(sum(c.paid_amount), 2) AS total_paid,
  round(sum(c.denied_amount), 2) AS total_denied
FROM claims c
JOIN payers p ON p.id = c.payer_id
GROUP BY p.payer_name
ORDER BY claim_count DESC, p.payer_name;
```

### 8. 当前 prior authorization 的状态分布是怎样的？

标准答案：

- `approved`: `149`
- `denied`: `31`
- `partially_approved`: `50`
- `pending`: `50`

验证 SQL：

```sql
SELECT auth_status, count(*) AS auth_count
FROM prior_auth_requests
GROUP BY auth_status
ORDER BY auth_status;
```

### 9. 按理赔状态统计，总申报金额、总支付金额、总拒付金额分别是多少？

标准答案：

- `denied`: `claim_count = 48`，`total_billed = 26530.00`，`total_paid = 0.00`，`total_denied = 17740.93`
- `paid`: `claim_count = 576`，`total_billed = 844621.00`，`total_paid = 575279.92`，`total_denied = 0.00`
- `pending`: `claim_count = 96`，`total_billed = 178411.00`，`total_paid = 0.00`，`total_denied = 0.00`

验证 SQL：

```sql
SELECT
  claim_status,
  count(*) AS claim_count,
  round(sum(billed_amount), 2) AS total_billed,
  round(sum(paid_amount), 2) AS total_paid,
  round(sum(denied_amount), 2) AS total_denied
FROM claims
GROUP BY claim_status
ORDER BY claim_status;
```

### 10. 哪个科室的拒付金额最高？

标准答案：

- 第 1 名：`Emergency`，`total_denied_amount = 6374.13`
- 第 2 名：`Oncology`，`total_denied_amount = 5857.14`
- 第 3 名：`Cardiology`，`total_denied_amount = 5509.66`

说明：

- 当前只有这 3 个科室产生了非零拒付金额。

验证 SQL：

```sql
SELECT
  d.department_name,
  round(sum(c.denied_amount), 2) AS total_denied_amount
FROM claims c
JOIN encounters e ON e.id = c.encounter_id
JOIN departments d ON d.id = e.department_id
GROUP BY d.department_name
ORDER BY total_denied_amount DESC, d.department_name;
```

---

## 困难

### 11. 哪家医院的 denied claim rate 最高？

标准答案：

- 最高不是单一医院，而是 **3 家并列第一**
- `Chengdu West General`: `16 / 144 = 11.11%`
- `Shanghai Harbor Hospital`: `16 / 144 = 11.11%`
- `Shenzhen Innovation Hospital`: `16 / 144 = 11.11%`

补充：

- `Beijing Central Medical Center`: `0 / 144 = 0.00%`
- `Wuhan River Teaching Hospital`: `0 / 144 = 0.00%`

验证 SQL：

```sql
SELECT
  h.hospital_name,
  count(*) FILTER (WHERE c.claim_status = 'denied') AS denied_claims,
  count(*) AS total_claims,
  round(
    100.0 * count(*) FILTER (WHERE c.claim_status = 'denied') / count(*),
    2
  ) AS denied_claim_rate_pct
FROM claims c
JOIN encounters e ON e.id = c.encounter_id
JOIN hospitals h ON h.id = e.hospital_id
GROUP BY h.hospital_name
ORDER BY denied_claim_rate_pct DESC, denied_claims DESC, h.hospital_name;
```

### 12. 哪类 prior auth 服务的拒绝率最高？

标准答案：

- 也是 **3 类并列第一**
- `Biologic Therapy`: `8 / 70 = 11.43%`
- `Chemotherapy`: `8 / 70 = 11.43%`
- `Joint Replacement`: `8 / 70 = 11.43%`
- `MRI`: `7 / 70 = 10.00%`

验证 SQL：

```sql
SELECT
  service_type,
  count(*) FILTER (WHERE auth_status = 'denied') AS denied_count,
  count(*) AS total_count,
  round(
    100.0 * count(*) FILTER (WHERE auth_status = 'denied') / count(*),
    2
  ) AS denied_rate_pct
FROM prior_auth_requests
GROUP BY service_type
ORDER BY denied_rate_pct DESC, service_type;
```

### 13. 哪个风险分层（risk segment）的 claim 平均支付金额最高？

标准答案：

- `low`: `claim_count = 392`，`avg_paid_amount = 1036.18`
- 其后依次是：
  - `complex`: `816.17`
  - `high`: `800.26`
  - `medium`: `310.88`

验证 SQL：

```sql
WITH claim_patient AS (
  SELECT
    p.risk_segment,
    c.id,
    c.paid_amount
  FROM claims c
  JOIN encounters e ON e.id = c.encounter_id
  JOIN patients p ON p.id = e.patient_id
)
SELECT
  risk_segment,
  count(*) AS claim_count,
  round(avg(paid_amount), 2) AS avg_paid_amount
FROM claim_patient
GROUP BY risk_segment
ORDER BY avg_paid_amount DESC, risk_segment;
```

### 14. 哪个风险分层带来的总拒付金额最高？

标准答案：

- `medium`: `total_denied_amount = 14478.45`
- `high`: `3262.48`
- `complex`: `0.00`
- `low`: `0.00`

验证 SQL：

```sql
WITH denial_by_risk AS (
  SELECT
    p.risk_segment,
    c.id AS claim_id,
    c.denied_amount
  FROM claims c
  JOIN encounters e ON e.id = c.encounter_id
  JOIN patients p ON p.id = e.patient_id
)
SELECT
  risk_segment,
  round(sum(denied_amount), 2) AS total_denied_amount,
  round(avg(denied_amount), 2) AS avg_denied_amount_per_claim
FROM denial_by_risk
GROUP BY risk_segment
ORDER BY total_denied_amount DESC, risk_segment;
```

### 15. 哪个风险分层中，同时“有未关闭 care event”且“最大 adherence gap >= 10 天”的患者最多？

标准答案：

- `medium`: `35`
- `high`: `1`
- `complex`: `0`
- `low`: `0`

也就是说，当前最值得被 Agent 识别出来的高运营压力群体是 `medium` 风险层中的这批患者。

验证 SQL：

```sql
WITH patient_flags AS (
  SELECT
    p.id,
    p.patient_mrn,
    p.risk_segment,
    COALESCE(MAX(pf.adherence_gap_days), 0) AS max_gap_days,
    COUNT(DISTINCT cme.id) FILTER (WHERE cme.status <> 'closed') AS open_care_events
  FROM patients p
  LEFT JOIN pharmacy_fills pf ON pf.patient_id = p.id
  LEFT JOIN care_management_events cme ON cme.patient_id = p.id
  GROUP BY p.id, p.patient_mrn, p.risk_segment
)
SELECT
  risk_segment,
  count(*) FILTER (WHERE open_care_events > 0) AS patients_with_open_events,
  count(*) FILTER (WHERE max_gap_days >= 10) AS patients_with_gap_ge_10,
  count(*) FILTER (WHERE open_care_events > 0 AND max_gap_days >= 10) AS patients_with_both
FROM patient_flags
GROUP BY risk_segment
ORDER BY risk_segment;
```

### 16. 哪个 specialty 的 claim 平均支付金额最高？

标准答案：

- `Emergency Medicine`: `claim_count = 144`，`avg_paid_amount = 1082.43`
- 其后依次是：
  - `Internal Medicine`: `925.06`
  - `Orthopedics`: `681.11`
  - `Oncology`: `675.91`
  - `Cardiology`: `630.50`

验证 SQL：

```sql
SELECT
  pr.specialty,
  count(*) AS claim_count,
  round(avg(c.paid_amount), 2) AS avg_paid_amount
FROM claims c
JOIN encounters e ON e.id = c.encounter_id
JOIN providers pr ON pr.id = e.provider_id
GROUP BY pr.specialty
ORDER BY avg_paid_amount DESC, pr.specialty;
```

按科室和服务线分析，哪些部门的就诊记录中慢性病患者比例最高且近期有异常检验结果？
SELECT D.DEPARTMENT_NAME,
   D.SERVICE_LINE,
   COUNT (DISTINCT E.ID) AS TOTAL_VISITS,
   COUNT (DISTINCT CASE WHEN DIAG.IS_CHRONIC THEN E.ID END) AS CHRONIC_VISITS,
   ROUND (100.0 * COUNT (DISTINCT CASE WHEN DIAG.IS_CHRONIC THEN E.ID END) / COUNT (DISTINCT E.ID), 2) AS CHRONIC_RATIO_PCT,
   COUNT (DISTINCT CASE WHEN LR.ABNORMAL_FLAG = 'normal' THEN E.ID END) AS ABNORMAL_LAB_VISITS,
   ROUND (100.0 * COUNT (DISTINCT CASE WHEN LR.ABNORMAL_FLAG = 'normal' THEN E.ID END) / COUNT (DISTINCT E.ID), 2) AS ABNORMAL_LAB_RATIO_PCT
FROM ENCOUNTERS E
  JOIN DEPARTMENTS D ON E.DEPARTMENT_ID = D.ID
  LEFT JOIN DIAGNOSES DIAG ON E.ID = DIAG.ENCOUNTER_ID
  LEFT JOIN LAB_RESULTS LR ON E.ID = LR.ENCOUNTER_ID
WHERE E.ADMITTED_AT > = '2026-01-01'
GROUP BY D.DEPARTMENT_NAME,
   D.SERVICE_LINE
ORDER BY CHRONIC_RATIO_PCT DESC,
   ABNORMAL_LAB_RATIO_PCT DESC;


-- 按科室和服务线分析慢性病比例和近期异常检验结果
WITH encounter_chronic_flag AS (
    -- 确定每个就诊是否有慢性诊断
    SELECT 
        e.id as encounter_id,
        e.department_id,
        MAX(CASE WHEN diag.is_chronic THEN 1 ELSE 0 END) as has_chronic
    FROM encounters e
    LEFT JOIN diagnoses diag ON e.id = diag.encounter_id
    GROUP BY e.id, e.department_id
),
encounter_abnormal_lab_flag AS (
    -- 确定每个就诊是否有近期异常检验结果（最近90天）
    SELECT 
        e.id as encounter_id,
        MAX(CASE WHEN lab.abnormal_flag != 'normal' AND lab.collected_at >= CURRENT_DATE - INTERVAL '90 days' THEN 1 ELSE 0 END) as has_abnormal_lab_recent
    FROM encounters e
    LEFT JOIN lab_results lab ON e.id = lab.encounter_id
    GROUP BY e.id
)
SELECT 
    d.department_name,
    d.service_line,
    COUNT(DISTINCT ecf.encounter_id) as total_encounters,
    SUM(ecf.has_chronic) as chronic_encounters,
    ROUND(100.0 * SUM(ecf.has_chronic) / COUNT(DISTINCT ecf.encounter_id), 2) as chronic_percentage,
    SUM(ealf.has_abnormal_lab_recent) as recent_abnormal_lab_encounters,
    ROUND(100.0 * SUM(ealf.has_abnormal_lab_recent) / COUNT(DISTINCT ecf.encounter_id), 2) as abnormal_lab_percentage
FROM encounter_chronic_flag ecf
JOIN departments d ON ecf.department_id = d.id
LEFT JOIN encounter_abnormal_lab_flag ealf ON ecf.encounter_id = ealf.encounter_id
GROUP BY d.department_name, d.service_line
ORDER BY chronic_percentage DESC
LIMIT 20;


| 科室 | 服务线 | 总就诊数 | 慢性病就诊数 | 慢性病比例(%) | 近期异常检验就诊数 | 异常检验比例(%) |
| --- | --- | --- | --- | --- | --- | --- |
| Orthopedics | Surgery | 240 | 240 | 100.00 | 42 | 17.50 |
| Cardiology | Heart | 240 | 0 | 0.00 | 44 | 18.33 |
| Emergency | Acute Care | 240 | 0 | 0.00 | 26 | 10.83 |
| Oncology | Cancer | 240 | 0 | 0.00 | 25 | 10.42 |


按地区（region）和保险类型（payer_type）汇总的就诊记录中，异常检验结果（abnormal_flag 为真）的出现频率是多少？

SELECT h.region, p.payer_type, COUNT(*) as total_tests, SUM(CASE WHEN lr.abnormal_flag = 'high' THEN 1 ELSE 0 END) as abnormal_count, (SUM(CASE WHEN lr.abnormal_flag = 'high' THEN 1.0 ELSE 0.0 END) / COUNT(*)) * 100 as abnormal_rate FROM lab_results lr JOIN encounters e ON lr.encounter_id = e.id JOIN hospitals h ON e.hospital_id = h.id JOIN claims c ON e.id = c.encounter_id JOIN payers p ON c.payer_id = p.id GROUP BY h.region, p.payer_type

| 地区 (region) | 保险类型 (payer_type) | 总检验结果数 | 异常结果数 | 异常频率 (%) |
| --- | --- | --- | --- | --- |
| Central | commercial | 288 | 30 | 10.42 |
| Central | government | 144 | 7 | 4.86 |
| East | commercial | 288 | 77 | 26.74 |
| East | government | 144 | 7 | 4.86 |
| North | commercial | 288 | 30 | 10.42 |
| North | government | 144 | 7 | 4.86 |
| South | commercial | 288 | 78 | 27.08 |
| South | government | 144 | 7 | 4.86 |
| West | commercial | 288 | 29 | 10.07 |
| West | government | 144 | 55 | 38.19 |
---

## 推荐使用顺序

如果你要拿这些题去验证 Agent，我建议按下面顺序跑：

1. 先跑简单题，确认 Agent 能识别表和基础聚合
2. 再跑中等题，验证金额口径和 join 是否正确
3. 最后跑困难题，重点看：
   - 是否能正确处理并列第一
   - 是否能正确理解 risk segment / denial / prior auth / care event 的业务含义
   - 是否能稳定生成多表 join SQL

## 额外建议

如果你后面要把这份题库作为正式回归验证集，我建议下一步再补两类东西：

- 一列“预期涉及的核心表”
- 一列“常见错误答案 / 常见错误 SQL 模式”

这样就不只是测试题库，而会变成一份更完整的 Agent 验收基线。
