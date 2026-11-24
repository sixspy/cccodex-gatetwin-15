import os
import tempfile

import pytest

# 在导入 app 之前指向临时库，每个测试会话独立
_临时 = tempfile.mkdtemp(prefix="gatetwin-test-")
os.environ["数据目录"] = _临时
os.environ["夹具目录"] = "/workspace/fixtures"

from app.db import 连接  # noqa: E402
from app.seed import 初始化库  # noqa: E402
from app.services import 装载, 贯验, 回正  # noqa: E402
from app.services.回正 import 回正拒绝  # noqa: E402

初始化库()


def _装(批次, 事件):
    return 装载.装一批({"批次编号": 批次, "事件": 事件})


def _旁路行(原因=None, 事件编号=None):
    conn = 连接()
    try:
        sql = "SELECT * FROM 旁路匣 WHERE 状态='待回正'"
        参数 = []
        if 原因:
            sql += " AND 原因=?"
            参数.append(原因)
        if 事件编号:
            sql += " AND 事件编号=?"
            参数.append(事件编号)
        sql += " ORDER BY 编号 DESC LIMIT 1"
        return dict(conn.execute(sql, 参数).fetchone())
    finally:
        conn.close()


def _计数(sql):
    conn = 连接()
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def _刷卡(事件编号):
    conn = 连接()
    try:
        return dict(conn.execute(
            "SELECT * FROM 刷卡点 WHERE 事件编号=?", (事件编号,)
        ).fetchone())
    finally:
        conn.close()


# ---- 夹具一·甲：出站孤儿、同卡无在途开腿 → 整票拒绝、零行程、旁路保持 ----

