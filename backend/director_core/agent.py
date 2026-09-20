"""Portable role state and visible event formatter extracted from the verified engine."""
class Agent:
    def __init__(self, name: str, card: dict):
        self.name = name
        self.card = card
        self.location = card["start_location"]
        self.health = 100
        self.status = "active"      # active / down（失去行动能力吸收态）
        self.down_step = None
        self.diaries = []          # ["第1日：...", ...]
        self.last_full_events = []  # 最近亲历的结构化事件
        self.action_history = []   # [(action_type, target), ...]
        self.last_public = ""      # 上一步公开行动（跨步去重）
        self.last_dialogue = ""
        self.met_target = False    # 是否曾与目标同框
        # M5 多人+主角机制
        self.role = card.get("role", "supporting")  # protagonist/main/supporting/minor
        self.narrative_weight = card.get("narrative_weight", 0.4)
        self.arc = card.get("arc")

    def snapshot(self):
        return {"location": self.location, "health": self.health,
                "diaries": self.diaries}


class WorldEngine:
    def _format_event_for_agent(self, ev: dict):
        who = ev.get("actor", "世界")
        line = f"[#{ev['id']} 第{ev['step']}步 {ev.get('location','')}] {who}：{ev.get('public_action','')}"
        if ev.get("dialogue"):
            line += f" 说道：“{ev['dialogue']}”"
        if ev.get("result"):
            line += f" 结果：{ev['result']}"
        return line
