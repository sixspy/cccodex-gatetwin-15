from app.db import 连接
from app.seed import 此刻


def 跑贯验() -> dict:
    """行程账与刷卡点互证：每笔已成对行程对应两笔已成对刷卡；旁路/开腿命运自洽。

    回正链路口径（显式回正写闸）：
    - 待回正旁路对应的刷卡点命运必须仍是已旁路（禁止无写闸改命运）；
    - 已回正旁路与回正审计一一对应，审计编号互指；
    - 审计=成对必有行程账落账；审计=重新开腿其开腿不得仍处已旁路；
    - 行程键唯一，杜绝双行程。
    """
    conn = 连接()
    try:
        问题 = []
        刷卡数 = conn.execute("SELECT COUNT(*) FROM 刷卡点").fetchone()[0]
        行程 = conn.execute("SELECT * FROM 行程账 WHERE 状态='已成对'").fetchall()
        开腿数 = conn.execute("SELECT COUNT(*) FROM 开腿账 WHERE 状态='在途'").fetchone()[0]
        旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

        for t in 行程:
            进 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["进站事件编号"],)
            ).fetchone()
            出 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["出站事件编号"],)
            ).fetchone()
            if not 进 or not 出:
                问题.append(f"行程{t['行程键']}缺刷卡点")
                continue
            if 进["命运"] != "已成对" or 出["命运"] != "已成对":
                问题.append(f"行程{t['行程键']}刷卡命运非已成对")
            if 进["行程键"] != t["行程键"] or 出["行程键"] != t["行程键"]:
                问题.append(f"行程{t['行程键']}刷卡行程键不一致")
            if 进["卡号"] != t["卡号"] or 出["卡号"] != t["卡号"]:
                问题.append(f"行程{t['行程键']}卡号不一致")
            if 进["方向"] != "进站" or 出["方向"] != "出站":
                问题.append(f"行程{t['行程键']}方向不配对")

        成对刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已成对'"
        ).fetchone()[0]
        if 成对刷 != len(行程) * 2:
            问题.append(f"已成对刷卡{成对刷} ≠ 行程{len(行程)}×2")

        开腿刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已开腿'"
        ).fetchone()[0]
        if 开腿刷 != 开腿数:
            问题.append(f"已开腿刷卡{开腿刷} ≠ 在途开腿{开腿数}")

        # 回正链路互证
        待回正 = conn.execute(
            "SELECT * FROM 旁路匣 WHERE 状态='待回正'"
        ).fetchall()
        for b in 待回正:
            if not b["事件编号"]:
                continue
            刷 = conn.execute(
                "SELECT 命运 FROM 刷卡点 WHERE 事件编号=?", (b["事件编号"],)
            ).fetchone()
            if 刷 and 刷["命运"] != "已旁路":
                问题.append(
                    f"旁路{b['编号']}待回正但刷卡{b['事件编号']}命运={刷['命运']}（无写闸改命运）"
                )

        已回正 = conn.execute(
            "SELECT * FROM 旁路匣 WHERE 状态='已回正'"
        ).fetchall()
        for b in 已回正:
            审 = conn.execute(
                "SELECT * FROM 回正审计 WHERE 旁路编号=?", (b["编号"],)
            ).fetchone()
            if not 审:
                问题.append(f"旁路{b['编号']}已回正但无审计")
                continue
            if b["回正审计编号"] != 审["审计编号"]:
                问题.append(f"旁路{b['编号']}与审计编号互指不一致")
            if 审["结果"] == "成对":
                行 = conn.execute(
                    "SELECT 1 FROM 行程账 WHERE 行程键=?", (审["行程键"],)
                ).fetchone()
                if not 行:
                    问题.append(f"审计{审['审计编号']}声称成对但行程账无{审['行程键']}")
            elif 审["结果"] == "重新开腿":
                腿 = conn.execute(
                    "SELECT 状态 FROM 开腿账 WHERE 开腿键=?", (审["开腿键"],)
                ).fetchone()
                if not 腿:
                    问题.append(f"审计{审['审计编号']}声称开腿但开腿{审['开腿键']}不存在")
                elif 腿["状态"] == "已旁路":
                    # 复活后又被缺腿超时再次旁路是合法的，但必须有晚于审计的新旁路行解释
                    后续 = conn.execute(
                        "SELECT 1 FROM 旁路匣 WHERE 事件编号=? AND 时刻>? LIMIT 1",
                        (审["事件编号"], 审["时刻"]),
                    ).fetchone()
                    if not 后续:
                        问题.append(
                            f"审计{审['审计编号']}声称开腿但开腿{审['开腿键']}已旁路且无后续旁路行"
                        )

        审计数 = conn.execute("SELECT COUNT(*) FROM 回正审计").fetchone()[0]
        if 审计数 != len(已回正):
            问题.append(f"回正审计{审计数} ≠ 已回正旁路{len(已回正)}（一一对应破裂）")
        双审计 = conn.execute(
            "SELECT 旁路编号, COUNT(*) c FROM 回正审计 GROUP BY 旁路编号 HAVING c > 1"
        ).fetchall()
        if 双审计:
            问题.append("存在重复回正审计：" + ",".join(str(r["旁路编号"]) for r in 双审计))

        通过 = 1 if not 问题 else 0
        说明 = "行程账与刷卡点互证通过" if 通过 else "；".join(问题)[:800]
        conn.execute(
            """INSERT INTO 行程贯验(时刻,刷卡数,行程数,开腿数,旁路数,是否通过,说明)
               VALUES (?,?,?,?,?,?,?)""",
            (此刻(), 刷卡数, len(行程), 开腿数, 旁路数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "刷卡数": 刷卡数,
            "行程数": len(行程),
            "开腿数": 开腿数,
            "旁路数": 旁路数,
            "回正审计数": 审计数,
            "说明": 说明,
            "问题": 问题,
        }
    finally:
        conn.close()
