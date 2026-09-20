"""M1 实体状态机内核（事实层 v2 · Stage 1）。

纯符号、确定性、不依赖 LLM，也【不】从自由文本抽取物品或流转事件
（文本识别是独立的识别层，其准确率单独评测，不混入本内核）。

职责
----
维护每个实体的客观状态与当前位置/持有者，并对"某角色此刻取用某实体"给出风险等级。

设计要点（对应 docs/design/FACT-LAYER-V2-DESIGN.md）
- 状态只有 active / destroyed 两态；active 时 holder(随身者) 与 location(所在地点) 恰有一个非空。
- 状态只能由【世界裁决】经显式事件改变；角色口头 claim 不得改状态（承继不变量 I2）。
- "销毁后重新获得"通过 pickup/transfer 把状态复活为 active，故 destroyed 即代表"销毁后无再获得"。
- 本层不认识的实体（不在库中）返回 None 表示"不表态"，交由上层（v1 开放层 / 未来 M3 语义裁判）。

风险与响应
----------
- R0 可立即取用（本人随身 / 就在其所在地点）             -> L0 放行
- R1 取用已销毁且未再获得的实体                          -> L2 硬拦改写
- R2 实体存在但此刻不可即取（在他人处/他处，且无持有记录） -> L1 软标注、不改叙事
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Entity:
    eid: str
    state: str = "active"                 # active / destroyed
    holder: Optional[str] = None          # 随身持有角色名
    location: Optional[str] = None        # 所在地点（与 holder 互斥）
    log: list = field(default_factory=list)  # [(step, event, detail)]

    def is_held_or_present(self, who: str, who_location: Optional[str]) -> bool:
        """该角色此刻能否立即取用：本人随身，或实体就在其所在地点。"""
        if self.holder == who:
            return True
        if self.location and who_location and \
                (self.location in who_location or who_location in self.location):
            return True
        return False


class EntityStateMachine:
    """实体客观状态的唯一权威。所有变更方法返回 bool（是否成功），失败不改状态。"""

    def __init__(self, entities: Optional[dict] = None):
        self.entities: dict[str, Entity] = {}
        for eid, kw in (entities or {}).items():
            self.entities[eid] = Entity(eid=eid, **kw)
            self._check_invariant(self.entities[eid])

    # ---------- 不变量 ----------
    @staticmethod
    def _check_invariant(e: Entity):
        if e.state == "active":
            assert (e.holder is None) ^ (e.location is None), \
                f"实体[{e.eid}]active 时 holder/location 必须恰有一个非空"
        elif e.state == "destroyed":
            assert e.holder is None and e.location is None, \
                f"实体[{e.eid}]destroyed 时不得有 holder/location"
        else:
            raise AssertionError(f"实体[{e.eid}]非法状态 {e.state}")

    # ---------- 世界裁决事件（唯一改状态入口）----------
    def _record(self, e: Entity, step: int, event: str, detail: str):
        e.log.append((step, event, detail))

    def transfer(self, step: int, eid: str, to_who: str) -> bool:
        """转交：持有者变为 to_who（含夺取/拾取后转交）。目标不存在则失败。"""
        e = self.entities.get(eid)
        if e is None or not to_who:
            return False
        e.state, e.holder, e.location = "active", to_who, None
        self._record(e, step, "transfer", f"->holder {to_who}")
        self._check_invariant(e)
        return True

    def pickup(self, step: int, eid: str, who: str) -> bool:
        """拾得/重新获得：角色在现场取得，随身持有（可使 destroyed 实体复活）。"""
        e = self.entities.get(eid)
        if e is None or not who:
            return False
        e.state, e.holder, e.location = "active", who, None
        self._record(e, step, "pickup", f"->holder {who}")
        self._check_invariant(e)
        return True

    def drop(self, step: int, eid: str, where: str) -> bool:
        """掉落/遗置/藏匿到某地：无人随身，位于 where。"""
        e = self.entities.get(eid)
        if e is None or not where:
            return False
        e.state, e.holder, e.location = "active", None, where
        self._record(e, step, "drop", f"->location {where}")
        self._check_invariant(e)
        return True

    def destroy(self, step: int, eid: str) -> bool:
        """销毁/消耗（不可逆，除非世界裁决后续 pickup/transfer 复活）。"""
        e = self.entities.get(eid)
        if e is None:
            return False
        e.state, e.holder, e.location = "destroyed", None, None
        self._record(e, step, "destroy", "destroyed")
        self._check_invariant(e)
        return True

    # ---------- 取用风险仲裁 ----------
    def assess(self, who: str, who_location: Optional[str], eid: str) -> Optional[dict]:
        """返回风险评估 dict；实体不由本层管理时返回 None（不表态）。

        返回: {eid, risk: R0/R1/R2, level: L0/L1/L2, reason}
        """
        e = self.entities.get(eid)
        if e is None:
            return None
        if e.state == "destroyed":
            return {"eid": eid, "risk": "R1", "level": "L2",
                    "reason": f"{eid}已被销毁且此后无重新获得记录"}
        if e.is_held_or_present(who, who_location):
            return {"eid": eid, "risk": "R0", "level": "L0",
                    "reason": f"{who}此刻可立即取用{eid}"}
        return {"eid": eid, "risk": "R2", "level": "L1",
                "reason": f"{eid}存在但不在{who}身上/其所在地点"}


def apply_response(decision: dict, assessment: dict, who: str, pronoun: str = "他") -> dict:
    """纯函数：按风险等级对决策副本做分级响应（实现验收 A9/A10）。

    - L0/L1：不改写 public_action/dialogue（L1 仅由调用方另记软日志）。
    - L2：改写为"摸空"，清空基于该物的台词，置 _hard_blocked。
    返回同一 decision（原地修改）。
    """
    level = assessment["level"]
    if level == "L2":
        decision["public_action"] = (
            f"{who}伸手欲取{assessment['eid']}，却摸了个空——"
            f"{pronoun}根本没有这东西，动作僵在半空，神色微变。"
        )
        decision["dialogue"] = ""
        decision["_hard_blocked"] = True
        decision["_block_reason"] = assessment["reason"]
    # L0/L1: 不动叙事；L1 的软记录由 engine 写 claim_log
    return decision
