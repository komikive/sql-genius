"""Provision complex Postgres lab databases and register them as datasources.

This script creates three realistic business databases on the local Postgres
cluster, seeds them with multi-table relational data, registers them into the
SQL Genius metadata database, and optionally triggers datasource onboarding
through the running FastAPI backend.

Recommended usage:

    uv run python provision_complex_postgres_labs.py

The registered datasource URLs default to the Docker Compose network hostname
`postgres`, which matches the current demo stack. If you run the backend on the
host instead, pass `--runtime-host 127.0.0.1`.
"""

from __future__ import annotations

import argparse
import json
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass

import psycopg
from psycopg import sql
from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings
from app.core.psycopg_dsn import raw_psycopg_dsn


@dataclass(frozen=True, slots=True)
class LabSpec:
    key: str
    db_name: str
    datasource_id: str
    display_name: str
    summary: str
    ddl_and_seed_sql: str


RETAIL_SQL = textwrap.dedent(
    """
    SET TIME ZONE 'UTC';

    CREATE TABLE IF NOT EXISTS regions (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      region_code text NOT NULL UNIQUE,
      region_name text NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS stores (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      store_code text NOT NULL UNIQUE,
      region_id bigint NOT NULL REFERENCES regions(id),
      store_name text NOT NULL,
      format_type text NOT NULL CHECK (format_type IN ('flagship', 'mall', 'community', 'outlet')),
      city text NOT NULL,
      opened_at timestamptz NOT NULL,
      is_active boolean NOT NULL DEFAULT true
    );
    CREATE INDEX IF NOT EXISTS stores_region_id_idx ON stores (region_id);

    CREATE TABLE IF NOT EXISTS suppliers (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      supplier_code text NOT NULL UNIQUE,
      supplier_name text NOT NULL,
      country text NOT NULL,
      quality_score numeric(5,2) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      category_code text NOT NULL UNIQUE,
      parent_category_id bigint NULL REFERENCES categories(id),
      category_name text NOT NULL UNIQUE
    );
    CREATE INDEX IF NOT EXISTS categories_parent_category_id_idx ON categories (parent_category_id);

    CREATE TABLE IF NOT EXISTS products (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      sku text NOT NULL UNIQUE,
      category_id bigint NOT NULL REFERENCES categories(id),
      supplier_id bigint NOT NULL REFERENCES suppliers(id),
      product_name text NOT NULL,
      status text NOT NULL CHECK (status IN ('active', 'seasonal', 'retired')),
      cost_price numeric(12,2) NOT NULL,
      unit_price numeric(12,2) NOT NULL,
      launch_date date NOT NULL,
      attributes jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS products_category_supplier_idx ON products (category_id, supplier_id);
    CREATE INDEX IF NOT EXISTS products_active_launch_idx ON products (status, launch_date DESC);

    CREATE TABLE IF NOT EXISTS customers (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      external_customer_code text NOT NULL UNIQUE,
      region_id bigint NOT NULL REFERENCES regions(id),
      preferred_store_id bigint NULL REFERENCES stores(id),
      customer_name text NOT NULL,
      tier text NOT NULL CHECK (tier IN ('standard', 'silver', 'gold', 'platinum')),
      preferred_channel text NOT NULL CHECK (preferred_channel IN ('online', 'store', 'hybrid')),
      acquired_at timestamptz NOT NULL,
      churn_risk numeric(5,2) NOT NULL,
      profile jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS customers_region_id_idx ON customers (region_id);
    CREATE INDEX IF NOT EXISTS customers_tier_acquired_idx ON customers (tier, acquired_at DESC);

    CREATE TABLE IF NOT EXISTS promotions (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      promotion_code text NOT NULL UNIQUE,
      promotion_name text NOT NULL,
      channel text NOT NULL CHECK (channel IN ('online', 'store', 'all')),
      discount_type text NOT NULL CHECK (discount_type IN ('percentage', 'coupon', 'bundle')),
      discount_value numeric(10,2) NOT NULL,
      start_at timestamptz NOT NULL,
      end_at timestamptz NOT NULL,
      target_segment text NOT NULL,
      rules_json jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS promotions_window_idx ON promotions (start_at, end_at);

    CREATE TABLE IF NOT EXISTS orders (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      order_no text NOT NULL UNIQUE,
      customer_id bigint NOT NULL REFERENCES customers(id),
      store_id bigint NOT NULL REFERENCES stores(id),
      promotion_id bigint NULL REFERENCES promotions(id),
      ordered_at timestamptz NOT NULL,
      status text NOT NULL CHECK (status IN ('completed', 'returned', 'cancelled')),
      channel text NOT NULL CHECK (channel IN ('online', 'store', 'app')),
      payment_status text NOT NULL CHECK (payment_status IN ('paid', 'partial_refund', 'refunded')),
      shipping_fee numeric(12,2) NOT NULL DEFAULT 0,
      gross_amount numeric(12,2) NOT NULL DEFAULT 0,
      discount_amount numeric(12,2) NOT NULL DEFAULT 0,
      net_amount numeric(12,2) NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS orders_customer_ordered_idx ON orders (customer_id, ordered_at DESC);
    CREATE INDEX IF NOT EXISTS orders_store_status_ordered_idx ON orders (store_id, status, ordered_at DESC);
    CREATE INDEX IF NOT EXISTS orders_completed_ordered_idx ON orders (ordered_at DESC) WHERE status = 'completed';

    CREATE TABLE IF NOT EXISTS order_items (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      order_id bigint NOT NULL REFERENCES orders(id),
      line_no integer NOT NULL,
      product_id bigint NOT NULL REFERENCES products(id),
      quantity integer NOT NULL CHECK (quantity > 0),
      list_price numeric(12,2) NOT NULL,
      discount_amount numeric(12,2) NOT NULL DEFAULT 0,
      net_amount numeric(12,2) NOT NULL,
      UNIQUE (order_id, line_no)
    );
    CREATE INDEX IF NOT EXISTS order_items_order_id_idx ON order_items (order_id);
    CREATE INDEX IF NOT EXISTS order_items_product_id_idx ON order_items (product_id);

    CREATE TABLE IF NOT EXISTS payments (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      payment_reference text NOT NULL UNIQUE,
      order_id bigint NOT NULL REFERENCES orders(id),
      payment_provider text NOT NULL,
      paid_at timestamptz NOT NULL,
      status text NOT NULL CHECK (status IN ('captured', 'partial_refund', 'refunded')),
      amount numeric(12,2) NOT NULL,
      refund_amount numeric(12,2) NOT NULL DEFAULT 0,
      risk_score numeric(5,2) NOT NULL
    );
    CREATE INDEX IF NOT EXISTS payments_order_id_idx ON payments (order_id);
    CREATE INDEX IF NOT EXISTS payments_status_paid_at_idx ON payments (status, paid_at DESC);

    CREATE TABLE IF NOT EXISTS shipments (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      shipment_no text NOT NULL UNIQUE,
      order_id bigint NOT NULL REFERENCES orders(id),
      warehouse_code text NOT NULL,
      carrier text NOT NULL,
      shipped_at timestamptz NOT NULL,
      delivered_at timestamptz NULL,
      promised_at timestamptz NOT NULL,
      status text NOT NULL CHECK (status IN ('delivered', 'in_transit', 'exception')),
      actual_days integer NULL
    );
    CREATE INDEX IF NOT EXISTS shipments_order_id_idx ON shipments (order_id);
    CREATE INDEX IF NOT EXISTS shipments_status_promised_idx ON shipments (status, promised_at DESC);

    CREATE TABLE IF NOT EXISTS returns (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      return_no text NOT NULL UNIQUE,
      order_item_id bigint NOT NULL REFERENCES order_items(id),
      returned_at timestamptz NOT NULL,
      reason_code text NOT NULL,
      condition_grade text NOT NULL CHECK (condition_grade IN ('sealed', 'opened', 'damaged')),
      approved_amount numeric(12,2) NOT NULL,
      restocked boolean NOT NULL DEFAULT false
    );
    CREATE INDEX IF NOT EXISTS returns_order_item_id_idx ON returns (order_item_id);
    CREATE INDEX IF NOT EXISTS returns_reason_returned_idx ON returns (reason_code, returned_at DESC);

    CREATE TABLE IF NOT EXISTS inventory_snapshots (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      store_id bigint NOT NULL REFERENCES stores(id),
      product_id bigint NOT NULL REFERENCES products(id),
      snapshot_date date NOT NULL,
      on_hand_qty integer NOT NULL,
      reserved_qty integer NOT NULL DEFAULT 0,
      reorder_point integer NOT NULL,
      stock_value numeric(14,2) NOT NULL,
      UNIQUE (store_id, product_id, snapshot_date)
    );
    CREATE INDEX IF NOT EXISTS inventory_store_product_snapshot_idx
      ON inventory_snapshots (store_id, product_id, snapshot_date DESC);

    CREATE TABLE IF NOT EXISTS loyalty_ledger (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      customer_id bigint NOT NULL REFERENCES customers(id),
      order_id bigint NULL REFERENCES orders(id),
      event_at timestamptz NOT NULL,
      event_type text NOT NULL CHECK (event_type IN ('earn', 'redeem', 'manual_adjustment')),
      points_delta integer NOT NULL,
      balance_after integer NOT NULL,
      UNIQUE (customer_id, order_id, event_type)
    );
    CREATE INDEX IF NOT EXISTS loyalty_customer_event_idx ON loyalty_ledger (customer_id, event_at DESC);

    CREATE TABLE IF NOT EXISTS customer_service_cases (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      case_no text NOT NULL UNIQUE,
      customer_id bigint NOT NULL REFERENCES customers(id),
      order_id bigint NULL REFERENCES orders(id),
      created_at timestamptz NOT NULL,
      case_type text NOT NULL CHECK (case_type IN ('delivery', 'refund', 'quality', 'membership')),
      severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
      resolution_status text NOT NULL CHECK (resolution_status IN ('resolved', 'escalated', 'open')),
      resolution_hours numeric(8,2) NOT NULL,
      sentiment_score numeric(5,2) NOT NULL,
      notes jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX IF NOT EXISTS service_cases_customer_created_idx ON customer_service_cases (customer_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS service_cases_open_idx ON customer_service_cases (created_at DESC) WHERE resolution_status <> 'resolved';

    INSERT INTO regions (region_code, region_name)
    VALUES
      ('NORTH', 'North Region'),
      ('EAST', 'East Region'),
      ('SOUTH', 'South Region'),
      ('WEST', 'West Region'),
      ('CENTRAL', 'Central Region')
    ON CONFLICT (region_code) DO NOTHING;

    INSERT INTO stores (store_code, region_id, store_name, format_type, city, opened_at, is_active)
    SELECT
      format('ST-%s-%s', lower(r.region_code), gs.n),
      r.id,
      format('%s Store %s', initcap(lower(r.region_code)), gs.n),
      CASE gs.n
        WHEN 1 THEN 'flagship'
        WHEN 2 THEN 'mall'
        WHEN 3 THEN 'community'
        ELSE 'outlet'
      END,
      CASE r.region_code
        WHEN 'NORTH' THEN 'Beijing'
        WHEN 'EAST' THEN 'Shanghai'
        WHEN 'SOUTH' THEN 'Shenzhen'
        WHEN 'WEST' THEN 'Chengdu'
        ELSE 'Wuhan'
      END || ' ' || gs.n::text,
      now() - make_interval(days => 1600 - (r.id::int * 45) - gs.n * 30),
      true
    FROM regions r
    CROSS JOIN generate_series(1, 4) AS gs(n)
    ON CONFLICT (store_code) DO NOTHING;

    INSERT INTO suppliers (supplier_code, supplier_name, country, quality_score)
    SELECT
      format('SUP-%03s', gs),
      format('Supplier %s', gs),
      CASE gs % 5
        WHEN 0 THEN 'China'
        WHEN 1 THEN 'Vietnam'
        WHEN 2 THEN 'Malaysia'
        WHEN 3 THEN 'Thailand'
        ELSE 'South Korea'
      END,
      round((78 + (gs % 17) * 1.1)::numeric, 2)
    FROM generate_series(1, 18) AS gs
    ON CONFLICT (supplier_code) DO NOTHING;

    INSERT INTO categories (category_code, parent_category_id, category_name)
    VALUES
      ('apparel', NULL, 'Apparel'),
      ('accessories', NULL, 'Accessories'),
      ('footwear', NULL, 'Footwear'),
      ('beauty', NULL, 'Beauty'),
      ('sportswear', (SELECT id FROM categories WHERE category_code = 'apparel'), 'Sportswear'),
      ('formalwear', (SELECT id FROM categories WHERE category_code = 'apparel'), 'Formalwear'),
      ('bags', (SELECT id FROM categories WHERE category_code = 'accessories'), 'Bags'),
      ('small-leather-goods', (SELECT id FROM categories WHERE category_code = 'accessories'), 'Small Leather Goods'),
      ('running', (SELECT id FROM categories WHERE category_code = 'footwear'), 'Running'),
      ('casual-shoes', (SELECT id FROM categories WHERE category_code = 'footwear'), 'Casual Shoes')
    ON CONFLICT (category_code) DO NOTHING;

    INSERT INTO products (sku, category_id, supplier_id, product_name, status, cost_price, unit_price, launch_date, attributes)
    SELECT
      format('SKU-%s-%02s', c.category_code, gs.n),
      c.id,
      ((gs.n + c.id)::int % (SELECT count(*) FROM suppliers)) + 1,
      format('%s Product %s', initcap(replace(c.category_code, '-', ' ')), gs.n),
      CASE
        WHEN gs.n % 11 = 0 THEN 'retired'
        WHEN gs.n % 5 = 0 THEN 'seasonal'
        ELSE 'active'
      END,
      round((25 + c.id * 3 + gs.n * 1.7)::numeric, 2),
      round((48 + c.id * 5 + gs.n * 3.2)::numeric, 2),
      current_date - (((gs.n * 17) + (c.id::int * 9)) % 720),
      jsonb_build_object(
        'color_family', CASE gs.n % 4 WHEN 0 THEN 'black' WHEN 1 THEN 'white' WHEN 2 THEN 'navy' ELSE 'earth' END,
        'season_focus', CASE gs.n % 3 WHEN 0 THEN 'spring' WHEN 1 THEN 'summer' ELSE 'autumn' END,
        'drop_batch', ((gs.n + c.id) % 6) + 1
      )
    FROM categories c
    CROSS JOIN generate_series(1, 12) AS gs(n)
    ON CONFLICT (sku) DO NOTHING;

    INSERT INTO customers (external_customer_code, region_id, preferred_store_id, customer_name, tier, preferred_channel, acquired_at, churn_risk, profile)
    SELECT
      format('CUST-%05s', gs),
      ((gs - 1) % (SELECT count(*) FROM regions)) + 1,
      ((gs - 1) % (SELECT count(*) FROM stores)) + 1,
      format('Customer %s', gs),
      CASE
        WHEN gs % 17 = 0 THEN 'platinum'
        WHEN gs % 7 = 0 THEN 'gold'
        WHEN gs % 3 = 0 THEN 'silver'
        ELSE 'standard'
      END,
      CASE gs % 3 WHEN 0 THEN 'online' WHEN 1 THEN 'store' ELSE 'hybrid' END,
      now() - make_interval(days => (gs % 1000), hours => gs % 24),
      round(((gs % 23) * 3.1)::numeric, 2),
      jsonb_build_object(
        'household_size', 1 + (gs % 5),
        'lifetime_segment', CASE WHEN gs % 9 = 0 THEN 'high-value' ELSE 'core' END,
        'marketing_opt_in', (gs % 4) <> 0
      )
    FROM generate_series(1, 260) AS gs
    ON CONFLICT (external_customer_code) DO NOTHING;

    INSERT INTO promotions (promotion_code, promotion_name, channel, discount_type, discount_value, start_at, end_at, target_segment, rules_json)
    SELECT
      format('PROMO-%02s', gs),
      format('Campaign %s', gs),
      CASE gs % 3 WHEN 0 THEN 'online' WHEN 1 THEN 'store' ELSE 'all' END,
      CASE gs % 3 WHEN 0 THEN 'percentage' WHEN 1 THEN 'coupon' ELSE 'bundle' END,
      round((5 + gs * 1.5)::numeric, 2),
      now() - make_interval(days => 120 - gs * 4),
      now() + make_interval(days => 20 + gs * 3),
      CASE gs % 4 WHEN 0 THEN 'platinum' WHEN 1 THEN 'gold' WHEN 2 THEN 'hybrid-loyalists' ELSE 'new-customers' END,
      jsonb_build_object('minimum_basket', 80 + gs * 10, 'stackable', gs % 2 = 0)
    FROM generate_series(1, 10) AS gs
    ON CONFLICT (promotion_code) DO NOTHING;

    INSERT INTO orders (order_no, customer_id, store_id, promotion_id, ordered_at, status, channel, payment_status, shipping_fee)
    SELECT
      format('ORD-%06s', gs),
      ((gs - 1) % (SELECT count(*) FROM customers)) + 1,
      ((gs - 1) % (SELECT count(*) FROM stores)) + 1,
      CASE WHEN gs % 4 = 0 THEN ((gs - 1) % (SELECT count(*) FROM promotions)) + 1 ELSE NULL END,
      now() - make_interval(days => (gs % 210), hours => gs % 24, mins => gs % 60),
      CASE
        WHEN gs % 13 = 0 THEN 'cancelled'
        WHEN gs % 9 = 0 THEN 'returned'
        ELSE 'completed'
      END,
      CASE gs % 3 WHEN 0 THEN 'online' WHEN 1 THEN 'store' ELSE 'app' END,
      CASE
        WHEN gs % 9 = 0 THEN 'partial_refund'
        WHEN gs % 13 = 0 THEN 'refunded'
        ELSE 'paid'
      END,
      round((5 + (gs % 4) * 2.5)::numeric, 2)
    FROM generate_series(1, 1400) AS gs
    ON CONFLICT (order_no) DO NOTHING;

    INSERT INTO order_items (order_id, line_no, product_id, quantity, list_price, discount_amount, net_amount)
    SELECT
      o.id,
      line_items.line_no,
      (((o.id * 7) + line_items.line_no)::int % (SELECT count(*) FROM products)) + 1,
      1 + ((o.id + line_items.line_no) % 3),
      round((45 + ((o.id + line_items.line_no * 11) % 80) * 1.8)::numeric, 2),
      round((CASE WHEN o.promotion_id IS NULL THEN 0 ELSE 4 + (line_items.line_no * 1.5) END)::numeric, 2),
      round(
        ((1 + ((o.id + line_items.line_no) % 3)) * (45 + ((o.id + line_items.line_no * 11) % 80) * 1.8)
        - (CASE WHEN o.promotion_id IS NULL THEN 0 ELSE 4 + (line_items.line_no * 1.5) END))::numeric,
        2
      )
    FROM orders o
    CROSS JOIN LATERAL generate_series(1, 2 + (o.id::int % 3)) AS line_items(line_no)
    ON CONFLICT (order_id, line_no) DO NOTHING;

    UPDATE orders o
    SET
      gross_amount = agg.gross_amount,
      discount_amount = agg.discount_amount,
      net_amount = agg.net_amount + o.shipping_fee
    FROM (
      SELECT
        order_id,
        round(sum(list_price * quantity)::numeric, 2) AS gross_amount,
        round(sum(discount_amount)::numeric, 2) AS discount_amount,
        round(sum(net_amount)::numeric, 2) AS net_amount
      FROM order_items
      GROUP BY order_id
    ) AS agg
    WHERE agg.order_id = o.id;

    INSERT INTO payments (payment_reference, order_id, payment_provider, paid_at, status, amount, refund_amount, risk_score)
    SELECT
      format('PAY-%06s', o.id),
      o.id,
      CASE o.id % 4 WHEN 0 THEN 'alipay' WHEN 1 THEN 'wechat' WHEN 2 THEN 'unionpay' ELSE 'credit-card' END,
      o.ordered_at + make_interval(hours => 1 + (o.id::int % 6)),
      CASE o.payment_status WHEN 'paid' THEN 'captured' WHEN 'partial_refund' THEN 'partial_refund' ELSE 'refunded' END,
      o.net_amount,
      CASE o.payment_status WHEN 'partial_refund' THEN round((o.net_amount * 0.18)::numeric, 2) WHEN 'refunded' THEN o.net_amount ELSE 0 END,
      round((5 + (o.id % 40) * 1.2)::numeric, 2)
    FROM orders o
    ON CONFLICT (payment_reference) DO NOTHING;

    INSERT INTO shipments (shipment_no, order_id, warehouse_code, carrier, shipped_at, delivered_at, promised_at, status, actual_days)
    SELECT
      format('SHP-%06s', o.id),
      o.id,
      format('WH-%02s', 1 + (o.store_id % 5)),
      CASE o.id % 4 WHEN 0 THEN 'SF' WHEN 1 THEN 'JD Logistics' WHEN 2 THEN 'Cainiao' ELSE 'YTO' END,
      o.ordered_at + make_interval(hours => 12 + (o.id::int % 24)),
      CASE WHEN o.id % 17 = 0 THEN NULL ELSE o.ordered_at + make_interval(days => 2 + (o.id::int % 4)) END,
      o.ordered_at + make_interval(days => 3 + (o.id::int % 3)),
      CASE WHEN o.id % 17 = 0 THEN 'exception' WHEN o.id % 5 = 0 THEN 'in_transit' ELSE 'delivered' END,
      CASE WHEN o.id % 17 = 0 THEN NULL ELSE 2 + (o.id % 4) END
    FROM orders o
    WHERE o.status <> 'cancelled'
    ON CONFLICT (shipment_no) DO NOTHING;

    INSERT INTO returns (return_no, order_item_id, returned_at, reason_code, condition_grade, approved_amount, restocked)
    SELECT
      format('RET-%06s', oi.id),
      oi.id,
      o.ordered_at + make_interval(days => 10 + (oi.id::int % 20)),
      CASE oi.id % 4 WHEN 0 THEN 'size_mismatch' WHEN 1 THEN 'damaged' WHEN 2 THEN 'late_delivery' ELSE 'changed_mind' END,
      CASE oi.id % 3 WHEN 0 THEN 'sealed' WHEN 1 THEN 'opened' ELSE 'damaged' END,
      round((oi.net_amount * (0.65 + ((oi.id % 25) / 100.0)))::numeric, 2),
      (oi.id % 5) <> 0
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    WHERE o.status = 'returned'
    ON CONFLICT (return_no) DO NOTHING;

    INSERT INTO inventory_snapshots (store_id, product_id, snapshot_date, on_hand_qty, reserved_qty, reorder_point, stock_value)
    SELECT
      s.id,
      p.id,
      current_date - (gs.day_offset * 7),
      30 + ((s.id * 5 + p.id + gs.day_offset) % 90),
      ((s.id + p.id + gs.day_offset) % 12),
      18 + ((p.id + s.id) % 10),
      round(((30 + ((s.id * 5 + p.id + gs.day_offset) % 90)) * p.cost_price)::numeric, 2)
    FROM stores s
    JOIN products p ON p.id <= 48
    CROSS JOIN generate_series(0, 5) AS gs(day_offset)
    WHERE NOT EXISTS (SELECT 1 FROM inventory_snapshots)
    ON CONFLICT (store_id, product_id, snapshot_date) DO NOTHING;

    INSERT INTO loyalty_ledger (customer_id, order_id, event_at, event_type, points_delta, balance_after)
    SELECT
      o.customer_id,
      o.id,
      o.ordered_at + make_interval(hours => 2),
      'earn',
      floor(o.net_amount / 10)::int,
      floor(o.net_amount / 10)::int + ((o.customer_id % 25) * 35)
    FROM orders o
    WHERE o.status = 'completed'
    ON CONFLICT DO NOTHING;

    INSERT INTO customer_service_cases (case_no, customer_id, order_id, created_at, case_type, severity, resolution_status, resolution_hours, sentiment_score, notes)
    SELECT
      format('CASE-%06s', o.id),
      o.customer_id,
      o.id,
      o.ordered_at + make_interval(days => 1 + (o.id::int % 8)),
      CASE o.id % 4 WHEN 0 THEN 'delivery' WHEN 1 THEN 'refund' WHEN 2 THEN 'quality' ELSE 'membership' END,
      CASE o.id % 6 WHEN 0 THEN 'high' WHEN 1 THEN 'medium' ELSE 'low' END,
      CASE o.id % 10 WHEN 0 THEN 'open' WHEN 1 THEN 'escalated' ELSE 'resolved' END,
      round((6 + (o.id % 40) * 1.3)::numeric, 2),
      round((40 + (o.id % 55))::numeric, 2),
      jsonb_build_object('channel', CASE o.channel WHEN 'store' THEN 'hotline' ELSE 'chat' END, 'owner_team', CASE o.id % 3 WHEN 0 THEN 'cx' WHEN 1 THEN 'ops' ELSE 'vip' END)
    FROM orders o
    WHERE o.id % 11 = 0
    ON CONFLICT (case_no) DO NOTHING;

    ANALYZE;
    """
)


