import argparse
import os
import sqlite3
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


def bare_code(code: str) -> str:
    """去掉交易所后缀，如 600519.SH → 600519"""
    return code.split(".")[0]


def is_etf(code: str) -> bool:
    """判断是否为 ETF：沪市 51x/58x，深市 15x/16x"""
    c = bare_code(code)
    return c.startswith(("51", "58", "15", "16"))


DATA_DIR = Path(os.environ.get("ASTOCK_DATA_DIR", Path.home() / ".local/share/astock"))
DB_PATH  = DATA_DIR / "astock.db"


def clean_value(val):
    """清理 ="0" 这类 Excel 导出格式"""
    if isinstance(val, str):
        m = re.match(r'^="(.*)"$', val.strip())
        if m:
            return m.group(1)
    return val


def parse_numeric(val):
    """将清理后的值转为数字，空字符串转为 None"""
    cleaned = clean_value(val)
    if cleaned == "" or pd.isna(cleaned):
        return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS fund_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            currency        TEXT,
            security_name   TEXT,
            trade_date      TEXT,
            trade_price     REAL,
            trade_qty       REAL,
            amount          REAL,
            balance         REAL,
            remaining_qty   REAL,
            contract_id     TEXT,
            serial_no       TEXT UNIQUE,
            business_type   TEXT,
            stamp_duty      REAL,
            commission      REAL,
            handling_fee    REAL,
            regulatory_fee  REAL,
            settlement_fee  REAL,
            transfer_fee    REAL,
            other_fee       REAL,
            security_code   TEXT,
            shareholder_id  TEXT,
            remark          TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            security_code   TEXT,
            security_name   TEXT,
            direction       TEXT,
            trade_date      TEXT,
            trade_time      TEXT,
            trade_price     REAL,
            trade_qty       REAL,
            trade_amount    REAL,
            trade_no        TEXT UNIQUE,
            contract_id     TEXT,
            shareholder_id  TEXT
        );
    """)
    conn.commit()


def import_money(conn: sqlite3.Connection, path: Path) -> tuple[int, int]:
    df = pd.read_csv(path, sep="\t", encoding="gbk", dtype=str)

    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        serial_no = str(row.get("流水号", "")).strip()
        if not serial_no:
            skipped += 1
            continue

        try:
            conn.execute(
                """
                INSERT INTO fund_records (
                    currency, security_name, trade_date, trade_price, trade_qty,
                    amount, balance, remaining_qty, contract_id, serial_no,
                    business_type, stamp_duty, commission, handling_fee,
                    regulatory_fee, settlement_fee, transfer_fee, other_fee,
                    security_code, shareholder_id, remark
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    clean_value(row.get("币种")),
                    clean_value(row.get("证券名称")),
                    clean_value(row.get("成交日期")),
                    parse_numeric(row.get("成交价格")),
                    parse_numeric(row.get("成交数量")),
                    parse_numeric(row.get("发生金额")),
                    parse_numeric(row.get("资金余额")),
                    parse_numeric(row.get("剩余数量")),
                    clean_value(row.get("合同编号")),
                    serial_no,
                    clean_value(row.get("业务名称")),
                    parse_numeric(row.get("印花税")),
                    parse_numeric(row.get("佣金")),
                    parse_numeric(row.get("经手费")),
                    parse_numeric(row.get("证管费")),
                    parse_numeric(row.get("结算费")),
                    parse_numeric(row.get("过户费")),
                    parse_numeric(row.get("其他费用")),
                    clean_value(row.get("证券代码")),
                    clean_value(row.get("股东代码")),
                    clean_value(row.get("备注")),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    return inserted, skipped


def import_stock(conn: sqlite3.Connection, path: Path) -> tuple[int, int]:
    df = pd.read_csv(path, sep="\t", encoding="gbk", dtype=str)

    inserted = 0
    skipped = 0
    for _, row in df.iterrows():
        trade_no = str(row.get("成交编号", "")).strip()
        if not trade_no:
            skipped += 1
            continue

        try:
            conn.execute(
                """
                INSERT INTO trade_records (
                    security_code, security_name, direction,
                    trade_date, trade_time, trade_price,
                    trade_qty, trade_amount, trade_no,
                    contract_id, shareholder_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    clean_value(row.get("证券代码")),
                    clean_value(row.get("证券名称")),
                    clean_value(row.get("买卖标志")),
                    clean_value(row.get("成交日期")),
                    clean_value(row.get("成交时间")),
                    parse_numeric(row.get("成交价格")),
                    parse_numeric(row.get("成交数量")),
                    parse_numeric(row.get("成交金额")),
                    trade_no,
                    clean_value(row.get("委托编号")),
                    clean_value(row.get("股东代码")),
                ),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    return inserted, skipped


# CSV 列名的别名映射（宽松识别不同来源的文件头）
# 必须字段：trade_date, open, high, low, close
_KLINE_COL_ALIASES = {
    "trade_date": ["trade_date", "date", "日期", "交易日期"],
    "open":       ["open", "开盘", "开盘价"],
    "high":       ["high", "最高", "最高价"],
    "low":        ["low", "最低", "最低价"],
    "close":      ["close", "收盘", "收盘价"],
    "volume":     ["volume", "vol", "成交量"],
    "amount":     ["amount", "成交额", "成交金额"],
    "change_pct": ["change_pct", "pct_chg", "涨跌幅"],
    # tushare 格式：ts_code 用于自动提取证券代码
    "_ts_code":   ["ts_code"],
    # tushare amount 单位标记（千元）—— 通过列名 "amount" 在 tushare 文件中识别
}

_REQUIRED_COLS = ["trade_date", "open", "high", "low", "close"]

_REQUIRED_COL_HINT = "\n".join(
    f"  {std:12s}  可接受列名：{', '.join(aliases)}"
    for std, aliases in _KLINE_COL_ALIASES.items()
    if std in _REQUIRED_COLS
)


def _resolve_kline_columns(df: pd.DataFrame) -> dict[str, str]:
    """返回 {标准列名: 实际列名} 的映射（含可选列）。"""
    cols_lower = {c.lower(): c for c in df.columns}
    mapping = {}
    for std, aliases in _KLINE_COL_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                mapping[std] = alias
                break
            if alias.lower() in cols_lower:
                mapping[std] = cols_lower[alias.lower()]
                break
    return mapping


def import_kline(conn: sqlite3.Connection, path: Path, code: str | None) -> tuple[int, int, str]:
    """
    从 CSV 文件导入 K 线数据到 kline_daily 表。
    code 为 None 时，自动从 ts_code 列提取裸代码（要求文件内只有一个标的）。
    返回 (inserted, skipped, resolved_code)。
    """
    init_kline_table(conn)
    df = pd.read_csv(path, dtype=str)
    col_map = _resolve_kline_columns(df)

    missing = [c for c in _REQUIRED_COLS if c not in col_map]
    if missing:
        raise ValueError(
            f"CSV 缺少以下必须字段（列名无法识别）：{missing}\n\n"
            f"必须字段及可接受的列名：\n{_REQUIRED_COL_HINT}\n\n"
            f"文件实际列名：{list(df.columns)}"
        )

    # 自动从 ts_code 列提取代码
    if code is None:
        if "_ts_code" not in col_map:
            raise ValueError(
                "未指定 --code，且 CSV 中没有 ts_code 列，无法确定证券代码。\n"
                "请使用 --code <证券代码> 指定，或在 CSV 中保留 ts_code 列。"
            )
        ts_codes = df[col_map["_ts_code"]].dropna().unique()
        if len(ts_codes) != 1:
            raise ValueError(
                f"CSV 中包含多个标的（{list(ts_codes)}），请用 --code 指定其中一个，或拆分文件后分别导入。"
            )
        code = bare_code(ts_codes[0])

    # 重命名为标准列名（跳过内部用的 _ts_code）
    rename_map = {v: k for k, v in col_map.items() if not k.startswith("_")}
    df = df.rename(columns=rename_map)

    for col in ["open", "high", "low", "close", "volume", "amount", "change_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = float("nan")

    # tushare 文件的 amount 单位是千元，换算为元
    if "_ts_code" in col_map and "amount" in df.columns:
        df["amount"] = df["amount"] * 1000

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

    inserted = skipped = 0
    for _, row in df.iterrows():
        try:
            conn.execute(
                """
                INSERT INTO kline_daily
                    (security_code, trade_date, open, high, low, close, volume, amount, change_pct)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (code, row["trade_date"], row["open"], row["high"], row["low"],
                 row["close"], row.get("volume"), row.get("amount"), row.get("change_pct")),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped, code


def init_kline_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kline_daily (
            security_code  TEXT,
            trade_date     TEXT,
            open           REAL,
            high           REAL,
            low            REAL,
            close          REAL,
            volume         REAL,
            amount         REAL,
            change_pct     REAL,
            PRIMARY KEY (security_code, trade_date)
        )
    """)
    conn.commit()


def _to_ts_code(code: str) -> str:
    """
    将裸代码转为 tushare 格式（带交易所后缀）。
    代码本身若已含后缀（如 600519.SH）则直接返回。
    沪市：60xxxx（主板）、68xxxx（科创板）、5xxxxx（ETF/债券基金）
    深市：00xxxx（主板）、30xxxx（创业板）、1xxxxx（深市 ETF/LOF）
    """
    if "." in code:
        return code  # 已有后缀，直接用
    c = bare_code(code)
    if c.startswith(("6", "5", "9")):
        return f"{c}.SH"
    return f"{c}.SZ"


def _fetch_tushare(code: str, start: str, end: str) -> pd.DataFrame:
    """通过 tushare 抓取日K线。ETF/债券基金用 fund_daily，股票用 daily。"""
    import tushare as ts
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("未设置环境变量 TUSHARE_TOKEN")
    ts.set_token(token)
    pro = ts.pro_api()
    ts_code = _to_ts_code(code)
    start_fmt = start.replace("-", "")
    end_fmt = end.replace("-", "")
    if is_etf(code):
        df = pro.fund_daily(ts_code=ts_code, start_date=start_fmt, end_date=end_fmt)
    else:
        df = pro.daily(ts_code=ts_code, start_date=start_fmt, end_date=end_fmt)
    if df is None or df.empty:
        return pd.DataFrame()
    # tushare amount 单位为千元，统一换算为元
    df = df.rename(columns={"vol": "volume", "pct_chg": "change_pct"})
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce") * 1000
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume", "change_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["trade_date", "open", "high", "low", "close", "volume", "amount", "change_pct"]]


def fetch_kline(code: str, start: str, end: str) -> pd.DataFrame:
    """
    抓取日K线，目前仅支持 tushare（TUSHARE_TOKEN 环境变量）。
    失败时返回空 DataFrame 并提示用 CSV 导入。
    """
    try:
        return _fetch_tushare(code, start, end)
    except Exception as e:
        print(f"\n  抓取失败: {e}", file=sys.stderr)
        print(f"  提示：可用 CSV 文件手动导入 K线数据：", file=sys.stderr)
        print(f"    astock import --kline <file.csv> --code {bare_code(code)}", file=sys.stderr)
        return pd.DataFrame()


def upsert_klines(conn: sqlite3.Connection, code: str, df: pd.DataFrame) -> tuple[int, int]:
    inserted = skipped = 0
    for _, row in df.iterrows():
        try:
            conn.execute(
                """
                INSERT INTO kline_daily
                    (security_code, trade_date, open, high, low, close, volume, amount, change_pct)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (code, row["trade_date"], row["open"], row["high"], row["low"],
                 row["close"], row["volume"], row["amount"], row["change_pct"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


def cmd_fetch(args):
    conn = sqlite3.connect(DB_PATH)
    init_kline_table(conn)

    # 确定要抓的标的：默认从 trade_records 自动提取，也可 --codes 指定
    if args.codes:
        codes_names = {c: c for c in args.codes}
    else:
        rows = conn.execute("""
            SELECT DISTINCT security_code, security_name
            FROM trade_records
            WHERE direction IN ('买入','卖出')
              AND security_code NOT IN ('799999','204002','204007')
        """).fetchall()
        codes_names = {r[0]: r[1] for r in rows}

    if not codes_names:
        print("没有找到需要抓取的标的，请先导入交易数据或用 --codes 指定")
        conn.close()
        return

    # 确定日期范围：默认从 trade_records 最早日期到昨天（已确定不再变化）
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = args.start or conn.execute(
        "SELECT MIN(trade_date) FROM trade_records"
    ).fetchone()[0]
    # 将 YYYYMMDD 格式转换为 YYYY-MM-DD
    if start and len(start) == 8:
        start = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    end = args.end or yesterday

    print(f"抓取区间：{start} ~ {end}（共 {len(codes_names)} 个标的）")

    total_ins = total_skip = 0
    for code, name in codes_names.items():
        # 检查该标的已有的最新日期，做增量抓取
        latest = conn.execute(
            "SELECT MAX(trade_date) FROM kline_daily WHERE security_code=?", (code,)
        ).fetchone()[0]
        fetch_start = start
        if latest:
            # 从已有最新日期的次日开始
            next_day = (date.fromisoformat(latest) + timedelta(days=1)).strftime("%Y-%m-%d")
            if next_day > end:
                print(f"  {name}({code}) 已是最新，跳过")
                continue
            fetch_start = next_day

        print(f"  {name}({code}) {fetch_start} ~ {end} ...", end=" ", flush=True)
        df = fetch_kline(code, fetch_start, end)
        if df.empty:
            print("无数据")
            continue
        ins, skip = upsert_klines(conn, code, df)
        total_ins += ins
        total_skip += skip
        print(f"新增 {ins} 条，跳过 {skip} 条")

    conn.close()
    print(f"\n完成：共新增 {total_ins} 条，跳过 {total_skip} 条")


def build_trade_markers(conn: sqlite3.Connection, code: str, kline_dates: list[str]):
    """
    从 trade_records 汇总每日操作，返回用于标注的 DataFrame。
    规则：
      - 同一天既有买又有卖 → T（做T）
      - 只有买 → B
      - 只有卖 → S
    返回 index=trade_date(str), columns=[label, avg_price, direction]
    """
    rows = conn.execute("""
        SELECT trade_date, direction, trade_price, trade_qty
        FROM trade_records
        WHERE security_code=?
          AND direction IN ('买入','卖出')
        ORDER BY trade_date, trade_time
    """, (code,)).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["trade_date", "direction", "trade_price", "trade_qty"])
    df["trade_qty"] = df["trade_qty"].abs()
    df["trade_date"] = df["trade_date"].astype(str).str[:8]  # 保证 YYYYMMDD
    # 转为 YYYY-MM-DD 与 kline 对齐
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d")

    results = []
    for day, grp in df.groupby("trade_date"):
        if day not in kline_dates:
            continue
        has_buy  = (grp["direction"] == "买入").any()
        has_sell = (grp["direction"] == "卖出").any()

        if has_buy and has_sell:
            label = "T"
            # 用买入均价代表标注位置（买入方向）
            buy_grp = grp[grp["direction"] == "买入"]
            avg = (buy_grp["trade_price"] * buy_grp["trade_qty"]).sum() / buy_grp["trade_qty"].sum()
            direction = "买入"
        elif has_buy:
            label = "B"
            avg = (grp["trade_price"] * grp["trade_qty"]).sum() / grp["trade_qty"].sum()
            direction = "买入"
        else:
            label = "S"
            avg = (grp["trade_price"] * grp["trade_qty"]).sum() / grp["trade_qty"].sum()
            direction = "卖出"

        results.append({"trade_date": day, "label": label, "avg_price": avg, "direction": direction})

    return pd.DataFrame(results).set_index("trade_date") if results else pd.DataFrame()


def cmd_chart(args):
    import matplotlib
    matplotlib.use("TkAgg" if args.show else "Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import mplfinance as mpf

    conn = sqlite3.connect(DB_PATH)

    # 查 K 线数据
    query = "SELECT trade_date, open, high, low, close, volume FROM kline_daily WHERE security_code=?"
    params = [args.code]
    if args.start:
        query += " AND trade_date >= ?"
        params.append(args.start)
    if args.end:
        query += " AND trade_date <= ?"
        params.append(args.end)
    query += " ORDER BY trade_date"

    kline = pd.read_sql(query, conn, params=params)
    if kline.empty:
        print(f"没有找到 {args.code} 的K线数据，请先执行 astock fetch")
        conn.close()
        return

    # 查标的名称
    name_row = conn.execute(
        "SELECT security_name FROM trade_records WHERE security_code=? LIMIT 1", (args.code,)
    ).fetchone()
    security_name = name_row[0] if name_row else args.code

    kline["trade_date"] = pd.to_datetime(kline["trade_date"])
    kline = kline.set_index("trade_date")
    kline.index.name = "Date"
    for col in ["open", "high", "low", "close", "volume"]:
        kline[col] = pd.to_numeric(kline[col])
    kline.columns = ["Open", "High", "Low", "Close", "Volume"]

    kline_dates = kline.index.strftime("%Y-%m-%d").tolist()
    markers_df = build_trade_markers(conn, args.code, kline_dates)
    conn.close()

    # A股配色：红涨绿跌
    mc = mpf.make_marketcolors(
        up="red", down="green",
        edge={"up": "red", "down": "green"},
        wick={"up": "red", "down": "green"},
        volume={"up": "red", "down": "green"},
    )
    style = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle="--",
        gridcolor="#e0e0e0",
        facecolor="white",
        figcolor="white",
        rc={"font.family": ["Arial Unicode MS", "Heiti TC", "sans-serif"]},
    )

    # 构造标注 addplot
    addplots = []
    if not markers_df.empty:
        # 对齐到 kline index
        buy_scatter  = pd.Series(index=kline.index, dtype=float)
        sell_scatter = pd.Series(index=kline.index, dtype=float)
        t_scatter    = pd.Series(index=kline.index, dtype=float)

        for dt_str, row in markers_df.iterrows():
            dt = pd.Timestamp(dt_str)
            if dt not in kline.index:
                continue
            low  = kline.loc[dt, "Low"]
            high = kline.loc[dt, "High"]
            span = kline["High"].max() - kline["Low"].min()
            offset = span * 0.02

            if row["label"] == "B":
                buy_scatter[dt] = low - offset
            elif row["label"] == "S":
                sell_scatter[dt] = high + offset
            elif row["label"] == "T":
                buy_scatter[dt] = low - offset

        if buy_scatter.notna().any():
            addplots.append(mpf.make_addplot(
                buy_scatter, type="scatter", markersize=120,
                marker="^", color="red",
            ))
        if sell_scatter.notna().any():
            addplots.append(mpf.make_addplot(
                sell_scatter, type="scatter", markersize=120,
                marker="v", color="green",
            ))
        if t_scatter.notna().any():
            addplots.append(mpf.make_addplot(
                t_scatter, type="scatter", markersize=120,
                marker="D", color="orange",
            ))

    fig, axes = mpf.plot(
        kline,
        type="candle",
        style=style,
        title=f"{security_name}（{args.code}）日K线",
        volume=True,
        addplot=addplots if addplots else [],
        returnfig=True,
        figsize=(16, 9),
        tight_layout=True,
    )

    ax = axes[0]

    # 在标注点上方/下方写文字
    if not markers_df.empty:
        x_index = {d: i for i, d in enumerate(kline_dates)}
        span = kline["High"].max() - kline["Low"].min()
        offset = span * 0.02

        for dt_str, row in markers_df.iterrows():
            if dt_str not in x_index:
                continue
            xi = x_index[dt_str]
            dt = pd.Timestamp(dt_str)
            low  = kline.loc[dt, "Low"]
            high = kline.loc[dt, "High"]
            label = row["label"]

            if label in ("B", "T"):
                color = "red" if label == "B" else "orange"
                ax.text(xi, low - offset * 2.5, label,
                        ha="center", va="top", fontsize=9,
                        fontweight="bold", color=color)
            else:
                ax.text(xi, high + offset * 2.5, label,
                        ha="center", va="bottom", fontsize=9,
                        fontweight="bold", color="green")

    # 图例
    legend_handles = [
        mpatches.Patch(color="red",    label="B 买入"),
        mpatches.Patch(color="green",  label="S 卖出"),
        mpatches.Patch(color="orange", label="T 做T"),
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=9)

    out_path = Path(args.output) if args.output else Path(f"{args.code}_kline.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"图表已保存：{out_path.resolve()}")

    if args.show:
        plt.show()

    plt.close(fig)


def calc_positions(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    用均价成本法逐笔重建持仓，返回每个标的的：
      security_code, security_name, qty, cost_price, cost_total,
      realized_pnl（含费用）, total_buy_amount, total_sell_amount
    """
    trades = pd.read_sql("""
        SELECT t.security_code, t.security_name, t.trade_date, t.trade_time,
               t.direction, t.trade_price, t.trade_qty, t.trade_amount, t.contract_id
        FROM trade_records t
        WHERE t.direction IN ('买入','卖出')
        ORDER BY t.security_code, t.trade_date, t.trade_time
    """, conn)
    trades["trade_qty"] = trades["trade_qty"].abs()

    # 关联费用
    fees = pd.read_sql("""
        SELECT contract_id,
               commission + stamp_duty + handling_fee +
               regulatory_fee + transfer_fee + other_fee as total_fee
        FROM fund_records
        WHERE business_type IN ('证券买入','证券卖出')
    """, conn)
    trades = trades.merge(fees, on="contract_id", how="left").fillna({"total_fee": 0})

    results = {}
    for code, grp in trades.groupby("security_code"):
        name = grp["security_name"].iloc[0]
        qty = 0.0
        cost_total = 0.0   # 当前持仓总成本
        realized = 0.0
        buy_total = 0.0
        sell_total = 0.0

        for _, row in grp.iterrows():
            if row["direction"] == "买入":
                cost_total += row["trade_amount"] + row["total_fee"]
                qty += row["trade_qty"]
                buy_total += row["trade_amount"]
            else:
                if qty <= 0:
                    continue
                avg_cost = cost_total / qty
                sell_qty = min(row["trade_qty"], qty)
                sell_proceeds = row["trade_amount"] - row["total_fee"]
                realized += sell_proceeds - avg_cost * sell_qty
                cost_total -= avg_cost * sell_qty
                qty -= sell_qty
                sell_total += row["trade_amount"]

        results[code] = {
            "security_code": code,
            "security_name": name,
            "qty": qty,
            "cost_price": cost_total / qty if qty > 0 else 0.0,
            "cost_total": cost_total,
            "realized_pnl": realized,
            "buy_total": buy_total,
            "sell_total": sell_total,
        }

    return pd.DataFrame(results.values())


def cmd_position(_args):
    conn = sqlite3.connect(DB_PATH)
    pos = calc_positions(conn)
    held = pos[pos["qty"] > 0].copy()

    if held.empty:
        print("当前无持仓")
        conn.close()
        return

    # 取最新收盘价
    codes = held["security_code"].tolist()
    placeholders = ",".join("?" * len(codes))
    latest = pd.read_sql(f"""
        SELECT security_code, close as latest_price, trade_date
        FROM kline_daily
        WHERE (security_code, trade_date) IN (
            SELECT security_code, MAX(trade_date)
            FROM kline_daily WHERE security_code IN ({placeholders})
            GROUP BY security_code
        )
    """, conn, params=codes)
    conn.close()

    held = held.merge(latest, on="security_code", how="left")
    held["market_value"] = held["latest_price"] * held["qty"]
    held["float_pnl"]    = held["market_value"] - held["cost_total"]
    held["float_pct"]    = held["float_pnl"] / held["cost_total"] * 100
    total_market = held["market_value"].sum()
    held["weight"] = held["market_value"] / total_market * 100

    sep = "─" * 100
    print(f"\n{'═'*100}")
    print(f"  当前持仓明细（最新价截至 {held['trade_date'].max()}）")
    print(f"{'═'*100}")
    print(f"  {'标的':<22} {'持仓量':>12} {'成本均价':>9} {'持仓成本':>12} "
          f"{'最新价':>9} {'市值':>12} {'浮盈亏':>11} {'浮动%':>7} {'仓位%':>7}")
    print(sep)

    for _, r in held.sort_values("market_value", ascending=False).iterrows():
        pnl_str = f"{r['float_pnl']:>+11,.2f}"
        pct_str = f"{r['float_pct']:>+6.2f}%"
        print(f"  {r['security_name']+'('+r['security_code']+')' :<22} "
              f"{r['qty']:>12,.0f} "
              f"{r['cost_price']:>9.4f} "
              f"{r['cost_total']:>12,.2f} "
              f"{r['latest_price']:>9.4f} "
              f"{r['market_value']:>12,.2f} "
              f"{pnl_str} "
              f"{pct_str} "
              f"{r['weight']:>6.1f}%")

    print(sep)
    total_cost  = held["cost_total"].sum()
    total_float = held["float_pnl"].sum()
    print(f"  {'合计':<22} {'':>12} {'':>9} {total_cost:>12,.2f} "
          f"{'':>9} {total_market:>12,.2f} {total_float:>+11,.2f} "
          f"{total_float/total_cost*100:>+6.2f}% {'100.0%':>7}")
    print(f"{'═'*100}\n")


def cmd_pnl(_args):
    conn = sqlite3.connect(DB_PATH)
    pos = calc_positions(conn)

    # 已实现盈亏（已清仓标的）
    closed = pos[pos["qty"] == 0].copy()
    # 持仓浮动盈亏
    held   = pos[pos["qty"] >  0].copy()

    codes = held["security_code"].tolist()
    if codes:
        placeholders = ",".join("?" * len(codes))
        latest = pd.read_sql(f"""
            SELECT security_code, close as latest_price
            FROM kline_daily
            WHERE (security_code, trade_date) IN (
                SELECT security_code, MAX(trade_date)
                FROM kline_daily WHERE security_code IN ({placeholders})
                GROUP BY security_code
            )
        """, conn, params=codes)
        held = held.merge(latest, on="security_code", how="left")
        held["market_value"] = held["latest_price"] * held["qty"]
        held["float_pnl"]    = held["market_value"] - held["cost_total"]
    else:
        held["market_value"] = 0.0
        held["float_pnl"]    = 0.0

    sep = "─" * 72

    print(f"\n{'═'*72}")
    print(f"  盈亏分析报告")
    print(f"{'═'*72}")

    def print_realized_table(df):
        print(f"  {'标的':<22} {'买入总额':>12} {'卖出总额':>12} {'已实现盈亏':>12} {'收益率':>8}")
        print(sep)
        for _, r in df.sort_values("realized_pnl", ascending=False).iterrows():
            rate = r["realized_pnl"] / r["buy_total"] * 100 if r["buy_total"] > 0 else 0
            print(f"  {r['security_name']+'('+r['security_code']+')' :<22} "
                  f"{r['buy_total']:>12,.2f} "
                  f"{r['sell_total']:>12,.2f} "
                  f"{r['realized_pnl']:>+12,.2f} "
                  f"{rate:>+7.2f}%")
        print(sep)
        total_rate = df["realized_pnl"].sum() / df["buy_total"].sum() * 100 if df["buy_total"].sum() > 0 else 0
        print(f"  {'合计':<22} {df['buy_total'].sum():>12,.2f} "
              f"{df['sell_total'].sum():>12,.2f} "
              f"{df['realized_pnl'].sum():>+12,.2f} "
              f"{total_rate:>+7.2f}%")

    # 已清仓标的
    print(f"\n【一、已实现盈亏 — 已清仓标的】")
    print(sep)
    if closed.empty:
        print("  无已清仓标的")
    else:
        print_realized_table(closed)

    # 持仓标的中的已实现部分（做T、部分减仓等）
    held_with_realized = held[held["realized_pnl"] != 0].copy()
    print(f"\n【二、已实现盈亏 — 持仓标的（部分减仓/做T）】")
    print(sep)
    if held_with_realized.empty:
        print("  无")
    else:
        print_realized_table(held_with_realized)

    # 持仓浮盈
    print(f"\n【三、浮动盈亏（当前持仓）】")
    print(sep)
    if held.empty:
        print("  无持仓")
    else:
        print(f"  {'标的':<22} {'持仓成本':>12} {'当前市值':>12} {'浮动盈亏':>12} {'浮动%':>8}")
        print(sep)
        for _, r in held.sort_values("float_pnl", ascending=False).iterrows():
            rate = r["float_pnl"] / r["cost_total"] * 100 if r["cost_total"] > 0 else 0
            print(f"  {r['security_name']+'('+r['security_code']+')' :<22} "
                  f"{r['cost_total']:>12,.2f} "
                  f"{r['market_value']:>12,.2f} "
                  f"{r['float_pnl']:>+12,.2f} "
                  f"{rate:>+7.2f}%")
        print(sep)
        tc = held["cost_total"].sum()
        tm = held["market_value"].sum()
        print(f"  {'合计':<22} {tc:>12,.2f} {tm:>12,.2f} "
              f"{tm-tc:>+12,.2f} {(tm-tc)/tc*100:>+7.2f}%")

    # 四、总览
    total_realized = pos["realized_pnl"].sum()
    total_float    = (held["market_value"].sum() - held["cost_total"].sum()) if not held.empty else 0
    total_pnl      = total_realized + total_float

    print(f"\n【四、盈亏总览】")
    print(sep)
    print(f"  已实现盈亏（全部标的）     {total_realized:>+12,.2f} 元")
    print(f"  浮动盈亏（持仓市值）       {total_float:>+12,.2f} 元")
    print(f"  总盈亏                     {total_pnl:>+12,.2f} 元")
    print(f"{'═'*72}\n")

    conn.close()


def cmd_summary(_args):
    conn = sqlite3.connect(DB_PATH)
    pos = calc_positions(conn)
    held = pos[pos["qty"] > 0].copy()

    # 最新持仓市值
    total_market = 0.0
    if not held.empty:
        codes = held["security_code"].tolist()
        placeholders = ",".join("?" * len(codes))
        latest = pd.read_sql(f"""
            SELECT security_code, close as latest_price
            FROM kline_daily
            WHERE (security_code, trade_date) IN (
                SELECT security_code, MAX(trade_date)
                FROM kline_daily WHERE security_code IN ({placeholders})
                GROUP BY security_code
            )
        """, conn, params=codes)
        held = held.merge(latest, on="security_code", how="left")
        held["market_value"] = held["latest_price"] * held["qty"]
        total_market = held["market_value"].sum()

    # 资金流水：计算净入金
    cash_in  = conn.execute("SELECT COALESCE(SUM(amount),0) FROM fund_records WHERE business_type='银行转存'").fetchone()[0]
    cash_out = conn.execute("SELECT COALESCE(SUM(ABS(amount)),0) FROM fund_records WHERE business_type='银行转取'").fetchone()[0]
    net_deposit = cash_in - cash_out

    # 现金 + 现金等价物：直接读最新一行快照
    # balance       = 券商现金（不含任何产品持仓）
    # remaining_qty = 该行对应产品的持仓份额（天添利行上才有意义）
    # 数据为倒序导出，id 最小 = 最新
    latest_cash = conn.execute("""
        SELECT balance FROM fund_records
        WHERE (security_code IS NULL OR security_code NOT IN (
            SELECT DISTINCT security_code FROM fund_records
            WHERE business_type IN ('产品申购确认','产品赎回确认','产品红利发放')
              AND security_code IS NOT NULL
        ))
        ORDER BY id ASC LIMIT 1
    """).fetchone()
    cash_balance = latest_cash[0] if latest_cash else 0.0

    # 所有"现金等价物产品"：没有出现在 trade_records 的有代码产品
    # 取每个产品最新一行的 remaining_qty 作为当前持仓份额（单价1元）
    cash_products = conn.execute("""
        SELECT security_code, security_name,
               remaining_qty,
               SUM(CASE WHEN business_type='产品红利发放' THEN amount ELSE 0 END) as dividends
        FROM fund_records
        WHERE security_code IN (
            SELECT DISTINCT security_code FROM fund_records
            WHERE business_type IN ('产品申购确认','产品赎回确认','产品红利发放')
              AND security_code IS NOT NULL
              AND security_code NOT IN (SELECT DISTINCT security_code FROM trade_records)
        )
        GROUP BY security_code
        HAVING id = MIN(id)
    """).fetchall()
    # 重新按最新快照查
    cash_products = conn.execute("""
        SELECT f.security_code, f.security_name, f.remaining_qty,
               d.dividends
        FROM fund_records f
        JOIN (
            SELECT security_code, MIN(id) as min_id,
                   SUM(CASE WHEN business_type='产品红利发放' THEN amount ELSE 0 END) as dividends
            FROM fund_records
            WHERE security_code IN (
                SELECT DISTINCT security_code FROM fund_records
                WHERE business_type IN ('产品申购确认','产品赎回确认','产品红利发放')
                  AND security_code IS NOT NULL
                  AND security_code NOT IN (SELECT DISTINCT security_code FROM trade_records)
            )
            GROUP BY security_code
        ) d ON f.security_code = d.security_code AND f.id = d.min_id
    """).fetchall()

    cash_product_total    = sum(r[2] for r in cash_products)
    cash_product_dividend = sum(r[3] for r in cash_products)

    conn.close()

    total_realized = pos["realized_pnl"].sum() + cash_product_dividend
    total_cost     = held["cost_total"].sum() if not held.empty else 0
    total_float    = total_market - total_cost
    total_assets   = cash_balance + cash_product_total + total_market
    total_pnl      = total_realized + total_float

    sep = "─" * 50
    print(f"\n{'═'*50}")
    print(f"  账户总览")
    print(f"{'═'*50}")
    print(f"  净入金                {net_deposit:>14,.2f} 元")
    print(sep)
    print(f"  券商现金              {cash_balance:>14,.2f} 元")
    for r in cash_products:
        print(f"  {r[1]}({r[0]})     {r[2]:>14,.2f} 元（现金等价物）")
    print(f"  证券持仓市值          {total_market:>14,.2f} 元")
    print(f"  总资产                {total_assets:>14,.2f} 元")
    print(sep)
    print(f"  已实现盈亏            {total_realized:>+14,.2f} 元（含现金产品红利 {cash_product_dividend:,.2f} 元）")
    print(f"  浮动盈亏              {total_float:>+14,.2f} 元")
    print(f"  总盈亏                {total_pnl:>+14,.2f} 元")
    if net_deposit > 0:
        print(f"  总收益率（/净入金）   {total_pnl/net_deposit*100:>+13.2f}%")
    print(f"{'═'*50}\n")


def cmd_friction(_args):
    conn = sqlite3.connect(DB_PATH)

    # ── 1. 原始数据 ──────────────────────────────────────────────
    trades = pd.read_sql("""
        SELECT t.security_code, t.security_name, t.trade_date, t.trade_time,
               t.direction, t.trade_price, t.trade_qty, t.trade_amount, t.contract_id
        FROM trade_records t
        WHERE t.direction IN ('买入','卖出')
        ORDER BY t.security_code, t.trade_date, t.trade_time
    """, conn)
    trades["trade_qty"] = trades["trade_qty"].abs()
    trades["trade_date_fmt"] = trades["trade_date"].astype(str).str[:8]

    fees = pd.read_sql("""
        SELECT security_code, business_type, contract_id,
               ABS(amount) as amount,
               commission, stamp_duty, handling_fee,
               regulatory_fee, transfer_fee, other_fee
        FROM fund_records
        WHERE business_type IN ('证券买入','证券卖出')
          AND security_code IS NOT NULL
    """, conn)
    fees["total_fee"] = (
        fees["commission"] + fees["stamp_duty"] + fees["handling_fee"] +
        fees["regulatory_fee"] + fees["transfer_fee"] + fees["other_fee"]
    )
    # 关联费用到交易记录
    trades = trades.merge(
        fees[["contract_id", "total_fee", "commission", "stamp_duty",
              "handling_fee", "regulatory_fee", "transfer_fee"]],
        on="contract_id", how="left"
    ).fillna(0)

    conn.close()

    # ── 2. 按标的汇总费用 ─────────────────────────────────────────
    fee_cols = ["commission", "stamp_duty", "handling_fee", "regulatory_fee", "transfer_fee"]
    by_code = (
        trades.groupby(["security_code", "security_name"])[["trade_amount", "total_fee"] + fee_cols]
        .sum()
        .reset_index()
    )
    by_code["fee_rate_bps"] = by_code["total_fee"] / by_code["trade_amount"] * 10000

    # ── 3. 做T磨损 ───────────────────────────────────────────────
    # 同日同标的既有买又有卖，取 min(buy_qty, sell_qty) 作为做T数量
    day_grp = trades.groupby(["security_code", "security_name", "trade_date_fmt", "direction"])
    day_sum = day_grp.agg(
        qty=("trade_qty", "sum"),
        amount=("trade_amount", "sum"),
        fee=("total_fee", "sum"),
    ).reset_index()

    buy_day  = day_sum[day_sum["direction"] == "买入"].rename(
        columns={"qty": "buy_qty", "amount": "buy_amount", "fee": "buy_fee"})
    sell_day = day_sum[day_sum["direction"] == "卖出"].rename(
        columns={"qty": "sell_qty", "amount": "sell_amount", "fee": "sell_fee"})

    t_days = buy_day.merge(
        sell_day, on=["security_code", "security_name", "trade_date_fmt"]
    )
    t_days["t_qty"]     = t_days[["buy_qty", "sell_qty"]].min(axis=1)
    t_days["buy_price"]  = t_days["buy_amount"]  / t_days["buy_qty"]
    t_days["sell_price"] = t_days["sell_amount"] / t_days["sell_qty"]
    t_days["spread"]     = t_days["sell_price"] - t_days["buy_price"]
    # 做T磨损 = 价差 × T数量（正为盈，负为亏）+ 该日双边费用按比例
    t_days["t_fee_buy"]  = t_days["buy_fee"]  * (t_days["t_qty"] / t_days["buy_qty"])
    t_days["t_fee_sell"] = t_days["sell_fee"] * (t_days["t_qty"] / t_days["sell_qty"])
    t_days["t_pnl"]      = t_days["spread"] * t_days["t_qty"]
    t_days["t_fee"]      = t_days["t_fee_buy"] + t_days["t_fee_sell"]
    t_days["t_net"]      = t_days["t_pnl"] - t_days["t_fee"]

    t_summary = t_days.groupby(["security_code", "security_name"]).agg(
        t_count=("trade_date_fmt", "count"),
        t_qty=("t_qty", "sum"),
        t_pnl=("t_pnl", "sum"),
        t_fee=("t_fee", "sum"),
        t_net=("t_net", "sum"),
    ).reset_index()

    # ── 4. 输出 ───────────────────────────────────────────────────
    sep = "─" * 80

    print(f"\n{'═'*80}")
    print(f"  交易磨损分析")
    print(f"{'═'*80}")

    # 4-1 总费用汇总
    grand_amount = by_code["trade_amount"].sum()
    grand_fee    = by_code["total_fee"].sum()
    print(f"\n【一、交易费用汇总】")
    print(f"{sep}")
    print(f"  {'标的':<20} {'成交额':>14} {'佣金':>8} {'印花税':>7} {'经手费':>7} {'监管费':>6} {'过户费':>6} {'合计':>8} {'费率(bps)':>9}")
    print(f"{sep}")
    for _, r in by_code.sort_values("trade_amount", ascending=False).iterrows():
        print(f"  {r['security_name']+'('+r['security_code']+')' :<20} "
              f"{r['trade_amount']:>14,.2f} "
              f"{r['commission']:>8,.2f} "
              f"{r['stamp_duty']:>7,.2f} "
              f"{r['handling_fee']:>7,.2f} "
              f"{r['regulatory_fee']:>6,.2f} "
              f"{r['transfer_fee']:>6,.2f} "
              f"{r['total_fee']:>8,.2f} "
              f"{r['fee_rate_bps']:>8.2f}")
    print(f"{sep}")
    print(f"  {'合计':<20} {grand_amount:>14,.2f} "
          f"{'':>8} {'':>7} {'':>7} {'':>6} {'':>6} "
          f"{grand_fee:>8,.2f} "
          f"{grand_fee/grand_amount*10000:>8.2f}")

    # 4-2 买卖方向拆分
    print(f"\n【二、买入 vs 卖出 费用拆分】")
    print(f"{sep}")
    dir_grp = (
        trades.groupby(["security_code", "security_name", "direction"])
        .agg(trades_n=("trade_qty","count"), amount=("trade_amount","sum"), fee=("total_fee","sum"))
        .reset_index()
    )
    print(f"  {'标的':<20} {'方向':<4} {'笔数':>5} {'成交额':>14} {'费用':>8} {'费率(bps)':>9}")
    print(f"{sep}")
    for _, r in dir_grp.sort_values(["security_code","direction"]).iterrows():
        print(f"  {r['security_name']+'('+r['security_code']+')' :<20} "
              f"{r['direction']:<4} {r['trades_n']:>5} "
              f"{r['amount']:>14,.2f} {r['fee']:>8,.2f} "
              f"{r['fee']/r['amount']*10000:>8.2f}")

    # 4-3 做T磨损
    print(f"\n【三、做T磨损明细】")
    print(f"{sep}")
    if t_days.empty:
        print("  无做T记录")
    else:
        print(f"  {'标的':<20} {'日期':<12} {'T数量':>10} {'买均价':>8} {'卖均价':>8} {'价差':>8} {'价差盈亏':>10} {'双边费用':>9} {'净盈亏':>10}")
        print(f"{sep}")
        for _, r in t_days.sort_values(["security_code","trade_date_fmt"]).iterrows():
            print(f"  {r['security_name']+'('+r['security_code']+')' :<20} "
                  f"{r['trade_date_fmt']:<12} "
                  f"{r['t_qty']:>10,.0f} "
                  f"{r['buy_price']:>8.4f} "
                  f"{r['sell_price']:>8.4f} "
                  f"{r['spread']:>+8.4f} "
                  f"{r['t_pnl']:>+10.2f} "
                  f"{r['t_fee']:>9.2f} "
                  f"{r['t_net']:>+10.2f}")
        print(f"{sep}")
        t_tot = t_days[["t_pnl","t_fee","t_net"]].sum()
        print(f"  {'做T合计':<34} "
              f"{'':>10} {'':>8} {'':>8} {'':>8} "
              f"{t_tot['t_pnl']:>+10.2f} "
              f"{t_tot['t_fee']:>9.2f} "
              f"{t_tot['t_net']:>+10.2f}")

        print(f"\n  按标的汇总：")
        print(f"  {'标的':<20} {'做T次数':>7} {'T总量':>12} {'价差盈亏':>10} {'双边费用':>9} {'净盈亏':>10}")
        for _, r in t_summary.iterrows():
            print(f"  {r['security_name']+'('+r['security_code']+')' :<20} "
                  f"{r['t_count']:>7} {r['t_qty']:>12,.0f} "
                  f"{r['t_pnl']:>+10.2f} {r['t_fee']:>9.2f} {r['t_net']:>+10.2f}")

    # 4-4 总磨损
    t_total_fee  = t_summary["t_fee"].sum()  if not t_summary.empty else 0
    t_loss_rows = t_days[t_days["t_net"] < 0]["t_net"].sum() if not t_days.empty else 0
    t_total_loss = abs(t_loss_rows)
    print(f"\n【四、磨损总览】")
    print(f"{sep}")
    print(f"  总成交额                  {grand_amount:>14,.2f} 元")
    print(f"  交易费用合计              {grand_fee:>14,.2f} 元  ({grand_fee/grand_amount*10000:.2f} bps)")
    print(f"    其中 佣金               {by_code['commission'].sum():>14,.2f} 元")
    print(f"    其中 印花税             {by_code['stamp_duty'].sum():>14,.2f} 元")
    print(f"    其中 经手费             {by_code['handling_fee'].sum():>14,.2f} 元")
    print(f"    其中 监管费+过户费      {(by_code['regulatory_fee']+by_code['transfer_fee']).sum():>14,.2f} 元")
    print(f"  做T双边费用               {t_total_fee:>14,.2f} 元  (含于上方费用中)")
    print(f"  做T净亏损（亏损场次）     {t_total_loss:>14,.2f} 元")
    print(f"  总磨损（费用+做T亏损）    {grand_fee + t_total_loss:>14,.2f} 元")
    print(f"{'═'*80}\n")


def cmd_import(args):
    if not args.money and not args.stock and not args.kline:
        print("错误：至少指定 --money、--stock 或 --kline 之一", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if args.money:
        path = Path(args.money)
        if not path.exists():
            print(f"错误：文件不存在 {path}", file=sys.stderr)
            sys.exit(1)
        ins, skip = import_money(conn, path)
        print(f"[fund_records]  导入 {ins} 条，跳过 {skip} 条（重复或无流水号）")

    if args.stock:
        path = Path(args.stock)
        if not path.exists():
            print(f"错误：文件不存在 {path}", file=sys.stderr)
            sys.exit(1)
        ins, skip = import_stock(conn, path)
        print(f"[trade_records] 导入 {ins} 条，跳过 {skip} 条（重复或无成交编号）")

    if args.kline:
        path = Path(args.kline)
        if not path.exists():
            print(f"错误：文件不存在 {path}", file=sys.stderr)
            sys.exit(1)
        try:
            ins, skip, resolved_code = import_kline(conn, path, args.code or None)
            print(f"[kline_daily]   导入 {ins} 条，跳过 {skip} 条（重复）  [{resolved_code}]")
        except ValueError as e:
            print(f"错误：{e}", file=sys.stderr)
            sys.exit(1)

    conn.close()
    print(f"数据库：{DB_PATH.resolve()}")


def main():
    parser = argparse.ArgumentParser(prog="astock", description="A股交易数据分析工具")
    sub = parser.add_subparsers(dest="command")

    p_import = sub.add_parser("import", help="导入交易数据")
    p_import.add_argument("--money", metavar="FILE", help="资金流水 TSV 文件")
    p_import.add_argument("--stock", metavar="FILE", help="成交记录 TSV 文件")
    p_import.add_argument("--kline", metavar="FILE", help="K线 CSV 文件（各数据源兜底方案）")
    p_import.add_argument("--code",  metavar="CODE", help="--kline 对应的证券代码（如 518880）；CSV 含 ts_code 列时可省略")

    p_fetch = sub.add_parser("fetch", help="抓取标的历史日K线并存入数据库")
    p_fetch.add_argument("--codes", nargs="+", metavar="CODE", help="指定标的代码（默认自动从交易记录提取）")
    p_fetch.add_argument("--start", metavar="YYYY-MM-DD", help="开始日期（默认：交易记录最早日期）")
    p_fetch.add_argument("--end", metavar="YYYY-MM-DD", help="结束日期（默认：昨天）")

    sub.add_parser("summary",  help="账户总览（资金、市值、总盈亏）")
    sub.add_parser("position", help="当前持仓明细")
    sub.add_parser("pnl",      help="盈亏分析（已实现+浮动）")
    sub.add_parser("friction", help="交易磨损分析（费用+做T损耗）")

    p_chart = sub.add_parser("chart", help="绘制标的日K线图并标注交易操作")
    p_chart.add_argument("code", help="标的代码，如 518880")
    p_chart.add_argument("--start", metavar="YYYY-MM-DD", help="开始日期")
    p_chart.add_argument("--end", metavar="YYYY-MM-DD", help="结束日期")
    p_chart.add_argument("--output", "-o", metavar="FILE", help="输出文件路径（默认：<code>_kline.png）")
    p_chart.add_argument("--show", action="store_true", help="同时弹窗显示图表")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.command == "import":
        cmd_import(args)
    elif args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "chart":
        cmd_chart(args)
    elif args.command == "summary":
        cmd_summary(args)
    elif args.command == "position":
        cmd_position(args)
    elif args.command == "pnl":
        cmd_pnl(args)
    elif args.command == "friction":
        cmd_friction(args)


if __name__ == "__main__":
    main()