def test_甲_孤儿无开腿回正拒绝且无行程():
    _装("批-甲", [
        {"事件编号": "甲-o", "卡号": "卡甲", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-22T10:00:00Z", "处理时": "2026-11-22T10:00:01Z"},
    ])
    b = _旁路行("出站孤儿", "甲-o")
    预览 = 回正.只读预览(b["编号"])
    assert 预览["valid"] is True
    assert 预览["是否允许回正"] is False
    assert 预览["审计编号"] is None
    assert 预览["重放结果"] is None

    行程前 = _计数("SELECT COUNT(*) FROM 行程账")
    with pytest.raises(回正拒绝):
        回正.回正写闸(b["编号"])
    assert _计数("SELECT COUNT(*) FROM 行程账") == 行程前
    assert _计数("SELECT COUNT(*) FROM 回正审计") == 0
    仍 = _旁路行("出站孤儿", "甲-o")
    assert 仍["状态"] == "待回正"
    assert _刷卡("甲-o")["命运"] == "已旁路"


# ---- 夹具一·乙：同卡后补在途开腿 → 回正成对、旁路关闭、审计留痕 ----

def test_乙_孤儿有开腿回正成对且旁路关闭():
    _装("批-乙-孤儿", [
        {"事件编号": "乙-o", "卡号": "卡乙", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-22T09:00:00Z", "处理时": "2026-11-22T09:00:01Z"},
    ])
    _装("批-乙-进站", [
        {"事件编号": "乙-i", "卡号": "卡乙", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-22T10:00:00Z", "处理时": "2026-11-22T10:00:01Z"},
    ])
    b = _旁路行("出站孤儿", "乙-o")
    预览 = 回正.只读预览(b["编号"])
    assert 预览["是否允许回正"] is True
    assert 预览["重放结果"]["模式"] == "成对"
    assert 预览["重放结果"]["行程键"] == "行-乙-i-乙-o"

    行程前 = _计数("SELECT COUNT(*) FROM 行程账")
    r = 回正.回正写闸(b["编号"])
    assert r["是否允许回正"] is True
    assert r["幂等"] is False
    assert r["重放结果"]["行程键"] == "行-乙-i-乙-o"
    assert isinstance(r["审计编号"], int)
    assert _计数("SELECT COUNT(*) FROM 行程账") == 行程前 + 1

    conn = 连接()
    try:
        行 = dict(conn.execute("SELECT * FROM 旁路匣 WHERE 编号=?", (b["编号"],)).fetchone())
        assert 行["状态"] == "已回正"
        assert 行["回正审计编号"] == r["审计编号"]
        审 = dict(conn.execute(
            "SELECT * FROM 回正审计 WHERE 审计编号=?", (r["审计编号"],)
        ).fetchone())
        assert 审["旁路编号"] == b["编号"] and 审["结果"] == "成对"
        腿 = dict(conn.execute(
            "SELECT * FROM 开腿账 WHERE 开腿键='腿-乙-i'"
        ).fetchone())
        assert 腿["状态"] == "已成对"
    finally:
        conn.close()
    assert _刷卡("乙-i")["命运"] == "已成对"
    assert _刷卡("乙-o")["命运"] == "已成对"
    assert _刷卡("乙-o")["行程键"] == "行-乙-i-乙-o"
    assert 贯验.跑贯验()["是否通过"] is True


# ---- 夹具二：重复回正幂等，不得双行程 ----

def test_重复回正不得双行程():
    # 自包含造一个可回正孤儿
    _装("批-幂-孤", [
        {"事件编号": "幂-o", "卡号": "卡幂", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-22T09:00:00Z", "处理时": "2026-11-22T09:00:01Z"},
    ])
    _装("批-幂-腿", [
        {"事件编号": "幂-i", "卡号": "卡幂", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-22T10:00:00Z", "处理时": "2026-11-22T10:00:01Z"},
    ])
    conn = 连接()
    try:
        编号 = conn.execute(
            "SELECT 编号 FROM 旁路匣 WHERE 事件编号='幂-o'"
        ).fetchone()["编号"]
    finally:
        conn.close()
    r1 = 回正.回正写闸(编号)
    审计 = r1["审计编号"]
    行程前 = _计数("SELECT COUNT(*) FROM 行程账")
    r2 = 回正.回正写闸(编号)
    r3 = 回正.回正写闸(编号)
    assert r2["幂等"] is True and r3["幂等"] is True
    assert r2["审计编号"] == r3["审计编号"] == 审计
    assert _计数("SELECT COUNT(*) FROM 行程账") == 行程前
    conn = 连接()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM 回正审计 WHERE 旁路编号=?", (编号,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM 行程账 WHERE 行程键='行-幂-i-幂-o'"
        ).fetchone()[0] == 1
    finally:
        conn.close()


# ---- 夹具三·缺腿超时回正：重新开腿，无新行程 ----

def test_缺腿超时回正重新开腿():
    _装("批-缺腿回正", [
        {"事件编号": "丙-t1", "卡号": "卡丙", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-22T06:00:00Z", "处理时": "2026-11-22T06:00:01Z"},
        {"事件编号": "丙-水", "卡号": "卡丙水", "站点键": "站B", "方向": "进站",
         "事件时": "2026-11-22T09:30:00Z", "处理时": "2026-11-22T09:30:01Z"},
    ])
    b = _旁路行("缺腿超时", "丙-t1")
    预览 = 回正.只读预览(b["编号"])
    assert 预览["是否允许回正"] is True
    assert 预览["重放结果"]["模式"] == "开腿"
    行程前 = _计数("SELECT COUNT(*) FROM 行程账")
    r = 回正.回正写闸(b["编号"])
    assert r["重放结果"]["结果"] == "重新开腿"
    assert r["重放结果"]["开腿键"] == "腿-丙-t1"
    assert _计数("SELECT COUNT(*) FROM 行程账") == 行程前
    conn = 连接()
    try:
        assert dict(conn.execute(
            "SELECT 状态 FROM 开腿账 WHERE 开腿键='腿-丙-t1'"
        ).fetchone())["状态"] == "在途"
    finally:
        conn.close()
    assert _刷卡("丙-t1")["命运"] == "已开腿"
    # 复活后后续出站可正常成对
    _装("批-丙出站", [
        {"事件编号": "丙-o", "卡号": "卡丙", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-22T10:00:00Z", "处理时": "2026-11-22T10:00:01Z"},
    ])
    assert _刷卡("丙-t1")["命运"] == "已成对"
    assert 贯验.跑贯验()["是否通过"] is True


# ---- 重复进站：在途腿尚在时拒绝（防双开腿）；腾空后可回正 ----

def test_重复进站回正防双开腿():
    _装("批-重复", [
        {"事件编号": "丁-r1", "卡号": "卡丁", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-22T11:00:00Z", "处理时": "2026-11-22T11:00:01Z"},
        {"事件编号": "丁-r2", "卡号": "卡丁", "站点键": "站B", "方向": "进站",
         "事件时": "2026-11-22T11:20:00Z", "处理时": "2026-11-22T11:20:01Z"},
    ])
    b = _旁路行("重复进站", "丁-r1")
    # r2 仍在途 → 回正会双开腿，拒绝
    assert 回正.只读预览(b["编号"])["是否允许回正"] is False
    with pytest.raises(回正拒绝):
        回正.回正写闸(b["编号"])
    # r2 成对腾空后 → 可回正复活 r1
    _装("批-丁出", [
        {"事件编号": "丁-r3", "卡号": "卡丁", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-22T11:45:00Z", "处理时": "2026-11-22T11:45:01Z"},
    ])
    assert 回正.只读预览(b["编号"])["是否允许回正"] is True
    r = 回正.回正写闸(b["编号"])
    assert r["重放结果"]["开腿键"] == "腿-丁-r1"
    # 复活腿在超时窗口内自行成对收尾，避免被后续批次水位再次超时旁路
    _装("批-丁收尾", [
        {"事件编号": "丁-r4", "卡号": "卡丁", "站点键": "站B", "方向": "出站",
         "事件时": "2026-11-22T11:50:00Z", "处理时": "2026-11-22T11:50:01Z"},
    ])
    assert _刷卡("丁-r1")["命运"] == "已成对"
    assert 贯验.跑贯验()["是否通过"] is True


# ---- 终态缺陷旁路（未知站点）不可回正 ----

def test_未知站点终态不可回正():
    _装("批-未知", [
        {"事件编号": "戊-x", "卡号": "卡戊", "站点键": "站Z", "方向": "进站",
         "事件时": "2026-11-22T12:00:00Z", "处理时": "2026-11-22T12:00:01Z"},
    ])
    b = _旁路行("未知站点", "戊-x")
    预览 = 回正.只读预览(b["编号"])
    assert 预览["valid"] is True and 预览["是否允许回正"] is False
    with pytest.raises(回正拒绝):
        回正.回正写闸(b["编号"])
    assert _刷卡("戊-x")["命运"] == "已旁路"


def test_不存在旁路编号valid为假():
    assert 回正.只读预览(999999)["valid"] is False
    with pytest.raises(回正拒绝):
        回正.回正写闸(999999)


# ---- 贯验能检出「无写闸改命运」 ----

def test_贯验检出无写闸改命运():
    b = _旁路行("出站孤儿", "甲-o")
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE 刷卡点 SET 命运='已成对' WHERE 事件编号='甲-o'"
        )
        conn.commit()
    finally:
        conn.close()
    r = 贯验.跑贯验()
    assert r["是否通过"] is False
    assert any("无写闸改命运" in s for s in r["问题"])
    # 复原，避免污染后续并发测试的贯验
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE 刷卡点 SET 命运='已旁路', 行程键='' WHERE 事件编号='甲-o'")
        conn.commit()
    finally:
        conn.close()


# ---- 夹具四：回正与装载并发，不得半截开腿/双行程 ----

def test_并发回正与装载无半截(tmp_path):
    import threading

    # 造 12 个出站孤儿（先孤儿后补腿），分两组建好可回正条件
    for i in range(12):
        _装(f"批-并-孤-{i}", [
            {"事件编号": f"并-o-{i}", "卡号": f"卡并{i}", "站点键": "站C",
             "方向": "出站", "事件时": "2026-11-23T08:00:00Z",
             "处理时": "2026-11-23T08:00:01Z"},
        ])
        _装(f"批-并-腿-{i}", [
            {"事件编号": f"并-i-{i}", "卡号": f"卡并{i}", "站点键": "站A",
             "方向": "进站", "事件时": "2026-11-23T09:00:00Z",
             "处理时": "2026-11-23T09:00:01Z"},
        ])
    conn = 连接()
    try:
        编号表 = [
            r["编号"] for r in conn.execute(
                "SELECT 编号 FROM 旁路匣 WHERE 原因='出站孤儿' AND 事件编号 LIKE '并-o-%'"
            )
        ]
    finally:
        conn.close()
    assert len(编号表) == 12

    屏障 = threading.Barrier(24)
    错误 = []

    def 回正线程(编号):
        try:
            屏障.wait()
            回正.回正写闸(编号)
            回正.回正写闸(编号)  # 同票重复，压幂等
        except Exception as e:  # noqa: BLE001
            错误.append(f"回正{编号}:{e}")

    def 装载线程(k):
        try:
            屏障.wait()
            _装(f"批-并发载-{k}", [
                {"事件编号": f"并发-i-{k}", "卡号": f"卡载{k}", "站点键": "站A",
                 "方向": "进站", "事件时": f"2026-11-23T10:{k:02d}:00Z",
                 "处理时": f"2026-11-23T10:{k:02d}:01Z"},
                {"事件编号": f"并发-o-{k}", "卡号": f"卡载{k}", "站点键": "站B",
                 "方向": "出站", "事件时": f"2026-11-23T10:{k:02d}:30Z",
                 "处理时": f"2026-11-23T10:{k:02d}:31Z"},
            ])
        except Exception as e:  # noqa: BLE001
            错误.append(f"装载{k}:{e}")

    线程s = [threading.Thread(target=回正线程, args=(n,)) for n in 编号表]
    线程s += [threading.Thread(target=装载线程, args=(k,)) for k in range(12)]
    for t in 线程s:
        t.start()
    for t in 线程s:
        t.join()

    assert not 错误, 错误
    # 每个旁路至多一条审计；12 个孤儿全部成对回正
    conn = 连接()
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM (SELECT 旁路编号 FROM 回正审计 GROUP BY 旁路编号 HAVING COUNT(*)>1)"
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM 旁路匣 WHERE 原因='出站孤儿' AND 事件编号 LIKE '并-o-%' AND 状态='已回正'"
        ).fetchone()[0] == 12
        # 无半截：在途开腿数 == 已开腿刷卡数（贯验内同一不变量）
        assert conn.execute(
            "SELECT COUNT(*) FROM 开腿账 WHERE 状态='在途'"
        ).fetchone()[0] == conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已开腿'"
        ).fetchone()[0]
    finally:
        conn.close()
    r = 贯验.跑贯验()
    assert r["是否通过"] is True, r["问题"]