HEALTHCARE_SQL = textwrap.dedent(
    """
    SET TIME ZONE 'UTC';

    CREATE TABLE IF NOT EXISTS hospitals (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      hospital_code text NOT NULL UNIQUE,
      hospital_name text NOT NULL,
      region text NOT NULL,
      ownership_type text NOT NULL CHECK (ownership_type IN ('public', 'private', 'teaching'))
    );

    CREATE TABLE IF NOT EXISTS departments (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      hospital_id bigint NOT NULL REFERENCES hospitals(id),
      department_code text NOT NULL UNIQUE,
      department_name text NOT NULL,
      service_line text NOT NULL
    );
    CREATE INDEX IF NOT EXISTS departments_hospital_id_idx ON departments (hospital_id);

    CREATE TABLE IF NOT EXISTS providers (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      provider_code text NOT NULL UNIQUE,
      hospital_id bigint NOT NULL REFERENCES hospitals(id),
      department_id bigint NOT NULL REFERENCES departments(id),
      provider_name text NOT NULL,
      specialty text NOT NULL,
      employment_type text NOT NULL CHECK (employment_type IN ('employed', 'contracted', 'visiting')),
      start_date date NOT NULL
    );
    CREATE INDEX IF NOT EXISTS providers_hospital_department_idx ON providers (hospital_id, department_id);

    CREATE TABLE IF NOT EXISTS payers (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      payer_code text NOT NULL UNIQUE,
      payer_name text NOT NULL,
      payer_type text NOT NULL CHECK (payer_type IN ('commercial', 'government', 'employer')),
      contract_model text NOT NULL CHECK (contract_model IN ('fee_for_service', 'bundled', 'capitated'))
    );

    CREATE TABLE IF NOT EXISTS plans (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      payer_id bigint NOT NULL REFERENCES payers(id),
      plan_code text NOT NULL UNIQUE,
      plan_name text NOT NULL,
      line_of_business text NOT NULL,
      deductible_amount numeric(12,2) NOT NULL,
      copay_amount numeric(12,2) NOT NULL
    );
    CREATE INDEX IF NOT EXISTS plans_payer_id_idx ON plans (payer_id);

    CREATE TABLE IF NOT EXISTS patients (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      patient_mrn text NOT NULL UNIQUE,
      patient_name text NOT NULL,
      birth_date date NOT NULL,
      gender text NOT NULL CHECK (gender IN ('female', 'male', 'other')),
      home_region text NOT NULL,
      risk_segment text NOT NULL CHECK (risk_segment IN ('low', 'medium', 'high', 'complex')),
      chronic_conditions jsonb NOT NULL DEFAULT '[]'::jsonb
    );

    CREATE TABLE IF NOT EXISTS encounters (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      encounter_no text NOT NULL UNIQUE,
      patient_id bigint NOT NULL REFERENCES patients(id),
      hospital_id bigint NOT NULL REFERENCES hospitals(id),
      department_id bigint NOT NULL REFERENCES departments(id),
      provider_id bigint NOT NULL REFERENCES providers(id),
      primary_plan_id bigint NOT NULL REFERENCES plans(id),
      admitted_at timestamptz NOT NULL,
      discharged_at timestamptz NOT NULL,
      encounter_type text NOT NULL CHECK (encounter_type IN ('inpatient', 'outpatient', 'ed')),
      total_charge numeric(14,2) NOT NULL DEFAULT 0,
      total_allowed numeric(14,2) NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS encounters_patient_admit_idx ON encounters (patient_id, admitted_at DESC);
    CREATE INDEX IF NOT EXISTS encounters_hospital_type_idx ON encounters (hospital_id, encounter_type, admitted_at DESC);

    CREATE TABLE IF NOT EXISTS diagnoses (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      encounter_id bigint NOT NULL REFERENCES encounters(id),
      diagnosis_rank integer NOT NULL,
      icd10_code text NOT NULL,
      diagnosis_name text NOT NULL,
      is_chronic boolean NOT NULL DEFAULT false,
      UNIQUE (encounter_id, diagnosis_rank)
    );
    CREATE INDEX IF NOT EXISTS diagnoses_encounter_id_idx ON diagnoses (encounter_id);

    CREATE TABLE IF NOT EXISTS procedures (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      encounter_id bigint NOT NULL REFERENCES encounters(id),
      procedure_rank integer NOT NULL,
      cpt_code text NOT NULL,
      procedure_name text NOT NULL,
      performed_at timestamptz NOT NULL,
      billed_amount numeric(12,2) NOT NULL,
      UNIQUE (encounter_id, procedure_rank)
    );
    CREATE INDEX IF NOT EXISTS procedures_encounter_id_idx ON procedures (encounter_id);

    CREATE TABLE IF NOT EXISTS claims (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      claim_no text NOT NULL UNIQUE,
      encounter_id bigint NOT NULL REFERENCES encounters(id),
      payer_id bigint NOT NULL REFERENCES payers(id),
      plan_id bigint NOT NULL REFERENCES plans(id),
      submitted_at timestamptz NOT NULL,
      claim_status text NOT NULL CHECK (claim_status IN ('paid', 'partial_denial', 'denied', 'pending')),
      billed_amount numeric(14,2) NOT NULL DEFAULT 0,
      allowed_amount numeric(14,2) NOT NULL DEFAULT 0,
      paid_amount numeric(14,2) NOT NULL DEFAULT 0,
      denied_amount numeric(14,2) NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS claims_status_submitted_idx ON claims (claim_status, submitted_at DESC);
    CREATE INDEX IF NOT EXISTS claims_payer_plan_idx ON claims (payer_id, plan_id, submitted_at DESC);

    CREATE TABLE IF NOT EXISTS claim_lines (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      claim_id bigint NOT NULL REFERENCES claims(id),
      procedure_id bigint NULL REFERENCES procedures(id),
      revenue_code text NOT NULL,
      units integer NOT NULL CHECK (units > 0),
      billed_amount numeric(12,2) NOT NULL,
      allowed_amount numeric(12,2) NOT NULL,
      line_status text NOT NULL CHECK (line_status IN ('paid', 'denied', 'pending')),
      UNIQUE (claim_id, procedure_id, revenue_code)
    );
    CREATE INDEX IF NOT EXISTS claim_lines_claim_id_idx ON claim_lines (claim_id);
    CREATE INDEX IF NOT EXISTS claim_lines_status_claim_idx ON claim_lines (line_status, claim_id);

    CREATE TABLE IF NOT EXISTS denials (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      claim_line_id bigint NOT NULL REFERENCES claim_lines(id),
      denial_code text NOT NULL,
      denial_reason text NOT NULL,
      denial_category text NOT NULL,
      denied_at timestamptz NOT NULL,
      overturned_at timestamptz NULL,
      UNIQUE (claim_line_id, denial_code)
    );
    CREATE INDEX IF NOT EXISTS denials_claim_line_id_idx ON denials (claim_line_id);
    CREATE INDEX IF NOT EXISTS denials_open_idx ON denials (denied_at DESC) WHERE overturned_at IS NULL;

    CREATE TABLE IF NOT EXISTS prior_auth_requests (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      auth_no text NOT NULL UNIQUE,
      patient_id bigint NOT NULL REFERENCES patients(id),
      provider_id bigint NOT NULL REFERENCES providers(id),
      plan_id bigint NOT NULL REFERENCES plans(id),
      requested_at timestamptz NOT NULL,
      service_type text NOT NULL,
      auth_status text NOT NULL CHECK (auth_status IN ('approved', 'partially_approved', 'denied', 'pending')),
      requested_amount numeric(12,2) NOT NULL,
      approved_amount numeric(12,2) NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS prior_auth_plan_status_idx ON prior_auth_requests (plan_id, auth_status, requested_at DESC);

    CREATE TABLE IF NOT EXISTS pharmacy_fills (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      patient_id bigint NOT NULL REFERENCES patients(id),
      provider_id bigint NOT NULL REFERENCES providers(id),
      plan_id bigint NOT NULL REFERENCES plans(id),
      ndc_code text NOT NULL,
      drug_name text NOT NULL,
      fill_date date NOT NULL,
      days_supply integer NOT NULL,
      paid_amount numeric(12,2) NOT NULL,
      adherence_gap_days integer NOT NULL DEFAULT 0,
      UNIQUE (patient_id, ndc_code, fill_date)
    );
    CREATE INDEX IF NOT EXISTS pharmacy_patient_fill_idx ON pharmacy_fills (patient_id, fill_date DESC);

    CREATE TABLE IF NOT EXISTS care_management_events (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      patient_id bigint NOT NULL REFERENCES patients(id),
      encounter_id bigint NULL REFERENCES encounters(id),
      created_at timestamptz NOT NULL,
      event_type text NOT NULL,
      priority text NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
      status text NOT NULL CHECK (status IN ('open', 'in_progress', 'closed')),
      assigned_team text NOT NULL,
      UNIQUE (patient_id, encounter_id, event_type)
    );
    CREATE INDEX IF NOT EXISTS care_events_patient_created_idx ON care_management_events (patient_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS lab_results (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      encounter_id bigint NOT NULL REFERENCES encounters(id),
      test_code text NOT NULL,
      test_name text NOT NULL,
      result_value numeric(12,2) NOT NULL,
      result_unit text NOT NULL,
      abnormal_flag text NOT NULL CHECK (abnormal_flag IN ('normal', 'high', 'low')),
      collected_at timestamptz NOT NULL,
      UNIQUE (encounter_id, test_code)
    );
    CREATE INDEX IF NOT EXISTS lab_results_encounter_collected_idx ON lab_results (encounter_id, collected_at DESC);

    INSERT INTO hospitals (hospital_code, hospital_name, region, ownership_type)
    VALUES
      ('H-BJ-01', 'Beijing Central Medical Center', 'North', 'teaching'),
      ('H-SH-01', 'Shanghai Harbor Hospital', 'East', 'public'),
      ('H-SZ-01', 'Shenzhen Innovation Hospital', 'South', 'private'),
      ('H-CD-01', 'Chengdu West General', 'West', 'public'),
      ('H-WH-01', 'Wuhan River Teaching Hospital', 'Central', 'teaching')
    ON CONFLICT (hospital_code) DO NOTHING;

    INSERT INTO departments (hospital_id, department_code, department_name, service_line)
    SELECT
      h.id,
      format('DEP-%s-%s', split_part(h.hospital_code, '-', 2), dept.seq),
      dept.department_name,
      dept.service_line
    FROM hospitals h
    CROSS JOIN (
      VALUES
        (1, 'Emergency', 'Acute Care'),
        (2, 'Cardiology', 'Heart'),
        (3, 'Oncology', 'Cancer'),
        (4, 'Orthopedics', 'Surgery')
    ) AS dept(seq, department_name, service_line)
    ON CONFLICT (department_code) DO NOTHING;

    INSERT INTO providers (provider_code, hospital_id, department_id, provider_name, specialty, employment_type, start_date)
    SELECT
      format('PRV-%s-%02s', d.department_code, gs.n),
      h.id,
      d.id,
      format('%s Provider %s', d.department_name, gs.n),
      CASE (gs.n + d.id) % 5
        WHEN 0 THEN 'Emergency Medicine'
        WHEN 1 THEN 'Cardiology'
        WHEN 2 THEN 'Oncology'
        WHEN 3 THEN 'Orthopedics'
        ELSE 'Internal Medicine'
      END,
      CASE gs.n % 3 WHEN 0 THEN 'employed' WHEN 1 THEN 'contracted' ELSE 'visiting' END,
      current_date - (((gs.n * 47) + (d.id::int * 11)) % 1800)
    FROM hospitals h
    JOIN departments d ON d.hospital_id = h.id
    CROSS JOIN generate_series(1, 4) AS gs(n)
    ON CONFLICT (provider_code) DO NOTHING;

    INSERT INTO payers (payer_code, payer_name, payer_type, contract_model)
    VALUES
      ('PAY-COM-01', 'Harmony Commercial', 'commercial', 'fee_for_service'),
      ('PAY-COM-02', 'Evercare Commercial', 'commercial', 'bundled'),
      ('PAY-GOV-01', 'National Resident Plan', 'government', 'fee_for_service'),
      ('PAY-EMP-01', 'Enterprise Alliance Health', 'employer', 'capitated')
    ON CONFLICT (payer_code) DO NOTHING;

    INSERT INTO plans (payer_id, plan_code, plan_name, line_of_business, deductible_amount, copay_amount)
    SELECT
      p.id,
      format('PLAN-%s-%s', split_part(p.payer_code, '-', 2), gs.n),
      format('%s Plan %s', p.payer_name, gs.n),
      CASE gs.n WHEN 1 THEN 'Individual' WHEN 2 THEN 'Family' ELSE 'Senior' END,
      500 + gs.n * 250,
      15 + gs.n * 10
    FROM payers p
    CROSS JOIN generate_series(1, 3) AS gs(n)
    ON CONFLICT (plan_code) DO NOTHING;

    INSERT INTO patients (patient_mrn, patient_name, birth_date, gender, home_region, risk_segment, chronic_conditions)
    SELECT
      format('MRN-%06s', gs),
      format('Patient %s', gs),
      current_date - ((18 + (gs % 70)) * INTERVAL '1 year') - ((gs % 365) * INTERVAL '1 day'),
      CASE gs % 3 WHEN 0 THEN 'female' WHEN 1 THEN 'male' ELSE 'other' END,
      CASE gs % 5 WHEN 0 THEN 'North' WHEN 1 THEN 'East' WHEN 2 THEN 'South' WHEN 3 THEN 'West' ELSE 'Central' END,
      CASE
        WHEN gs % 19 = 0 THEN 'complex'
        WHEN gs % 7 = 0 THEN 'high'
        WHEN gs % 3 = 0 THEN 'medium'
        ELSE 'low'
      END,
      CASE
        WHEN gs % 10 = 0 THEN '["diabetes", "hypertension"]'::jsonb
        WHEN gs % 6 = 0 THEN '["asthma"]'::jsonb
        ELSE '[]'::jsonb
      END
    FROM generate_series(1, 240) AS gs
    ON CONFLICT (patient_mrn) DO NOTHING;

    INSERT INTO encounters (encounter_no, patient_id, hospital_id, department_id, provider_id, primary_plan_id, admitted_at, discharged_at, encounter_type)
    SELECT
      format('ENC-%06s', gs),
      patient_row.id,
      dept_row.hospital_id,
      dept_row.id,
      provider_row.id,
      plan_row.id,
      now() - make_interval(days => (gs % 240), hours => gs % 24),
      now() - make_interval(days => (gs % 240) - 1, hours => 18 - (gs % 6)),
      CASE gs % 5 WHEN 0 THEN 'inpatient' WHEN 1 THEN 'ed' ELSE 'outpatient' END
    FROM generate_series(1, 960) AS gs
    CROSS JOIN LATERAL (
      SELECT id
      FROM patients
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM patients))
      LIMIT 1
    ) AS patient_row
    CROSS JOIN LATERAL (
      SELECT id, hospital_id
      FROM departments
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM departments))
      LIMIT 1
    ) AS dept_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM providers
      WHERE department_id = dept_row.id
      ORDER BY id
      OFFSET ((gs - 1) % 4)
      LIMIT 1
    ) AS provider_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM plans
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM plans))
      LIMIT 1
    ) AS plan_row
    ON CONFLICT (encounter_no) DO NOTHING;

    INSERT INTO diagnoses (encounter_id, diagnosis_rank, icd10_code, diagnosis_name, is_chronic)
    SELECT
      e.id,
      dx.rank_no,
      CASE dx.rank_no
        WHEN 1 THEN format('I1%s.%s', e.id % 9, e.id % 5)
        ELSE format('E1%s.%s', e.id % 7, dx.rank_no)
      END,
      CASE dx.rank_no
        WHEN 1 THEN 'Primary chronic condition'
        ELSE 'Secondary complexity driver'
      END,
      dx.rank_no = 1 AND e.id % 4 = 0
    FROM encounters e
    CROSS JOIN (VALUES (1), (2)) AS dx(rank_no)
    ON CONFLICT (encounter_id, diagnosis_rank) DO NOTHING;

    INSERT INTO procedures (encounter_id, procedure_rank, cpt_code, procedure_name, performed_at, billed_amount)
    SELECT
      e.id,
      proc.rank_no,
      format('CPT-%04s', ((e.id + proc.rank_no * 17) % 7000) + 1000),
      CASE proc.rank_no WHEN 1 THEN 'Primary procedure' WHEN 2 THEN 'Observation package' ELSE 'Ancillary service' END,
      e.admitted_at + make_interval(hours => 2 + (proc.rank_no::int * 3)),
      round((120 + (e.id % 70) * (proc.rank_no + 1) * 6.7)::numeric, 2)
    FROM encounters e
    CROSS JOIN LATERAL generate_series(1, 1 + (e.id % 3)) AS proc(rank_no)
    ON CONFLICT (encounter_id, procedure_rank) DO NOTHING;

    UPDATE encounters e
    SET
      total_charge = agg.total_charge,
      total_allowed = round((agg.total_charge * (0.72 + ((e.id % 12) / 100.0)))::numeric, 2)
    FROM (
      SELECT encounter_id, round(sum(billed_amount)::numeric, 2) AS total_charge
      FROM procedures
      GROUP BY encounter_id
    ) AS agg
    WHERE agg.encounter_id = e.id;

    INSERT INTO claims (claim_no, encounter_id, payer_id, plan_id, submitted_at, claim_status)
    SELECT
      format('CLM-%06s', e.id),
      e.id,
      payer_row.id,
      e.primary_plan_id,
      e.discharged_at + make_interval(days => 3 + (e.id::int % 9)),
      CASE
        WHEN e.id % 15 = 0 THEN 'denied'
        WHEN e.id % 8 = 0 THEN 'partial_denial'
        WHEN e.id % 5 = 0 THEN 'pending'
        ELSE 'paid'
      END
    FROM encounters e
    CROSS JOIN LATERAL (
      SELECT id
      FROM payers
      ORDER BY id
      OFFSET (((e.id - 1)::int) % (SELECT count(*) FROM payers))
      LIMIT 1
    ) AS payer_row
    WHERE e.id % 4 <> 0
    ON CONFLICT (claim_no) DO NOTHING;

    INSERT INTO claim_lines (claim_id, procedure_id, revenue_code, units, billed_amount, allowed_amount, line_status)
    SELECT
      c.id,
      p.id,
      format('RC-%03s', 100 + ((p.id + c.id) % 40)),
      1 + (p.id % 3),
      p.billed_amount,
      round((p.billed_amount * (0.64 + ((p.id % 9) / 100.0)))::numeric, 2),
      CASE
        WHEN c.claim_status = 'denied' THEN 'denied'
        WHEN c.claim_status = 'partial_denial' AND p.procedure_rank = 1 THEN 'denied'
        WHEN c.claim_status = 'pending' THEN 'pending'
        ELSE 'paid'
      END
    FROM claims c
    JOIN procedures p ON p.encounter_id = c.encounter_id
    ON CONFLICT DO NOTHING;

    UPDATE claims c
    SET
      billed_amount = agg.billed_amount,
      allowed_amount = agg.allowed_amount,
      paid_amount = CASE WHEN c.claim_status = 'pending' THEN 0 ELSE round((agg.allowed_amount - agg.denied_amount)::numeric, 2) END,
      denied_amount = agg.denied_amount
    FROM (
      SELECT
        claim_id,
        round(sum(billed_amount)::numeric, 2) AS billed_amount,
        round(sum(allowed_amount)::numeric, 2) AS allowed_amount,
        round(sum(CASE WHEN line_status = 'denied' THEN allowed_amount ELSE 0 END)::numeric, 2) AS denied_amount
      FROM claim_lines
      GROUP BY claim_id
    ) AS agg
    WHERE agg.claim_id = c.id;

    INSERT INTO denials (claim_line_id, denial_code, denial_reason, denial_category, denied_at, overturned_at)
    SELECT
      cl.id,
      CASE cl.id % 4 WHEN 0 THEN 'CO-16' WHEN 1 THEN 'CO-50' WHEN 2 THEN 'PR-204' ELSE 'CO-197' END,
      CASE cl.id % 4
        WHEN 0 THEN 'Missing information'
        WHEN 1 THEN 'Medical necessity not met'
        WHEN 2 THEN 'Authorization missing'
        ELSE 'Benefit exhausted'
      END,
      CASE cl.id % 3 WHEN 0 THEN 'clinical' WHEN 1 THEN 'administrative' ELSE 'eligibility' END,
      now() - make_interval(days => (cl.id::int % 120)),
      CASE WHEN cl.id % 5 = 0 THEN now() - make_interval(days => (cl.id::int % 80)) ELSE NULL END
    FROM claim_lines cl
    WHERE cl.line_status = 'denied'
    ON CONFLICT DO NOTHING;

    INSERT INTO prior_auth_requests (auth_no, patient_id, provider_id, plan_id, requested_at, service_type, auth_status, requested_amount, approved_amount)
    SELECT
      format('AUTH-%05s', gs),
      patient_row.id,
      provider_row.id,
      plan_row.id,
      now() - make_interval(days => (gs % 180), hours => gs % 24),
      CASE gs % 4 WHEN 0 THEN 'MRI' WHEN 1 THEN 'Chemotherapy' WHEN 2 THEN 'Joint Replacement' ELSE 'Biologic Therapy' END,
      CASE
        WHEN gs % 9 = 0 THEN 'denied'
        WHEN gs % 5 = 0 THEN 'partially_approved'
        WHEN gs % 3 = 0 THEN 'pending'
        ELSE 'approved'
      END,
      round((800 + (gs % 30) * 120)::numeric, 2),
      CASE
        WHEN gs % 9 = 0 THEN 0
        WHEN gs % 5 = 0 THEN round((500 + (gs % 20) * 70)::numeric, 2)
        ELSE round((800 + (gs % 30) * 120)::numeric, 2)
      END
    FROM generate_series(1, 280) AS gs
    CROSS JOIN LATERAL (
      SELECT id
      FROM patients
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM patients))
      LIMIT 1
    ) AS patient_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM providers
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM providers))
      LIMIT 1
    ) AS provider_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM plans
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM plans))
      LIMIT 1
    ) AS plan_row
    ON CONFLICT (auth_no) DO NOTHING;

    INSERT INTO pharmacy_fills (patient_id, provider_id, plan_id, ndc_code, drug_name, fill_date, days_supply, paid_amount, adherence_gap_days)
    SELECT
      patient_row.id,
      provider_row.id,
      plan_row.id,
      format('NDC-%011s', gs),
      CASE gs % 5 WHEN 0 THEN 'Metformin' WHEN 1 THEN 'Atorvastatin' WHEN 2 THEN 'Amlodipine' WHEN 3 THEN 'Insulin Glargine' ELSE 'Albuterol' END,
      current_date - (gs % 365),
      CASE gs % 3 WHEN 0 THEN 30 WHEN 1 THEN 60 ELSE 90 END,
      round((55 + (gs % 40) * 3.6)::numeric, 2),
      gs % 14
    FROM generate_series(1, 520) AS gs
    CROSS JOIN LATERAL (
      SELECT id
      FROM patients
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM patients))
      LIMIT 1
    ) AS patient_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM providers
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM providers))
      LIMIT 1
    ) AS provider_row
    CROSS JOIN LATERAL (
      SELECT id
      FROM plans
      ORDER BY id
      OFFSET ((gs - 1) % (SELECT count(*) FROM plans))
      LIMIT 1
    ) AS plan_row
    ON CONFLICT DO NOTHING;

    INSERT INTO care_management_events (patient_id, encounter_id, created_at, event_type, priority, status, assigned_team)
    SELECT
      e.patient_id,
      e.id,
      e.discharged_at + make_interval(days => 1 + (e.id::int % 12)),
      CASE e.id % 4 WHEN 0 THEN 'discharge_followup' WHEN 1 THEN 'medication_adherence' WHEN 2 THEN 'social_support' ELSE 'high_risk_rounding' END,
      CASE e.id % 6 WHEN 0 THEN 'high' WHEN 1 THEN 'medium' ELSE 'low' END,
      CASE e.id % 7 WHEN 0 THEN 'open' WHEN 1 THEN 'in_progress' ELSE 'closed' END,
      CASE e.id % 3 WHEN 0 THEN 'Transitions' WHEN 1 THEN 'Pharmacy' ELSE 'Risk Management' END
    FROM encounters e
    WHERE e.id % 3 = 0
    ON CONFLICT DO NOTHING;

    INSERT INTO lab_results (encounter_id, test_code, test_name, result_value, result_unit, abnormal_flag, collected_at)
    SELECT
      e.id,
      CASE lab.seq WHEN 1 THEN 'HBA1C' WHEN 2 THEN 'CRP' ELSE 'LDL' END,
      CASE lab.seq WHEN 1 THEN 'Hemoglobin A1c' WHEN 2 THEN 'C-Reactive Protein' ELSE 'LDL Cholesterol' END,
      round((CASE lab.seq WHEN 1 THEN 5.2 + ((e.id % 15) / 10.0) WHEN 2 THEN 1.0 + ((e.id % 30) / 5.0) ELSE 70 + (e.id % 60) END)::numeric, 2),
      CASE lab.seq WHEN 1 THEN '%' WHEN 2 THEN 'mg/L' ELSE 'mg/dL' END,
      CASE
        WHEN lab.seq = 1 AND e.id % 5 = 0 THEN 'high'
        WHEN lab.seq = 2 AND e.id % 7 = 0 THEN 'high'
        WHEN lab.seq = 3 AND e.id % 6 = 0 THEN 'high'
        ELSE 'normal'
      END,
      e.admitted_at + make_interval(hours => (lab.seq::int * 4))
    FROM encounters e
    CROSS JOIN (VALUES (1), (2), (3)) AS lab(seq)
    ON CONFLICT DO NOTHING;

    ANALYZE;
    """
)


