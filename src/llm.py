"""LLM 客户端：DeepSeek（OpenAI 兼容接口）。

- 真实调用：DeepSeekLLM（需环境变量 DEEPSEEK_API_KEY）
- 测试/演示：MockLLM（确定性返回，不依赖网络）
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class LLMError(RuntimeError):
    pass


class BaseLLM:
    """LLM 抽象：chat(messages) -> str；chat_json(messages) -> dict"""

    def chat(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        text = self.chat(messages)
        return _parse_json(text)


def _parse_json(text: str) -> Dict[str, Any]:
    """从模型输出中解析 JSON（容忍 ```json 包裹与首尾噪声）。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # 尝试截取第一个 { 到最后一个 }
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise LLMError(f"模型输出不是合法 JSON：{text[:200]}")


class DeepSeekLLM(BaseLLM):
    """DeepSeek 官方 API（OpenAI 兼容）。"""

    def __init__(self, api_key: Optional[str] = None,
                 base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL,
                 temperature: float = 0.3,
                 timeout: int = 120,
                 max_retries: int = 2):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise LLMError(
                "未设置 DEEPSEEK_API_KEY：请 export DEEPSEEK_API_KEY=sk-xxx 后重试。")
        self.base_url = base_url.rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: List[Dict[str, str]]) -> str:
        import requests  # 仅真实模型调用需要；离线演示不安装也可运行
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model,
                          "messages": messages,
                          "temperature": self.temperature,
                          "response_format": {"type": "json_object"},
                          "stream": False},
                    timeout=self.timeout)
                if resp.status_code != 200:
                    raise LLMError(
                        f"API {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (requests.RequestException, LLMError, KeyError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次后）：{last_err}")


class MockLLM(BaseLLM):
    """确定性 mock：按用户消息中的关键字返回固定 JSON，用于测试与离线演示。"""

    def __init__(self):
        self.calls: List[Dict[str, str]] = []

    def chat(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(messages)
        joined = "\n".join(m.get("content", "") for m in messages)
        if "本任务为周追踪" in joined:
            return json.dumps({
                "improvements": ["迟到次数较上周减少"],
                "regressions": [],
                "patterns": ["迟到集中在下午第一节课"],
                "risk_level": "🟡 关注",
                "note": "本周变化：迟到减少 1 次；注意课堂讲话新增 1 次。",
            }, ensure_ascii=False)
        if "本任务为成长报告" in joined:
            return json.dumps({
                "report": "该生本月迟到 2 次，较上月 4 次减少；课堂纪律稳定。"
                          "建议延续当前引导方式，观察 2 周。",
            }, ensure_ascii=False)
        if "本任务为案例起草" in joined:
            return json.dumps({
                "title": "多次迟到学生的'先问作息、再给底线'处理法",
                "problem_type": "迟到",
                "background": "连续 1 个月下午第一节课迟到 4 次，集中在固定时段。",
                "analysis": "住宿生、宿舍违纪比例高，作息与同伴影响可能性大。",
                "process": "第一次谈话先问作息原因；无效后改规则执行，迟到即留堂。",
                "outcome": "部分改善：迟到由每周 2 次降为 1 次。",
                "reusable_principle": "先归因后定性：问作息而非谈态度；规则执行比道理辩论有效。",
                "applicable": "适用于住宿生作息型迟到。",
                "not_applicable": "不适用于有健康或家庭原因的迟到。",
            }, ensure_ascii=False)
        # 默认：事件分析
        return json.dumps({
            "level": "L2",
            "analysis": "该生迟到集中在下午第一节课，宿舍违纪比例高、同伴影响可能性大；"
                        "【待核实】是否夜间玩手机，需谈话确认。",
            "suggestions": [
                "本周小目标：下午第一节课提前 2 分钟进班，做到了口头肯定一次。",
                "谈话开场用观察句：'我注意到你本周有 2 次踩点进班，是遇到什么困难了吗？'——先问作息，不归因为态度。",
                "若学生防御强，先不谈道理，给规则底线并执行一致。",
            ],
            "needs_conversation": True,
            "conversation_topic": "先问作息与宿舍情况，再确认是否与同伴影响有关",
            "followup_plan": "建议 3 天内低压力谈话 1 次，谈后观察 1 周",
            "risk_notes": "避免直接定性为'态度问题'；不一次处理多件事。",
        }, ensure_ascii=False)


def build_llm(mock: bool = False) -> BaseLLM:
    if mock:
        return MockLLM()
    return DeepSeekLLM()
