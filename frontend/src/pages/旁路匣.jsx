import React, { useEffect, useState } from "react";
import { 取, 递 } from "../api.js";

export default function 旁路匣() {
  const [行, 设] = useState([]);
  const [预览表, 设预览表] = useState({});
  const [审计, 设审计] = useState([]);
  const [讯, 设讯] = useState("");
  const 刷 = async () => {
    const 旁路 = await 取("/旁路匣");
    设(旁路);
    const 预 = await Promise.all(旁路.map((r) => 取(`/replay/preview/${r.编号}`)));
    设预览表(Object.fromEntries(预.map((p) => [p.旁路编号, p])));
    设审计(await 取("/replay"));
  };
  useEffect(() => { 刷(); }, []);

  const 回正 = async (编号) => {
    设讯(`写闸中：旁路${编号}…`);
    try {
      const r = await 递(`/replay/${编号}`);
      设讯(
        r.幂等
          ? `旁路${编号}重复回正已吞掉（幂等，审计${r.审计编号}），无新行程`
          : `旁路${编号}回正${r.重放结果.结果}，审计${r.审计编号}，行程键=${r.重放结果.行程键 || "—"}`
      );
      await 刷();
    } catch (e) {
      设讯(`旁路${编号}回正被写闸拒绝：${e.message || e}`);
    }
  };

  return (
    <div>
      <h1 className="题">旁路匣</h1>
      <p className="述">
        缺腿超时、出站孤儿、重复进站、未知站等旁路原因。架构口径：<b>显式回正写闸</b>——
        旁路行保持「待回正」，禁止无入口改命运；仅写闸可关旁路并同票重放成对/开腿、留审计，重复回正幂等不双行程。
      </p>
      <div className="行"><button className="次" onClick={刷}>刷新</button></div>
      {讯 && <p className="讯">{讯}</p>}
      {!行.length ? <div className="空态">旁路匣空。</div> : (
        <table>
          <thead>
            <tr><th>#</th><th>原因</th><th>卡号</th><th>事件</th><th>状态</th><th>时刻</th><th>回正只读预览 / 写闸</th><th>载荷</th></tr>
          </thead>
          <tbody>
            {行.map((r) => {
              const p = 预览表[r.编号];
              return (
                <tr key={r.编号}>
                  <td>{r.编号}</td>
                  <td>{r.原因}</td>
                  <td>{r.卡号}</td>
                  <td>{r.事件编号}</td>
                  <td>
                    <span className={`徽章 ${r.状态 === "已回正" ? "通" : "败"}`}>{r.状态}</span>
                    {r.回正审计编号 ? <span className="讯"> 审计{r.回正审计编号}</span> : null}
                  </td>
                  <td>{r.时刻}</td>
                  <td style={{ minWidth: 260 }}>
                    {p ? (
                      <>
                        <div className="讯" style={{ margin: 0 }}>
                          valid={String(p.valid)} · 允许回正={String(p.是否允许回正)}
                        </div>
                        <div className="讯" style={{ margin: 0 }}>{p.原因}</div>
                        {p.重放结果 ? (
                          <div className="讯" style={{ margin: 0 }}>
                            重放：{p.重放结果.结果} {p.重放结果.行程键 || p.重放结果.开腿键 || ""}
                          </div>
                        ) : null}
                        {r.状态 === "待回正" ? (
                          <button
                            className="次 亮片"
                            disabled={!p.是否允许回正}
                            onClick={() => 回正(r.编号)}
                          >
                            {p.是否允许回正 ? "回正写闸" : "不可回正"}
                          </button>
                        ) : (
                          <span className="徽章 通">已闭环</span>
                        )}
                      </>
                    ) : <span className="讯">预览加载中…</span>}
                  </td>
                  <td style={{ maxWidth: 300, wordBreak: "break-all" }}>{r.载荷}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <h2 className="题" style={{ fontSize: "1rem", marginTop: "1.5rem" }}>回正审计</h2>
      {!审计.length ? <div className="空态">尚无回正审计。</div> : (
        <table>
          <thead><tr><th>审计#</th><th>旁路#</th><th>卡号</th><th>事件</th><th>结果</th><th>行程键</th><th>开腿键</th><th>时刻</th></tr></thead>
          <tbody>
            {审计.map((a) => (
              <tr key={a.审计编号}>
                <td>{a.审计编号}</td><td>{a.旁路编号}</td><td>{a.卡号}</td><td>{a.事件编号}</td>
                <td>{a.结果}</td><td>{a.行程键 || "—"}</td><td>{a.开腿键 || "—"}</td><td>{a.时刻}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