MANUFACTURING_SQL = textwrap.dedent(
    """
    SET TIME ZONE 'UTC';

    CREATE TABLE IF NOT EXISTS plants (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      plant_code text NOT NULL UNIQUE,
      plant_name text NOT NULL,
      country text NOT NULL,
      timezone_name text NOT NULL
    );

    CREATE TABLE IF NOT EXISTS production_lines (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      plant_id bigint NOT NULL REFERENCES plants(id),
      line_code text NOT NULL UNIQUE,
      line_name text NOT NULL,
      product_family text NOT NULL,
      automation_level text NOT NULL CHECK (automation_level IN ('manual', 'semi_auto', 'fully_auto'))
    );
    CREATE INDEX IF NOT EXISTS production_lines_plant_id_idx ON production_lines (plant_id);

    CREATE TABLE IF NOT EXISTS machines (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      line_id bigint NOT NULL REFERENCES production_lines(id),
      machine_code text NOT NULL UNIQUE,
      machine_name text NOT NULL,
      machine_type text NOT NULL,
      vendor_name text NOT NULL,
      commissioned_at date NOT NULL,
      criticality_score numeric(5,2) NOT NULL
    );
    CREATE INDEX IF NOT EXISTS machines_line_id_idx ON machines (line_id);

    CREATE TABLE IF NOT EXISTS sensors (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      machine_id bigint NOT NULL REFERENCES machines(id),
      sensor_code text NOT NULL UNIQUE,
      sensor_type text NOT NULL,
      unit_name text NOT NULL,
      min_threshold numeric(12,2) NOT NULL,
      max_threshold numeric(12,2) NOT NULL,
      installed_at timestamptz NOT NULL
    );
    CREATE INDEX IF NOT EXISTS sensors_machine_id_idx ON sensors (machine_id);

    CREATE TABLE IF NOT EXISTS work_orders (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      work_order_no text NOT NULL UNIQUE,
      plant_id bigint NOT NULL REFERENCES plants(id),
      line_id bigint NOT NULL REFERENCES production_lines(id),
      product_code text NOT NULL,
      scheduled_start_at timestamptz NOT NULL,
      scheduled_end_at timestamptz NOT NULL,
      actual_start_at timestamptz NOT NULL,
      actual_end_at timestamptz NOT NULL,
      work_order_status text NOT NULL CHECK (work_order_status IN ('completed', 'delayed', 'scrapped')),
      planned_units integer NOT NULL,
      actual_units integer NOT NULL
    );
    CREATE INDEX IF NOT EXISTS work_orders_line_status_start_idx ON work_orders (line_id, work_order_status, actual_start_at DESC);

    CREATE TABLE IF NOT EXISTS work_order_operations (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      work_order_id bigint NOT NULL REFERENCES work_orders(id),
      operation_seq integer NOT NULL,
      operation_name text NOT NULL,
      machine_id bigint NOT NULL REFERENCES machines(id),
      operator_shift text NOT NULL CHECK (operator_shift IN ('A', 'B', 'C')),
      planned_minutes integer NOT NULL,
      actual_minutes integer NOT NULL,
      setup_minutes integer NOT NULL,
      UNIQUE (work_order_id, operation_seq)
    );
    CREATE INDEX IF NOT EXISTS work_order_operations_work_order_id_idx ON work_order_operations (work_order_id);
    CREATE INDEX IF NOT EXISTS work_order_operations_machine_id_idx ON work_order_operations (machine_id);

    CREATE TABLE IF NOT EXISTS sensor_readings (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      sensor_id bigint NOT NULL REFERENCES sensors(id),
      captured_at timestamptz NOT NULL,
      reading_value numeric(12,2) NOT NULL,
      reading_quality text NOT NULL CHECK (reading_quality IN ('good', 'suspect', 'bad')),
      context jsonb NOT NULL DEFAULT '{}'::jsonb,
      UNIQUE (sensor_id, captured_at)
    );
    CREATE INDEX IF NOT EXISTS sensor_readings_sensor_time_idx ON sensor_readings (sensor_id, captured_at DESC);

    CREATE TABLE IF NOT EXISTS downtime_events (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      machine_id bigint NOT NULL REFERENCES machines(id),
      work_order_id bigint NULL REFERENCES work_orders(id),
      started_at timestamptz NOT NULL,
      ended_at timestamptz NOT NULL,
      downtime_reason text NOT NULL,
      severity text NOT NULL CHECK (severity IN ('minor', 'major', 'critical')),
      minutes_lost integer NOT NULL,
      is_planned boolean NOT NULL DEFAULT false,
      UNIQUE (machine_id, started_at)
    );
    CREATE INDEX IF NOT EXISTS downtime_machine_started_idx ON downtime_events (machine_id, started_at DESC);
    CREATE INDEX IF NOT EXISTS downtime_unplanned_idx ON downtime_events (started_at DESC) WHERE is_planned IS FALSE;

    CREATE TABLE IF NOT EXISTS maintenance_work_orders (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      maintenance_no text NOT NULL UNIQUE,
      machine_id bigint NOT NULL REFERENCES machines(id),
      maintenance_type text NOT NULL CHECK (maintenance_type IN ('preventive', 'corrective', 'predictive')),
      opened_at timestamptz NOT NULL,
      closed_at timestamptz NULL,
      maintenance_status text NOT NULL CHECK (maintenance_status IN ('open', 'in_progress', 'closed')),
      root_cause text NOT NULL,
      cost_amount numeric(12,2) NOT NULL
    );
    CREATE INDEX IF NOT EXISTS maintenance_machine_status_opened_idx ON maintenance_work_orders (machine_id, maintenance_status, opened_at DESC);

    CREATE TABLE IF NOT EXISTS quality_inspections (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      work_order_id bigint NOT NULL REFERENCES work_orders(id),
      inspector_name text NOT NULL,
      inspected_at timestamptz NOT NULL,
      quality_status text NOT NULL CHECK (quality_status IN ('pass', 'warning', 'fail')),
      defect_rate numeric(8,4) NOT NULL,
      sample_size integer NOT NULL,
      UNIQUE (work_order_id)
    );
    CREATE INDEX IF NOT EXISTS inspections_work_order_time_idx ON quality_inspections (work_order_id, inspected_at DESC);

    CREATE TABLE IF NOT EXISTS defects (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      quality_inspection_id bigint NOT NULL REFERENCES quality_inspections(id),
      defect_code text NOT NULL,
      defect_category text NOT NULL,
      defect_count integer NOT NULL,
      defect_cost numeric(12,2) NOT NULL,
      disposition text NOT NULL CHECK (disposition IN ('rework', 'scrap', 'use_as_is')),
      UNIQUE (quality_inspection_id, defect_code)
    );
    CREATE INDEX IF NOT EXISTS defects_inspection_id_idx ON defects (quality_inspection_id);

    CREATE TABLE IF NOT EXISTS material_lots (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      material_lot_no text NOT NULL UNIQUE,
      supplier_name text NOT NULL,
      material_type text NOT NULL,
      received_at timestamptz NOT NULL,
      expiry_date date NOT NULL,
      quality_grade text NOT NULL CHECK (quality_grade IN ('A', 'B', 'C')),
      cost_per_unit numeric(12,2) NOT NULL
    );

    CREATE TABLE IF NOT EXISTS bom_components (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      work_order_id bigint NOT NULL REFERENCES work_orders(id),
      material_lot_id bigint NOT NULL REFERENCES material_lots(id),
      component_code text NOT NULL,
      planned_qty numeric(12,2) NOT NULL,
      issued_qty numeric(12,2) NOT NULL,
      scrap_qty numeric(12,2) NOT NULL,
      UNIQUE (work_order_id, component_code)
    );
    CREATE INDEX IF NOT EXISTS bom_components_work_order_idx ON bom_components (work_order_id);
    CREATE INDEX IF NOT EXISTS bom_components_material_lot_idx ON bom_components (material_lot_id);

    CREATE TABLE IF NOT EXISTS energy_usage_hourly (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      plant_id bigint NOT NULL REFERENCES plants(id),
      line_id bigint NULL REFERENCES production_lines(id),
      usage_hour timestamptz NOT NULL,
      kwh_used numeric(12,2) NOT NULL,
      peak_kw numeric(12,2) NOT NULL,
      co2_kg numeric(12,2) NOT NULL,
      UNIQUE (plant_id, line_id, usage_hour)
    );
    CREATE INDEX IF NOT EXISTS energy_usage_plant_hour_idx ON energy_usage_hourly (plant_id, usage_hour DESC);
    CREATE INDEX IF NOT EXISTS energy_usage_line_hour_idx ON energy_usage_hourly (line_id, usage_hour DESC);

    CREATE TABLE IF NOT EXISTS shipments (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      shipment_no text NOT NULL UNIQUE,
      work_order_id bigint NOT NULL REFERENCES work_orders(id),
      shipped_at timestamptz NOT NULL,
      destination_region text NOT NULL,
      shipped_units integer NOT NULL,
      on_time_flag boolean NOT NULL,
      carrier_name text NOT NULL
    );
    CREATE INDEX IF NOT EXISTS shipments_work_order_id_idx ON shipments (work_order_id);
    CREATE INDEX IF NOT EXISTS shipments_late_idx ON shipments (shipped_at DESC) WHERE on_time_flag IS FALSE;

    INSERT INTO plants (plant_code, plant_name, country, timezone_name)
    VALUES
      ('PLANT-SZ', 'Shenzhen Smart Plant', 'China', 'Asia/Shanghai'),
      ('PLANT-SU', 'Suzhou Precision Plant', 'China', 'Asia/Shanghai'),
      ('PLANT-CD', 'Chengdu Assembly Plant', 'China', 'Asia/Shanghai')
    ON CONFLICT (plant_code) DO NOTHING;

    INSERT INTO production_lines (plant_id, line_code, line_name, product_family, automation_level)
    SELECT
      p.id,
      format('LINE-%s-%s', right(p.plant_code, 2), gs.n),
      format('%s Line %s', p.plant_name, gs.n),
      CASE gs.n % 4 WHEN 0 THEN 'controllers' WHEN 1 THEN 'sensors' WHEN 2 THEN 'battery-packs' ELSE 'motor-drives' END,
      CASE gs.n % 3 WHEN 0 THEN 'manual' WHEN 1 THEN 'semi_auto' ELSE 'fully_auto' END
    FROM plants p
    CROSS JOIN generate_series(1, 4) AS gs(n)
    ON CONFLICT (line_code) DO NOTHING;

    INSERT INTO machines (line_id, machine_code, machine_name, machine_type, vendor_name, commissioned_at, criticality_score)
    SELECT
      l.id,
      format('MC-%s-%02s', right(l.line_code, 1), gs.n + (l.id * 10)),
      format('%s Machine %s', l.line_name, gs.n),
      CASE gs.n % 4 WHEN 0 THEN 'pick_and_place' WHEN 1 THEN 'reflow_oven' WHEN 2 THEN 'cnc' ELSE 'packaging' END,
      CASE gs.n % 3 WHEN 0 THEN 'Siemens' WHEN 1 THEN 'Fanuc' ELSE 'Bosch Rexroth' END,
      current_date - (((gs.n * 120) + (l.id::int * 20)) % 2200),
      round((70 + (gs.n * 4.5) + (l.id % 7) * 3.2)::numeric, 2)
    FROM production_lines l
    CROSS JOIN generate_series(1, 5) AS gs(n)
    ON CONFLICT (machine_code) DO NOTHING;

    INSERT INTO sensors (machine_id, sensor_code, sensor_type, unit_name, min_threshold, max_threshold, installed_at)
    SELECT
      m.id,
      format('SNS-%s-%s', m.id, sensor.seq),
      CASE sensor.seq WHEN 1 THEN 'temperature' WHEN 2 THEN 'vibration' ELSE 'power_draw' END,
      CASE sensor.seq WHEN 1 THEN 'celsius' WHEN 2 THEN 'mm_s' ELSE 'kw' END,
      CASE sensor.seq WHEN 1 THEN 15 WHEN 2 THEN 0.2 ELSE 3 END,
      CASE sensor.seq WHEN 1 THEN 92 WHEN 2 THEN 8.5 ELSE 26 END,
      now() - make_interval(days => (m.id::int % 800), hours => sensor.seq::int)
    FROM machines m
    CROSS JOIN (VALUES (1), (2), (3)) AS sensor(seq)
    ON CONFLICT (sensor_code) DO NOTHING;

    INSERT INTO work_orders (work_order_no, plant_id, line_id, product_code, scheduled_start_at, scheduled_end_at, actual_start_at, actual_end_at, work_order_status, planned_units, actual_units)
    SELECT
      format('WO-%06s', gs),
      ((gs - 1) % (SELECT count(*) FROM plants)) + 1,
      ((gs - 1) % (SELECT count(*) FROM production_lines)) + 1,
      format('FG-%04s', 1000 + (gs % 220)),
      now() - make_interval(days => (gs % 120), hours => (gs % 24)),
      now() - make_interval(days => (gs % 120), hours => (gs % 24) - 10),
      now() - make_interval(days => (gs % 120), hours => (gs % 24) - 11),
      now() - make_interval(days => (gs % 120), hours => (gs % 24) - (1 + (gs % 4))),
      CASE
        WHEN gs % 14 = 0 THEN 'scrapped'
        WHEN gs % 6 = 0 THEN 'delayed'
        ELSE 'completed'
      END,
      800 + (gs % 12) * 120,
      760 + (gs % 12) * 115 - CASE WHEN gs % 14 = 0 THEN 90 ELSE 0 END
    FROM generate_series(1, 320) AS gs
    ON CONFLICT (work_order_no) DO NOTHING;

    INSERT INTO work_order_operations (work_order_id, operation_seq, operation_name, machine_id, operator_shift, planned_minutes, actual_minutes, setup_minutes)
    SELECT
      wo.id,
      op.seq,
      CASE op.seq WHEN 1 THEN 'assembly' WHEN 2 THEN 'soldering' ELSE 'final_test' END,
      ((wo.id + op.seq) % (SELECT count(*) FROM machines)) + 1,
      CASE op.seq WHEN 1 THEN 'A' WHEN 2 THEN 'B' ELSE 'C' END,
      45 + op.seq * 15,
      42 + op.seq * 18 + (wo.id % 12),
      8 + (wo.id % 6)
    FROM work_orders wo
    CROSS JOIN (VALUES (1), (2), (3)) AS op(seq)
    ON CONFLICT (work_order_id, operation_seq) DO NOTHING;

    INSERT INTO sensor_readings (sensor_id, captured_at, reading_value, reading_quality, context)
    SELECT
      s.id,
      now() - make_interval(hours => gs.h),
      round((
        CASE s.sensor_type
          WHEN 'temperature' THEN 38 + ((s.id % 13) * 1.4) + (gs.h % 5) * 0.7
          WHEN 'vibration' THEN 1.2 + ((s.id % 9) * 0.35) + (gs.h % 4) * 0.2
          ELSE 8 + ((s.id % 11) * 0.8) + (gs.h % 6) * 0.4
        END
      )::numeric, 2),
      CASE
        WHEN s.sensor_type = 'temperature' AND gs.h % 17 = 0 THEN 'suspect'
        WHEN s.sensor_type = 'vibration' AND gs.h % 19 = 0 THEN 'bad'
        ELSE 'good'
      END,
      jsonb_build_object('shift', CASE gs.h % 3 WHEN 0 THEN 'A' WHEN 1 THEN 'B' ELSE 'C' END, 'window_hour', gs.h)
    FROM sensors s
    CROSS JOIN generate_series(1, 24) AS gs(h)
    WHERE NOT EXISTS (SELECT 1 FROM sensor_readings)
    ON CONFLICT DO NOTHING;

    INSERT INTO downtime_events (machine_id, work_order_id, started_at, ended_at, downtime_reason, severity, minutes_lost, is_planned)
    SELECT
      ((gs - 1) % (SELECT count(*) FROM machines)) + 1,
      CASE WHEN gs % 5 = 0 THEN NULL ELSE ((gs - 1) % (SELECT count(*) FROM work_orders)) + 1 END,
      now() - make_interval(days => (gs % 90), hours => gs % 24),
      now() - make_interval(days => (gs % 90), hours => gs % 24 - 1),
      CASE gs % 4 WHEN 0 THEN 'jam' WHEN 1 THEN 'sensor_drift' WHEN 2 THEN 'changeover' ELSE 'power_fluctuation' END,
      CASE gs % 7 WHEN 0 THEN 'critical' WHEN 1 THEN 'major' ELSE 'minor' END,
      12 + (gs % 140),
      gs % 6 = 0
    FROM generate_series(1, 420) AS gs
    WHERE NOT EXISTS (SELECT 1 FROM downtime_events)
    ON CONFLICT DO NOTHING;

    INSERT INTO maintenance_work_orders (maintenance_no, machine_id, maintenance_type, opened_at, closed_at, maintenance_status, root_cause, cost_amount)
    SELECT
      format('MWO-%05s', gs),
      ((gs - 1) % (SELECT count(*) FROM machines)) + 1,
      CASE gs % 3 WHEN 0 THEN 'preventive' WHEN 1 THEN 'corrective' ELSE 'predictive' END,
      now() - make_interval(days => (gs % 160), hours => gs % 24),
      CASE WHEN gs % 8 = 0 THEN NULL ELSE now() - make_interval(days => (gs % 160) - 1, hours => 8) END,
      CASE WHEN gs % 8 = 0 THEN 'open' WHEN gs % 5 = 0 THEN 'in_progress' ELSE 'closed' END,
      CASE gs % 4 WHEN 0 THEN 'bearing wear' WHEN 1 THEN 'thermal overload' WHEN 2 THEN 'alignment drift' ELSE 'air pressure instability' END,
      round((800 + (gs % 30) * 95)::numeric, 2)
    FROM generate_series(1, 260) AS gs
    ON CONFLICT (maintenance_no) DO NOTHING;

    INSERT INTO quality_inspections (work_order_id, inspector_name, inspected_at, quality_status, defect_rate, sample_size)
    SELECT
      wo.id,
      format('Inspector %s', 1 + (wo.id % 8)),
      wo.actual_end_at + make_interval(hours => 1),
      CASE
        WHEN wo.work_order_status = 'scrapped' THEN 'fail'
        WHEN wo.id % 6 = 0 THEN 'warning'
        ELSE 'pass'
      END,
      round((CASE WHEN wo.work_order_status = 'scrapped' THEN 0.18 WHEN wo.id % 6 = 0 THEN 0.045 ELSE 0.008 END)::numeric, 4),
      32 + (wo.id % 18)
    FROM work_orders wo
    ON CONFLICT DO NOTHING;

    INSERT INTO defects (quality_inspection_id, defect_code, defect_category, defect_count, defect_cost, disposition)
    SELECT
      qi.id,
      CASE def.seq WHEN 1 THEN 'SOLDER_VOID' WHEN 2 THEN 'MISALIGNMENT' ELSE 'PACKAGING_DAMAGE' END,
      CASE def.seq WHEN 1 THEN 'process' WHEN 2 THEN 'assembly' ELSE 'logistics' END,
      1 + ((qi.id + def.seq) % 7),
      round((40 + ((qi.id + def.seq) % 25) * 18)::numeric, 2),
      CASE def.seq WHEN 1 THEN 'rework' WHEN 2 THEN 'scrap' ELSE 'use_as_is' END
    FROM quality_inspections qi
    CROSS JOIN LATERAL generate_series(1, CASE WHEN qi.quality_status = 'pass' THEN 1 ELSE 2 END) AS def(seq)
    WHERE qi.quality_status <> 'pass' OR qi.id % 9 = 0
    ON CONFLICT DO NOTHING;

    INSERT INTO material_lots (material_lot_no, supplier_name, material_type, received_at, expiry_date, quality_grade, cost_per_unit)
    SELECT
      format('LOT-%06s', gs),
      CASE gs % 4 WHEN 0 THEN 'Jiangsu Materials' WHEN 1 THEN 'Pearl River Components' WHEN 2 THEN 'West Circuit Supply' ELSE 'Delta Precision Metals' END,
      CASE gs % 5 WHEN 0 THEN 'pcb' WHEN 1 THEN 'housing' WHEN 2 THEN 'connector' WHEN 3 THEN 'battery_cell' ELSE 'adhesive' END,
      now() - make_interval(days => (gs % 220)),
      current_date + (((gs % 540) + 90)::int),
      CASE gs % 5 WHEN 0 THEN 'C' WHEN 1 THEN 'B' ELSE 'A' END,
      round((6 + (gs % 35) * 1.4)::numeric, 2)
    FROM generate_series(1, 420) AS gs
    ON CONFLICT (material_lot_no) DO NOTHING;

    INSERT INTO bom_components (work_order_id, material_lot_id, component_code, planned_qty, issued_qty, scrap_qty)
    SELECT
      wo.id,
      ((wo.id + comp.seq) % (SELECT count(*) FROM material_lots)) + 1,
      format('CMP-%03s', 10 + ((wo.id + comp.seq) % 70)),
      round((30 + comp.seq * 8 + (wo.id % 14))::numeric, 2),
      round((30 + comp.seq * 8 + (wo.id % 14) + (wo.id % 3))::numeric, 2),
      round(((wo.id % 5) * 0.8)::numeric, 2)
    FROM work_orders wo
    CROSS JOIN (VALUES (1), (2), (3), (4)) AS comp(seq)
    ON CONFLICT DO NOTHING;

    INSERT INTO energy_usage_hourly (plant_id, line_id, usage_hour, kwh_used, peak_kw, co2_kg)
    SELECT
      p.id,
      l.id,
      date_trunc('hour', now() - make_interval(hours => gs.h)),
      round((180 + (l.id % 6) * 22 + (gs.h % 24) * 3.5)::numeric, 2),
      round((36 + (l.id % 5) * 4 + (gs.h % 12) * 0.9)::numeric, 2),
      round((95 + (l.id % 7) * 8 + (gs.h % 18) * 1.6)::numeric, 2)
    FROM plants p
    JOIN production_lines l ON l.plant_id = p.id
    CROSS JOIN generate_series(1, 72) AS gs(h)
    WHERE NOT EXISTS (SELECT 1 FROM energy_usage_hourly)
    ON CONFLICT DO NOTHING;

    INSERT INTO shipments (shipment_no, work_order_id, shipped_at, destination_region, shipped_units, on_time_flag, carrier_name)
    SELECT
      format('FGS-%06s', wo.id),
      wo.id,
      wo.actual_end_at + make_interval(days => 1 + (wo.id::int % 4)),
      CASE wo.id % 5 WHEN 0 THEN 'North' WHEN 1 THEN 'East' WHEN 2 THEN 'South' WHEN 3 THEN 'West' ELSE 'Central' END,
      GREATEST(wo.actual_units - ((wo.id % 9) * 3), 0),
      wo.work_order_status = 'completed' AND wo.id % 7 <> 0,
      CASE wo.id % 4 WHEN 0 THEN 'SF Freight' WHEN 1 THEN 'JD Express' WHEN 2 THEN 'Sinotrans' ELSE 'Yunda Industrial' END
    FROM work_orders wo
    ON CONFLICT (shipment_no) DO NOTHING;

    ANALYZE;
    """
)


