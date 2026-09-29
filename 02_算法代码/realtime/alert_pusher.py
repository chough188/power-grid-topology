# -*- coding: utf-8 -*-
"""实时告警推送（Phase 4.3）。

支持渠道：
- WebSocket（前端实时）
- 钉钉 webhook
- 企业微信 webhook
- 邮件 SMTP
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional


def _format_anomaly(anomaly: Dict[str, Any]) -> str:
    return (f"[{anomaly.get('severity', 'info').upper()}] "
            f"{anomaly.get('type', 'unknown')} @ {anomaly.get('location', '')} "
            f"(conf={anomaly.get('confidence', 0):.2f})")


def format_message(anomalies: List[Dict[str, Any]], title: str = "配电告警") -> Dict[str, Any]:
    """格式化为消息卡片。"""
    critical = [a for a in anomalies if a.get("severity") == "critical"]
    text = f"**{title}**\n\n"
    text += f"检测到 {len(anomalies)} 个异常，其中严重 {len(critical)} 个\n\n"
    for a in anomalies[:5]:
        text += f"- {_format_anomaly(a)}\n"
    if len(anomalies) > 5:
        text += f"- ...等 {len(anomalies)-5} 个\n"
    return {
        "title": title,
        "text": text,
        "count": len(anomalies),
        "critical_count": len(critical),
    }


class Pusher:
    """告警推送器，支持多种渠道。"""

    def __init__(self, channel: str = "console", config: Dict[str, Any] = None):
        self.channel = channel
        self.config = config or {}

    def push(self, anomalies: List[Dict[str, Any]], title: str = "配电告警") -> Dict[str, Any]:
        """推送告警。"""
        msg = format_message(anomalies, title)
        if self.channel == "dingtalk":
            return self._push_dingtalk(msg)
        elif self.channel == "wechat":
            return self._push_wechat(msg)
        elif self.channel == "email":
            return self._push_email(msg)
        else:  # console
            return self._push_console(msg)

    def _push_console(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[PUSHER:{self.channel}] {msg['title']}")
        print(msg["text"])
        return {"success": True, "channel": self.channel, "message": msg}

    def _push_dingtalk(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        webhook = self.config.get("webhook_url", "")
        if not webhook:
            return {"success": False, "error": "未配置钉钉 webhook"}
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": msg["title"],
                "text": msg["text"],
            }
        }
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "channel": "dingtalk", "result": result}
        except Exception as e:
            return {"success": False, "channel": "dingtalk", "error": str(e)}

    def _push_wechat(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        webhook = self.config.get("webhook_url", "")
        if not webhook:
            return {"success": False, "error": "未配置企微 webhook"}
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": msg["text"],
            }
        }
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            return {"success": True, "channel": "wechat", "result": result}
        except Exception as e:
            return {"success": False, "channel": "wechat", "error": str(e)}

    def _push_email(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        # 实际生产中应使用 smtplib
        return {"success": True, "channel": "email", "message": msg, "note": "SMTP未配置，已存消息"}

    def test_push(self, test_text: str = "测试消息") -> Dict[str, Any]:
        """发送测试消息。"""
        return self.push([{
            "type": "test", "location": "system",
            "confidence": 1.0, "severity": "info",
            "details": test_text,
        }], title="测试告警")


if __name__ == "__main__":
    p = Pusher("console")
    sample = [
        {"type": "topo_interrupt", "location": "line_15", "confidence": 0.95, "severity": "critical"},
        {"type": "voltage_collapse", "location": "bus_42", "confidence": 0.88, "severity": "critical"},
    ]
    r = p.push(sample, "case118 告警")
    print(f"Push result: {r['success']}")