RETAIL_COMMENTS_SQL = textwrap.dedent(
    """
    COMMENT ON TABLE regions IS '销售区域维表，用于门店、客户和营收的区域归属分析。';
    COMMENT ON COLUMN regions.id IS '区域主键。';
    COMMENT ON COLUMN regions.region_code IS '区域编码，例如 NORTH、EAST。';
    COMMENT ON COLUMN regions.region_name IS '区域名称。';

    COMMENT ON TABLE stores IS '门店维表，记录门店所属区域、业态、城市和启用状态。';
    COMMENT ON COLUMN stores.id IS '门店主键。';
    COMMENT ON COLUMN stores.store_code IS '门店编码。';
    COMMENT ON COLUMN stores.region_id IS '所属销售区域 ID。';
    COMMENT ON COLUMN stores.store_name IS '门店名称。';
    COMMENT ON COLUMN stores.format_type IS '门店业态，例如旗舰店、商场店、社区店、奥莱店。';
    COMMENT ON COLUMN stores.city IS '门店所在城市。';
    COMMENT ON COLUMN stores.opened_at IS '门店开业时间。';
    COMMENT ON COLUMN stores.is_active IS '门店是否仍在营业。';

    COMMENT ON TABLE suppliers IS '供应商维表，用于商品采购来源和质量评分分析。';
    COMMENT ON COLUMN suppliers.id IS '供应商主键。';
    COMMENT ON COLUMN suppliers.supplier_code IS '供应商编码。';
    COMMENT ON COLUMN suppliers.supplier_name IS '供应商名称。';
    COMMENT ON COLUMN suppliers.country IS '供应商所在国家或地区。';
    COMMENT ON COLUMN suppliers.quality_score IS '供应商质量评分。';

    COMMENT ON TABLE categories IS '商品类目维表，支持父子类目层级。';
    COMMENT ON COLUMN categories.id IS '类目主键。';
    COMMENT ON COLUMN categories.category_code IS '类目编码。';
    COMMENT ON COLUMN categories.parent_category_id IS '父级类目 ID，空表示一级类目。';
    COMMENT ON COLUMN categories.category_name IS '类目名称。';

    COMMENT ON TABLE products IS '商品维表，记录 SKU、类目、供应商、价格和商品属性。';
    COMMENT ON COLUMN products.id IS '商品主键。';
    COMMENT ON COLUMN products.sku IS '商品 SKU 编码。';
    COMMENT ON COLUMN products.category_id IS '所属类目 ID。';
    COMMENT ON COLUMN products.supplier_id IS '供应商 ID。';
    COMMENT ON COLUMN products.product_name IS '商品名称。';
    COMMENT ON COLUMN products.status IS '商品状态，例如 active、seasonal、retired。';
    COMMENT ON COLUMN products.cost_price IS '商品成本价。';
    COMMENT ON COLUMN products.unit_price IS '商品标价或标准售价。';
    COMMENT ON COLUMN products.launch_date IS '商品上市日期。';
    COMMENT ON COLUMN products.attributes IS '商品扩展属性，JSON 对象。';

    COMMENT ON TABLE customers IS '客户维表，记录会员等级、偏好渠道、所属区域和客户画像。';
    COMMENT ON COLUMN customers.id IS '客户主键。';
    COMMENT ON COLUMN customers.external_customer_code IS '外部客户编码。';
    COMMENT ON COLUMN customers.region_id IS '客户归属区域 ID。';
    COMMENT ON COLUMN customers.preferred_store_id IS '客户偏好门店 ID，可为空。';
    COMMENT ON COLUMN customers.customer_name IS '客户名称。';
    COMMENT ON COLUMN customers.tier IS '会员等级，例如 standard、silver、gold、platinum。';
    COMMENT ON COLUMN customers.preferred_channel IS '客户偏好渠道，例如 online、store、hybrid。';
    COMMENT ON COLUMN customers.acquired_at IS '客户首次获取时间。';
    COMMENT ON COLUMN customers.churn_risk IS '客户流失风险评分。';
    COMMENT ON COLUMN customers.profile IS '客户画像扩展信息，JSON 对象。';

    COMMENT ON TABLE promotions IS '营销活动维表，描述活动渠道、折扣类型、时间窗口和目标人群。';
    COMMENT ON COLUMN promotions.id IS '营销活动主键。';
    COMMENT ON COLUMN promotions.promotion_code IS '营销活动编码。';
    COMMENT ON COLUMN promotions.promotion_name IS '营销活动名称。';
    COMMENT ON COLUMN promotions.channel IS '活动渠道，例如 online、store、all。';
    COMMENT ON COLUMN promotions.discount_type IS '折扣类型，例如 percentage、coupon、bundle。';
    COMMENT ON COLUMN promotions.discount_value IS '折扣值。';
    COMMENT ON COLUMN promotions.start_at IS '活动开始时间。';
    COMMENT ON COLUMN promotions.end_at IS '活动结束时间。';
    COMMENT ON COLUMN promotions.target_segment IS '目标客户分群。';
    COMMENT ON COLUMN promotions.rules_json IS '活动规则扩展信息，JSON 对象。';

    COMMENT ON TABLE orders IS '订单主事实表，记录客户、门店、渠道、状态和订单金额。';
    COMMENT ON COLUMN orders.id IS '订单主键。';
    COMMENT ON COLUMN orders.order_no IS '订单编号。';
    COMMENT ON COLUMN orders.customer_id IS '下单客户 ID。';
    COMMENT ON COLUMN orders.store_id IS '履约或归属门店 ID。';
    COMMENT ON COLUMN orders.promotion_id IS '关联营销活动 ID，可为空。';
    COMMENT ON COLUMN orders.ordered_at IS '下单时间。';
    COMMENT ON COLUMN orders.status IS '订单状态，例如 completed、returned、cancelled。';
    COMMENT ON COLUMN orders.channel IS '下单渠道，例如 online、store、app。';
    COMMENT ON COLUMN orders.payment_status IS '支付状态，例如 paid、partial_refund、refunded。';
    COMMENT ON COLUMN orders.shipping_fee IS '订单运费。';
    COMMENT ON COLUMN orders.gross_amount IS '订单毛额，通常为行项目标价乘数量汇总。';
    COMMENT ON COLUMN orders.discount_amount IS '订单折扣金额。';
    COMMENT ON COLUMN orders.net_amount IS '订单净额，包含折扣和运费后的口径。';

    COMMENT ON TABLE order_items IS '订单行项目事实表，记录订单内商品、数量、价格和折扣。';
    COMMENT ON COLUMN order_items.id IS '订单行主键。';
    COMMENT ON COLUMN order_items.order_id IS '所属订单 ID。';
    COMMENT ON COLUMN order_items.line_no IS '订单内行号。';
    COMMENT ON COLUMN order_items.product_id IS '商品 ID。';
    COMMENT ON COLUMN order_items.quantity IS '购买数量。';
    COMMENT ON COLUMN order_items.list_price IS '行项目标价。';
    COMMENT ON COLUMN order_items.discount_amount IS '行项目折扣金额。';
    COMMENT ON COLUMN order_items.net_amount IS '行项目净额。';

    COMMENT ON TABLE payments IS '支付事实表，记录订单支付渠道、支付状态、退款和风控评分。';
    COMMENT ON COLUMN payments.id IS '支付主键。';
    COMMENT ON COLUMN payments.payment_reference IS '支付流水号。';
    COMMENT ON COLUMN payments.order_id IS '关联订单 ID。';
    COMMENT ON COLUMN payments.payment_provider IS '支付服务商。';
    COMMENT ON COLUMN payments.paid_at IS '支付完成时间。';
    COMMENT ON COLUMN payments.status IS '支付状态，例如 captured、partial_refund、refunded。';
    COMMENT ON COLUMN payments.amount IS '支付金额。';
    COMMENT ON COLUMN payments.refund_amount IS '退款金额。';
    COMMENT ON COLUMN payments.risk_score IS '支付风险评分。';

    COMMENT ON TABLE shipments IS '物流配送事实表，记录订单发货、承运商、承诺到达和实际配送状态。';
    COMMENT ON COLUMN shipments.id IS '物流记录主键。';
    COMMENT ON COLUMN shipments.shipment_no IS '物流单号。';
    COMMENT ON COLUMN shipments.order_id IS '关联订单 ID。';
    COMMENT ON COLUMN shipments.warehouse_code IS '发货仓库编码。';
    COMMENT ON COLUMN shipments.carrier IS '承运商名称。';
    COMMENT ON COLUMN shipments.shipped_at IS '发货时间。';
    COMMENT ON COLUMN shipments.delivered_at IS '签收时间，空表示尚未签收或异常。';
    COMMENT ON COLUMN shipments.promised_at IS '承诺送达时间。';
    COMMENT ON COLUMN shipments.status IS '物流状态，例如 delivered、in_transit、exception。';
    COMMENT ON COLUMN shipments.actual_days IS '实际配送天数。';

    COMMENT ON TABLE returns IS '退货事实表，记录退货原因、商品状态、审批金额和是否重新入库。';
    COMMENT ON COLUMN returns.id IS '退货主键。';
    COMMENT ON COLUMN returns.return_no IS '退货单号。';
    COMMENT ON COLUMN returns.order_item_id IS '关联订单行 ID。';
    COMMENT ON COLUMN returns.returned_at IS '退货发生时间。';
    COMMENT ON COLUMN returns.reason_code IS '退货原因编码。';
    COMMENT ON COLUMN returns.condition_grade IS '退回商品状态等级。';
    COMMENT ON COLUMN returns.approved_amount IS '审批通过的退款或补偿金额。';
    COMMENT ON COLUMN returns.restocked IS '是否已重新入库。';

    COMMENT ON TABLE inventory_snapshots IS '库存快照事实表，按门店、商品和日期记录库存水位。';
    COMMENT ON COLUMN inventory_snapshots.id IS '库存快照主键。';
    COMMENT ON COLUMN inventory_snapshots.store_id IS '门店 ID。';
    COMMENT ON COLUMN inventory_snapshots.product_id IS '商品 ID。';
    COMMENT ON COLUMN inventory_snapshots.snapshot_date IS '库存快照日期。';
    COMMENT ON COLUMN inventory_snapshots.on_hand_qty IS '账面现货数量。';
    COMMENT ON COLUMN inventory_snapshots.reserved_qty IS '已预留数量。';
    COMMENT ON COLUMN inventory_snapshots.reorder_point IS '补货触发点。';
    COMMENT ON COLUMN inventory_snapshots.stock_value IS '库存金额。';

    COMMENT ON TABLE loyalty_ledger IS '会员积分流水表，记录积分获取、兑换和人工调整。';
    COMMENT ON COLUMN loyalty_ledger.id IS '积分流水主键。';
    COMMENT ON COLUMN loyalty_ledger.customer_id IS '客户 ID。';
    COMMENT ON COLUMN loyalty_ledger.order_id IS '关联订单 ID，可为空。';
    COMMENT ON COLUMN loyalty_ledger.event_at IS '积分事件时间。';
    COMMENT ON COLUMN loyalty_ledger.event_type IS '积分事件类型，例如 earn、redeem、manual_adjustment。';
    COMMENT ON COLUMN loyalty_ledger.points_delta IS '本次积分变动值。';
    COMMENT ON COLUMN loyalty_ledger.balance_after IS '事件发生后的积分余额。';

    COMMENT ON TABLE customer_service_cases IS '客户服务工单表，记录售后、退款、配送和会员问题的处理情况。';
    COMMENT ON COLUMN customer_service_cases.id IS '客服工单主键。';
    COMMENT ON COLUMN customer_service_cases.case_no IS '客服工单编号。';
    COMMENT ON COLUMN customer_service_cases.customer_id IS '客户 ID。';
    COMMENT ON COLUMN customer_service_cases.order_id IS '关联订单 ID，可为空。';
    COMMENT ON COLUMN customer_service_cases.created_at IS '工单创建时间。';
    COMMENT ON COLUMN customer_service_cases.case_type IS '工单类型，例如 delivery、refund、quality、membership。';
    COMMENT ON COLUMN customer_service_cases.severity IS '工单严重程度。';
    COMMENT ON COLUMN customer_service_cases.resolution_status IS '处理状态，例如 resolved、escalated、open。';
    COMMENT ON COLUMN customer_service_cases.resolution_hours IS '工单解决耗时，单位小时。';
    COMMENT ON COLUMN customer_service_cases.sentiment_score IS '客户情绪评分。';
    COMMENT ON COLUMN customer_service_cases.notes IS '工单扩展备注，JSON 对象。';
    """
)


MANUFACTURING_COMMENTS_SQL = textwrap.dedent(
    """
    COMMENT ON TABLE plants IS '工厂维表，记录制造基地基本信息和时区。';
    COMMENT ON COLUMN plants.id IS '工厂主键。';
    COMMENT ON COLUMN plants.plant_code IS '工厂编码。';
    COMMENT ON COLUMN plants.plant_name IS '工厂名称。';
    COMMENT ON COLUMN plants.country IS '工厂所在国家或地区。';
    COMMENT ON COLUMN plants.timezone_name IS '工厂所在时区名称。';

    COMMENT ON TABLE production_lines IS '生产线维表，记录工厂下的产线、产品族和自动化水平。';
    COMMENT ON COLUMN production_lines.id IS '产线主键。';
    COMMENT ON COLUMN production_lines.plant_id IS '所属工厂 ID。';
    COMMENT ON COLUMN production_lines.line_code IS '产线编码。';
    COMMENT ON COLUMN production_lines.line_name IS '产线名称。';
    COMMENT ON COLUMN production_lines.product_family IS '产线主要产品族。';
    COMMENT ON COLUMN production_lines.automation_level IS '自动化水平，例如 manual、semi_auto、fully_auto。';

    COMMENT ON TABLE machines IS '设备维表，记录产线设备、厂商、投产日期和关键程度。';
    COMMENT ON COLUMN machines.id IS '设备主键。';
    COMMENT ON COLUMN machines.line_id IS '所属产线 ID。';
    COMMENT ON COLUMN machines.machine_code IS '设备编码。';
    COMMENT ON COLUMN machines.machine_name IS '设备名称。';
    COMMENT ON COLUMN machines.machine_type IS '设备类型，例如贴片、回流焊、CNC、包装。';
    COMMENT ON COLUMN machines.vendor_name IS '设备供应商名称。';
    COMMENT ON COLUMN machines.commissioned_at IS '设备投产日期。';
    COMMENT ON COLUMN machines.criticality_score IS '设备关键程度评分。';

    COMMENT ON TABLE sensors IS '传感器维表，记录设备传感器类型、单位和阈值范围。';
    COMMENT ON COLUMN sensors.id IS '传感器主键。';
    COMMENT ON COLUMN sensors.machine_id IS '所属设备 ID。';
    COMMENT ON COLUMN sensors.sensor_code IS '传感器编码。';
    COMMENT ON COLUMN sensors.sensor_type IS '传感器类型，例如 temperature、vibration、power_draw。';
    COMMENT ON COLUMN sensors.unit_name IS '读数单位。';
    COMMENT ON COLUMN sensors.min_threshold IS '正常下限阈值。';
    COMMENT ON COLUMN sensors.max_threshold IS '正常上限阈值。';
    COMMENT ON COLUMN sensors.installed_at IS '传感器安装时间。';

    COMMENT ON TABLE work_orders IS '生产工单主表，记录计划/实际时间、状态和产量。';
    COMMENT ON COLUMN work_orders.id IS '工单主键。';
    COMMENT ON COLUMN work_orders.work_order_no IS '工单编号。';
    COMMENT ON COLUMN work_orders.plant_id IS '所属工厂 ID。';
    COMMENT ON COLUMN work_orders.line_id IS '所属产线 ID。';
    COMMENT ON COLUMN work_orders.product_code IS '成品或产品编码。';
    COMMENT ON COLUMN work_orders.scheduled_start_at IS '计划开始时间。';
    COMMENT ON COLUMN work_orders.scheduled_end_at IS '计划结束时间。';
    COMMENT ON COLUMN work_orders.actual_start_at IS '实际开始时间。';
    COMMENT ON COLUMN work_orders.actual_end_at IS '实际结束时间。';
    COMMENT ON COLUMN work_orders.work_order_status IS '工单状态，例如 completed、delayed、scrapped。';
    COMMENT ON COLUMN work_orders.planned_units IS '计划产量。';
    COMMENT ON COLUMN work_orders.actual_units IS '实际合格或产出数量。';

    COMMENT ON TABLE work_order_operations IS '工单工序明细表，记录每道工序、设备、班次和工时。';
    COMMENT ON COLUMN work_order_operations.id IS '工序记录主键。';
    COMMENT ON COLUMN work_order_operations.work_order_id IS '所属工单 ID。';
    COMMENT ON COLUMN work_order_operations.operation_seq IS '工序顺序号。';
    COMMENT ON COLUMN work_order_operations.operation_name IS '工序名称。';
    COMMENT ON COLUMN work_order_operations.machine_id IS '执行工序的设备 ID。';
    COMMENT ON COLUMN work_order_operations.operator_shift IS '操作班次，例如 A、B、C。';
    COMMENT ON COLUMN work_order_operations.planned_minutes IS '计划工时，单位分钟。';
    COMMENT ON COLUMN work_order_operations.actual_minutes IS '实际工时，单位分钟。';
    COMMENT ON COLUMN work_order_operations.setup_minutes IS '换型或准备时间，单位分钟。';

    COMMENT ON TABLE sensor_readings IS '传感器读数事实表，按传感器和时间记录设备运行状态。';
    COMMENT ON COLUMN sensor_readings.id IS '传感器读数主键。';
    COMMENT ON COLUMN sensor_readings.sensor_id IS '传感器 ID。';
    COMMENT ON COLUMN sensor_readings.captured_at IS '读数采集时间。';
    COMMENT ON COLUMN sensor_readings.reading_value IS '传感器读数值。';
    COMMENT ON COLUMN sensor_readings.reading_quality IS '读数质量，例如 good、suspect、bad。';
    COMMENT ON COLUMN sensor_readings.context IS '采集上下文，JSON 对象。';

    COMMENT ON TABLE downtime_events IS '停机事件表，记录设备停机原因、严重程度和损失分钟数。';
    COMMENT ON COLUMN downtime_events.id IS '停机事件主键。';
    COMMENT ON COLUMN downtime_events.machine_id IS '停机设备 ID。';
    COMMENT ON COLUMN downtime_events.work_order_id IS '关联工单 ID，可为空。';
    COMMENT ON COLUMN downtime_events.started_at IS '停机开始时间。';
    COMMENT ON COLUMN downtime_events.ended_at IS '停机结束时间。';
    COMMENT ON COLUMN downtime_events.downtime_reason IS '停机原因。';
    COMMENT ON COLUMN downtime_events.severity IS '严重程度，例如 minor、major、critical。';
    COMMENT ON COLUMN downtime_events.minutes_lost IS '损失时间，单位分钟。';
    COMMENT ON COLUMN downtime_events.is_planned IS '是否为计划内停机。';

    COMMENT ON TABLE maintenance_work_orders IS '设备维修工单表，记录预防性、纠正性和预测性维护。';
    COMMENT ON COLUMN maintenance_work_orders.id IS '维修工单主键。';
    COMMENT ON COLUMN maintenance_work_orders.maintenance_no IS '维修工单编号。';
    COMMENT ON COLUMN maintenance_work_orders.machine_id IS '维修设备 ID。';
    COMMENT ON COLUMN maintenance_work_orders.maintenance_type IS '维修类型，例如 preventive、corrective、predictive。';
    COMMENT ON COLUMN maintenance_work_orders.opened_at IS '维修工单打开时间。';
    COMMENT ON COLUMN maintenance_work_orders.closed_at IS '维修工单关闭时间，空表示未关闭。';
    COMMENT ON COLUMN maintenance_work_orders.maintenance_status IS '维修状态，例如 open、in_progress、closed。';
    COMMENT ON COLUMN maintenance_work_orders.root_cause IS '根因描述。';
    COMMENT ON COLUMN maintenance_work_orders.cost_amount IS '维修成本金额。';

    COMMENT ON TABLE quality_inspections IS '质量检验主表，记录工单质检结果、缺陷率和抽样规模。';
    COMMENT ON COLUMN quality_inspections.id IS '质检记录主键。';
    COMMENT ON COLUMN quality_inspections.work_order_id IS '被检工单 ID。';
    COMMENT ON COLUMN quality_inspections.inspector_name IS '质检员名称。';
    COMMENT ON COLUMN quality_inspections.inspected_at IS '质检时间。';
    COMMENT ON COLUMN quality_inspections.quality_status IS '质检状态，例如 pass、warning、fail。';
    COMMENT ON COLUMN quality_inspections.defect_rate IS '缺陷率。';
    COMMENT ON COLUMN quality_inspections.sample_size IS '抽样数量。';

    COMMENT ON TABLE defects IS '缺陷明细表，记录质检中发现的缺陷类别、数量、成本和处置方式。';
    COMMENT ON COLUMN defects.id IS '缺陷记录主键。';
    COMMENT ON COLUMN defects.quality_inspection_id IS '所属质检记录 ID。';
    COMMENT ON COLUMN defects.defect_code IS '缺陷编码。';
    COMMENT ON COLUMN defects.defect_category IS '缺陷类别。';
    COMMENT ON COLUMN defects.defect_count IS '缺陷数量。';
    COMMENT ON COLUMN defects.defect_cost IS '缺陷成本金额。';
    COMMENT ON COLUMN defects.disposition IS '缺陷处置方式，例如 rework、scrap、use_as_is。';

    COMMENT ON TABLE material_lots IS '物料批次维表，记录供应商、物料类型、有效期、等级和单位成本。';
    COMMENT ON COLUMN material_lots.id IS '物料批次主键。';
    COMMENT ON COLUMN material_lots.material_lot_no IS '物料批次号。';
    COMMENT ON COLUMN material_lots.supplier_name IS '供应商名称。';
    COMMENT ON COLUMN material_lots.material_type IS '物料类型。';
    COMMENT ON COLUMN material_lots.received_at IS '物料收货时间。';
    COMMENT ON COLUMN material_lots.expiry_date IS '物料有效期日期。';
    COMMENT ON COLUMN material_lots.quality_grade IS '物料质量等级，例如 A、B、C。';
    COMMENT ON COLUMN material_lots.cost_per_unit IS '物料单位成本。';

    COMMENT ON TABLE bom_components IS '工单物料消耗表，记录每个工单的组件计划、发料和报废数量。';
    COMMENT ON COLUMN bom_components.id IS 'BOM 消耗记录主键。';
    COMMENT ON COLUMN bom_components.work_order_id IS '所属工单 ID。';
    COMMENT ON COLUMN bom_components.material_lot_id IS '使用的物料批次 ID。';
    COMMENT ON COLUMN bom_components.component_code IS '组件编码。';
    COMMENT ON COLUMN bom_components.planned_qty IS '计划用量。';
    COMMENT ON COLUMN bom_components.issued_qty IS '实际发料数量。';
    COMMENT ON COLUMN bom_components.scrap_qty IS '报废数量。';

    COMMENT ON TABLE energy_usage_hourly IS '小时级能源使用事实表，记录工厂或产线的用电、峰值功率和碳排。';
    COMMENT ON COLUMN energy_usage_hourly.id IS '能源记录主键。';
    COMMENT ON COLUMN energy_usage_hourly.plant_id IS '工厂 ID。';
    COMMENT ON COLUMN energy_usage_hourly.line_id IS '产线 ID，可为空表示工厂级别。';
    COMMENT ON COLUMN energy_usage_hourly.usage_hour IS '能源统计小时。';
    COMMENT ON COLUMN energy_usage_hourly.kwh_used IS '用电量，单位 kWh。';
    COMMENT ON COLUMN energy_usage_hourly.peak_kw IS '峰值功率，单位 kW。';
    COMMENT ON COLUMN energy_usage_hourly.co2_kg IS '估算碳排放量，单位 kg。';

    COMMENT ON TABLE shipments IS '成品出货事实表，记录工单对应成品发运、目的区域和是否准时。';
    COMMENT ON COLUMN shipments.id IS '出货记录主键。';
    COMMENT ON COLUMN shipments.shipment_no IS '成品出货单号。';
    COMMENT ON COLUMN shipments.work_order_id IS '关联生产工单 ID。';
    COMMENT ON COLUMN shipments.shipped_at IS '出货时间。';
    COMMENT ON COLUMN shipments.destination_region IS '目的区域。';
    COMMENT ON COLUMN shipments.shipped_units IS '出货数量。';
    COMMENT ON COLUMN shipments.on_time_flag IS '是否准时发运。';
    COMMENT ON COLUMN shipments.carrier_name IS '承运商名称。';
    """
)


HEALTHCARE_COMMENTS_SQL = textwrap.dedent(
    """
    COMMENT ON TABLE hospitals IS '医院主数据表，记录医疗机构基本信息与区域归属。';
    COMMENT ON COLUMN hospitals.id IS '医院主键。';
    COMMENT ON COLUMN hospitals.hospital_code IS '医院编码。';
    COMMENT ON COLUMN hospitals.hospital_name IS '医院名称。';
    COMMENT ON COLUMN hospitals.region IS '医院所在大区。';
    COMMENT ON COLUMN hospitals.ownership_type IS '医院属性，例如公立、私立、教学。';

    COMMENT ON TABLE departments IS '医院科室维表，用于描述科室与服务线。';
    COMMENT ON COLUMN departments.id IS '科室主键。';
    COMMENT ON COLUMN departments.hospital_id IS '所属医院 ID。';
    COMMENT ON COLUMN departments.department_code IS '科室编码。';
    COMMENT ON COLUMN departments.department_name IS '科室名称。';
    COMMENT ON COLUMN departments.service_line IS '科室所属服务线，例如急诊、心血管、肿瘤。';

    COMMENT ON TABLE providers IS '医生与执业提供者维表。';
    COMMENT ON COLUMN providers.id IS '提供者主键。';
    COMMENT ON COLUMN providers.provider_code IS '提供者编码。';
    COMMENT ON COLUMN providers.hospital_id IS '提供者所属医院 ID。';
    COMMENT ON COLUMN providers.department_id IS '提供者所属科室 ID。';
    COMMENT ON COLUMN providers.provider_name IS '提供者姓名。';
    COMMENT ON COLUMN providers.specialty IS '执业专科。';
    COMMENT ON COLUMN providers.employment_type IS '用工类型，例如正式、签约、访问。';
    COMMENT ON COLUMN providers.start_date IS '开始执业日期。';

    COMMENT ON TABLE payers IS '付款方维表，表示商业险、政府险、雇主计划等支付主体。';
    COMMENT ON COLUMN payers.id IS '付款方主键。';
    COMMENT ON COLUMN payers.payer_code IS '付款方编码。';
    COMMENT ON COLUMN payers.payer_name IS '付款方名称。';
    COMMENT ON COLUMN payers.payer_type IS '付款方类型，例如 commercial、government、employer。';
    COMMENT ON COLUMN payers.contract_model IS '合同模式，例如按项目付费、打包支付、人头付费。';

    COMMENT ON TABLE plans IS '保险计划维表，挂在付款方之下。';
    COMMENT ON COLUMN plans.id IS '保险计划主键。';
    COMMENT ON COLUMN plans.payer_id IS '所属付款方 ID。';
    COMMENT ON COLUMN plans.plan_code IS '保险计划编码。';
    COMMENT ON COLUMN plans.plan_name IS '保险计划名称。';
    COMMENT ON COLUMN plans.line_of_business IS '业务线，例如个人、家庭、老年。';
    COMMENT ON COLUMN plans.deductible_amount IS '起付额。';
    COMMENT ON COLUMN plans.copay_amount IS '固定共付金额。';

    COMMENT ON TABLE patients IS '患者维表。';
    COMMENT ON COLUMN patients.id IS '患者主键。';
    COMMENT ON COLUMN patients.patient_mrn IS '患者病案号 MRN。';
    COMMENT ON COLUMN patients.patient_name IS '患者姓名。';
    COMMENT ON COLUMN patients.birth_date IS '出生日期。';
    COMMENT ON COLUMN patients.gender IS '性别。';
    COMMENT ON COLUMN patients.home_region IS '患者常住地区。';
    COMMENT ON COLUMN patients.risk_segment IS '风险分层，例如 low、medium、high、complex。';
    COMMENT ON COLUMN patients.chronic_conditions IS '慢病列表，JSON 数组。';

    COMMENT ON TABLE encounters IS '就诊事实表，一次门诊、住院或急诊视为一次 encounter。';
    COMMENT ON COLUMN encounters.id IS '就诊主键。';
    COMMENT ON COLUMN encounters.encounter_no IS '就诊编号。';
    COMMENT ON COLUMN encounters.patient_id IS '患者 ID。';
    COMMENT ON COLUMN encounters.hospital_id IS '就诊医院 ID。';
    COMMENT ON COLUMN encounters.department_id IS '就诊科室 ID。';
    COMMENT ON COLUMN encounters.provider_id IS '主诊提供者 ID。';
    COMMENT ON COLUMN encounters.primary_plan_id IS '本次就诊主保险计划 ID。';
    COMMENT ON COLUMN encounters.admitted_at IS '入院或接诊时间。';
    COMMENT ON COLUMN encounters.discharged_at IS '出院或结束时间。';
    COMMENT ON COLUMN encounters.encounter_type IS '就诊类型，例如 inpatient、outpatient、ed。';
    COMMENT ON COLUMN encounters.total_charge IS '总收费金额。';
    COMMENT ON COLUMN encounters.total_allowed IS '付款方认可金额。';

    COMMENT ON TABLE diagnoses IS '诊断明细表，记录 encounter 对应的 ICD10 诊断。';
    COMMENT ON COLUMN diagnoses.id IS '诊断主键。';
    COMMENT ON COLUMN diagnoses.encounter_id IS '所属就诊 ID。';
    COMMENT ON COLUMN diagnoses.diagnosis_rank IS '诊断顺位，1 通常为主诊断。';
    COMMENT ON COLUMN diagnoses.icd10_code IS 'ICD10 编码。';
    COMMENT ON COLUMN diagnoses.diagnosis_name IS '诊断名称。';
    COMMENT ON COLUMN diagnoses.is_chronic IS '是否为慢病相关诊断。';

    COMMENT ON TABLE procedures IS '处置与手术明细表，记录 encounter 对应的 CPT 处置。';
    COMMENT ON COLUMN procedures.id IS '处置主键。';
    COMMENT ON COLUMN procedures.encounter_id IS '所属就诊 ID。';
    COMMENT ON COLUMN procedures.procedure_rank IS '处置顺位。';
    COMMENT ON COLUMN procedures.cpt_code IS 'CPT 编码。';
    COMMENT ON COLUMN procedures.procedure_name IS '处置名称。';
    COMMENT ON COLUMN procedures.performed_at IS '执行时间。';
    COMMENT ON COLUMN procedures.billed_amount IS '该处置收费金额。';

    COMMENT ON TABLE claims IS '理赔主表，一次 encounter 产生一张 claim。';
    COMMENT ON COLUMN claims.id IS '理赔主键。';
    COMMENT ON COLUMN claims.claim_no IS '理赔单号。';
    COMMENT ON COLUMN claims.encounter_id IS '对应就诊 ID。';
    COMMENT ON COLUMN claims.payer_id IS '付款方 ID。';
    COMMENT ON COLUMN claims.plan_id IS '保险计划 ID。';
    COMMENT ON COLUMN claims.submitted_at IS '向付款方提交理赔的时间。';
    COMMENT ON COLUMN claims.claim_status IS '理赔状态，例如 paid、denied、pending。';
    COMMENT ON COLUMN claims.billed_amount IS '理赔申报金额。';
    COMMENT ON COLUMN claims.allowed_amount IS '付款方认可金额。';
    COMMENT ON COLUMN claims.paid_amount IS '付款方最终支付金额。';
    COMMENT ON COLUMN claims.denied_amount IS '被拒付金额。';

    COMMENT ON TABLE claim_lines IS '理赔行项目表，claim 下的费用明细粒度。';
    COMMENT ON COLUMN claim_lines.id IS '理赔行主键。';
    COMMENT ON COLUMN claim_lines.claim_id IS '所属理赔 ID。';
    COMMENT ON COLUMN claim_lines.procedure_id IS '关联处置 ID，可为空。';
    COMMENT ON COLUMN claim_lines.revenue_code IS '收入代码或收费分类代码。';
    COMMENT ON COLUMN claim_lines.units IS '计费单位数。';
    COMMENT ON COLUMN claim_lines.billed_amount IS '行项目申报金额。';
    COMMENT ON COLUMN claim_lines.allowed_amount IS '行项目认可金额。';
    COMMENT ON COLUMN claim_lines.line_status IS '行项目状态，例如 paid、denied、pending。';

    COMMENT ON TABLE denials IS '拒付事件表，记录被拒付的 claim line 及原因。';
    COMMENT ON COLUMN denials.id IS '拒付事件主键。';
    COMMENT ON COLUMN denials.claim_line_id IS '对应理赔行 ID。';
    COMMENT ON COLUMN denials.denial_code IS '拒付代码。';
    COMMENT ON COLUMN denials.denial_reason IS '拒付原因文本。';
    COMMENT ON COLUMN denials.denial_category IS '拒付类别，例如 clinical、administrative、eligibility。';
    COMMENT ON COLUMN denials.denied_at IS '拒付发生时间。';
    COMMENT ON COLUMN denials.overturned_at IS '拒付被推翻或申诉成功的时间，空表示仍未解决。';

    COMMENT ON TABLE prior_auth_requests IS '事前授权申请表，用于高成本服务的预审批管理。';
    COMMENT ON COLUMN prior_auth_requests.id IS '授权申请主键。';
    COMMENT ON COLUMN prior_auth_requests.auth_no IS '授权申请编号。';
    COMMENT ON COLUMN prior_auth_requests.patient_id IS '患者 ID。';
    COMMENT ON COLUMN prior_auth_requests.provider_id IS '申请医生或提供者 ID。';
    COMMENT ON COLUMN prior_auth_requests.plan_id IS '保险计划 ID。';
    COMMENT ON COLUMN prior_auth_requests.requested_at IS '申请提交时间。';
    COMMENT ON COLUMN prior_auth_requests.service_type IS '申请服务类型，例如 MRI、化疗、关节置换。';
    COMMENT ON COLUMN prior_auth_requests.auth_status IS '授权状态，例如 approved、partially_approved、denied、pending。';
    COMMENT ON COLUMN prior_auth_requests.requested_amount IS '申请金额。';
    COMMENT ON COLUMN prior_auth_requests.approved_amount IS '获批金额。';

    COMMENT ON TABLE pharmacy_fills IS '药房配药事实表，用于依从性与药费分析。';
    COMMENT ON COLUMN pharmacy_fills.id IS '配药主键。';
    COMMENT ON COLUMN pharmacy_fills.patient_id IS '患者 ID。';
    COMMENT ON COLUMN pharmacy_fills.provider_id IS '开药提供者 ID。';
    COMMENT ON COLUMN pharmacy_fills.plan_id IS '保险计划 ID。';
    COMMENT ON COLUMN pharmacy_fills.ndc_code IS '药品 NDC 编码。';
    COMMENT ON COLUMN pharmacy_fills.drug_name IS '药品名称。';
    COMMENT ON COLUMN pharmacy_fills.fill_date IS '配药日期。';
    COMMENT ON COLUMN pharmacy_fills.days_supply IS '本次配药覆盖天数。';
    COMMENT ON COLUMN pharmacy_fills.paid_amount IS '药房实际支付金额。';
    COMMENT ON COLUMN pharmacy_fills.adherence_gap_days IS '依从性缺口天数。';

    COMMENT ON TABLE care_management_events IS '照护管理事件表，用于跟踪高风险患者跟进与协同任务。';
    COMMENT ON COLUMN care_management_events.id IS '照护事件主键。';
    COMMENT ON COLUMN care_management_events.patient_id IS '患者 ID。';
    COMMENT ON COLUMN care_management_events.encounter_id IS '关联就诊 ID，可为空。';
    COMMENT ON COLUMN care_management_events.created_at IS '事件创建时间。';
    COMMENT ON COLUMN care_management_events.event_type IS '事件类型，例如出院随访、风险干预、病例管理。';
    COMMENT ON COLUMN care_management_events.priority IS '优先级。';
    COMMENT ON COLUMN care_management_events.status IS '处理状态，例如 open、in_progress、closed。';
    COMMENT ON COLUMN care_management_events.assigned_team IS '负责团队。';

    COMMENT ON TABLE lab_results IS '检验结果表，记录 encounter 对应的关键化验指标。';
    COMMENT ON COLUMN lab_results.id IS '检验结果主键。';
    COMMENT ON COLUMN lab_results.encounter_id IS '所属就诊 ID。';
    COMMENT ON COLUMN lab_results.test_code IS '检验项目编码。';
    COMMENT ON COLUMN lab_results.test_name IS '检验项目名称。';
    COMMENT ON COLUMN lab_results.result_value IS '检验数值结果。';
    COMMENT ON COLUMN lab_results.result_unit IS '结果单位。';
    COMMENT ON COLUMN lab_results.abnormal_flag IS '是否异常，例如 normal、high、low。';
    COMMENT ON COLUMN lab_results.collected_at IS '采样或出结果时间。';
    """
)


DEFAULT_LAB_DATASOURCE_ID = "lab-retail-docker"

LAB_SPECS: tuple[LabSpec, ...] = (
    LabSpec(
        key="retail",
        db_name="lab_retail_analytics",
        datasource_id="lab-retail-docker",
        display_name="零售全渠道运营实验库",
        summary="零售订单、库存、促销、会员与售后混合场景，适合测试营收、库存周转、退货和门店绩效问题。",
        ddl_and_seed_sql=RETAIL_SQL + "\n" + RETAIL_COMMENTS_SQL,
    ),
    LabSpec(
        key="healthcare",
        db_name="lab_healthcare_claims",
        datasource_id="lab-healthcare-docker",
        display_name="医疗理赔风控实验库",
        summary="覆盖患者、就诊、诊断、处置、理赔、拒付、药房和 prior auth 的复杂医疗数据集。",
        ddl_and_seed_sql=HEALTHCARE_SQL + "\n" + HEALTHCARE_COMMENTS_SQL,
    ),
    LabSpec(
        key="manufacturing",
        db_name="lab_manufacturing_iot",
        datasource_id="lab-manufacturing-docker",
        display_name="制造物联网质量实验库",
        summary="覆盖工厂、产线、工单、设备传感器、停机、维修、质检和能源使用的工业场景。",
        ddl_and_seed_sql=MANUFACTURING_SQL + "\n" + MANUFACTURING_COMMENTS_SQL,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runtime-host",
        default="postgres",
        help="Host embedded into registered datasource URLs. Use `postgres` for Compose, `127.0.0.1` for host-run backend.",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8000",
        help="Running FastAPI base URL used to trigger onboarding.",
    )
    parser.add_argument(
        "--skip-onboarding",
        action="store_true",
        help="Only provision databases and register datasources without calling onboarding.",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate selected lab databases before provisioning. Safe for these generated labs.",
    )
    parser.add_argument(
        "--labs",
        nargs="*",
        choices=[spec.key for spec in LAB_SPECS],
        help="Only provision selected labs. Defaults to all labs.",
    )
    return parser.parse_args()


def selected_specs(args: argparse.Namespace) -> list[LabSpec]:
    if not args.labs:
        return list(LAB_SPECS)
    wanted = set(args.labs)
    return [spec for spec in LAB_SPECS if spec.key in wanted]


def metadata_admin_dsn() -> str:
    settings = get_settings()
    return raw_psycopg_dsn(settings.sql_agent_database_url)


def metadata_driver_url() -> URL:
    settings = get_settings()
    return make_url(settings.sql_agent_database_url)


def business_admin_dsn(db_name: str) -> str:
    return metadata_driver_url().set(drivername="postgresql", database=db_name).render_as_string(
        hide_password=False
    )


def registered_connection_url(db_name: str, runtime_host: str) -> str:
    url = metadata_driver_url()
    return URL.create(
        drivername="postgresql+psycopg",
        username=url.username,
        password=url.password,
        host=runtime_host,
        port=url.port,
        database=db_name,
    ).render_as_string(hide_password=False)


def ensure_database_exists(admin_dsn: str, db_name: str) -> bool:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,),
        ).fetchone()
        if exists:
            return False
        conn.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(db_name)
            )
        )
        return True


def drop_database_if_exists(admin_dsn: str, db_name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (db_name,),
        )
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name))
        )


def apply_sql_script(db_name: str, sql_script: str) -> None:
    with psycopg.connect(business_admin_dsn(db_name)) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_script)
        conn.commit()


def upsert_registered_datasource(spec: LabSpec, runtime_host: str) -> None:
    connection_url = registered_connection_url(spec.db_name, runtime_host)
    is_default = spec.datasource_id == DEFAULT_LAB_DATASOURCE_ID
    with psycopg.connect(metadata_admin_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO datasources (id, display_name, dialect, connection_url, is_default)
                VALUES (%s, %s, 'postgresql', %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET
                  display_name = EXCLUDED.display_name,
                  dialect = EXCLUDED.dialect,
                  connection_url = EXCLUDED.connection_url,
                  is_default = EXCLUDED.is_default
                """,
                (spec.datasource_id, spec.display_name, connection_url, is_default),
            )
        conn.commit()


def apply_default_lab_datasource() -> None:
    """Ensure 零售全渠道运营实验库 is the sole default datasource for Workbench/demo."""
    with psycopg.connect(metadata_admin_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE datasources SET is_default = false")
            cur.execute(
                "UPDATE datasources SET is_default = true WHERE id = %s",
                (DEFAULT_LAB_DATASOURCE_ID,),
            )
        conn.commit()


def ensure_backend_available(api_base_url: str) -> None:
    with urllib.request.urlopen(f"{api_base_url.rstrip('/')}/health", timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"backend health check failed with status {response.status}")


def trigger_onboarding(api_base_url: str, datasource_id: str) -> dict:
    url = f"{api_base_url.rstrip('/')}/api/v1/admin/datasources/{datasource_id}/onboarding/run"
    request = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def fetch_seed_summary(spec: LabSpec) -> dict[str, int]:
    summary_queries = {
        "lab_retail_analytics": {
            "orders": "SELECT count(*) FROM orders",
            "order_items": "SELECT count(*) FROM order_items",
            "customers": "SELECT count(*) FROM customers",
            "products": "SELECT count(*) FROM products",
        },
        "lab_healthcare_claims": {
            "encounters": "SELECT count(*) FROM encounters",
            "claims": "SELECT count(*) FROM claims",
            "claim_lines": "SELECT count(*) FROM claim_lines",
            "patients": "SELECT count(*) FROM patients",
        },
        "lab_manufacturing_iot": {
            "work_orders": "SELECT count(*) FROM work_orders",
            "sensor_readings": "SELECT count(*) FROM sensor_readings",
            "downtime_events": "SELECT count(*) FROM downtime_events",
            "machines": "SELECT count(*) FROM machines",
        },
    }
    query_map = summary_queries[spec.db_name]
    output: dict[str, int] = {}
    with psycopg.connect(business_admin_dsn(spec.db_name)) as conn:
        with conn.cursor() as cur:
            for label, statement in query_map.items():
                cur.execute(statement)
                output[label] = int(cur.fetchone()[0])
    return output


def main() -> int:
    args = parse_args()
    specs = selected_specs(args)
    admin_dsn = metadata_admin_dsn()

    print(f"Using metadata/admin DSN: {metadata_driver_url().set(password='***')}")
    print(f"Registering datasource URLs with runtime host: {args.runtime_host}")
    print()

    for spec in specs:
        if args.recreate:
            drop_database_if_exists(admin_dsn, spec.db_name)
        created = ensure_database_exists(admin_dsn, spec.db_name)
        apply_sql_script(spec.db_name, spec.ddl_and_seed_sql)
        upsert_registered_datasource(spec, args.runtime_host)
        counters = fetch_seed_summary(spec)
        print(
            f"[provisioned] {spec.display_name} | db={spec.db_name} | "
            f"datasource_id={spec.datasource_id} | created={created}"
        )
        print(f"  summary: {spec.summary}")
        print("  seeded counts: " + ", ".join(f"{key}={value}" for key, value in counters.items()))

    apply_default_lab_datasource()
    print(f"[default] datasource_id={DEFAULT_LAB_DATASOURCE_ID} (零售全渠道运营实验库)")

    if args.skip_onboarding:
        print()
        print("Skipping onboarding as requested.")
        return 0

    print()
    print("Checking backend health before onboarding...")
    try:
        ensure_backend_available(args.api_base_url)
    except Exception as exc:  # pragma: no cover - operator guidance
        print(f"[warning] backend unavailable, skipping onboarding: {exc}")
        return 0

    for spec in specs:
        print(f"[onboarding] {spec.datasource_id} ...")
        try:
            payload = trigger_onboarding(args.api_base_url, spec.datasource_id)
        except urllib.error.HTTPError as exc:  # pragma: no cover - operator guidance
            body = exc.read().decode("utf-8", errors="replace")
            print(f"[warning] onboarding failed for {spec.datasource_id}: HTTP {exc.code} {body}")
            continue
        except Exception as exc:  # pragma: no cover - operator guidance
            print(f"[warning] onboarding failed for {spec.datasource_id}: {exc}")
            continue
        print(
            "  result: "
            f"analysis_status={payload.get('analysis_status')} | "
            f"summary_length={len(str(payload.get('summary', '')))} | "
            f"skill_packs={len(payload.get('skill_packs', []))} | "
            f"memory_count={payload.get('active_memory_count', 0)}"
        )

    print()
    print("Provisioning complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
