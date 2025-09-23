"""
Fleet Carrier Discord Notifier - EDMC Plugin
Posts fleet carrier jump events to Discord via webhook.
"""

import tkinter as tk
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests

# EDMC imports
try:
    from config import config, appname, appversion
    import myNotebook as nb
except ImportError:
    from edmc_mocks import *

plugin_name = Path(__file__).resolve().parent.name

# Configuration keys
CONFIG_WEBHOOK = "fcms_discord_webhook"
CONFIG_CARRIER_ID = "fcms_carrier_id"
CONFIG_CARRIER_NAME = "fcms_carrier_name"
CONFIG_IMAGE_URL = "fcms_carrier_image"


class PluginConfig:
    def __init__(self):
        self.plugin_name = "Fleet Carrier Discord Notifier"
        self.version = "1.0.0"
        self.webhook_entry = None
        self.id_entry = None
        self.name_entry = None
        self.image_entry = None


config_state = PluginConfig()


def plugin_start3(plugin_dir: str) -> str:
    return "FCDN"


def plugin_stop() -> None:
    pass


def plugin_app(parent: tk.Frame) -> Optional[tk.Frame]:
    return None


def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> Optional[tk.Frame]:
    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)
    
    # Header
    nb.Label(frame, text="FCDN - Fleet Carrier Discord Notifier", font=("", 10, "bold")).grid(
        row=0, column=0, padx=10, pady=(10, 5), sticky=tk.W
    )
    nb.Label(frame, text=f"Version: {config_state.version}").grid(
        row=0, column=1, padx=10, pady=(10, 5), sticky=tk.E
    )
    
    # Settings
    settings = [
        ("Discord Webhook URL:", "webhook_entry"),
        ("Fleet Carrier ID:", "id_entry"),
        ("Fleet Carrier Name:", "name_entry"),
        ("Carrier Image URL:", "image_entry")
    ]
    
    for i, (label, attr) in enumerate(settings, 2):
        nb.Label(frame, text=label).grid(row=i, column=0, padx=10, pady=5, sticky=tk.W)
        entry = nb.Entry(frame, width=60)
        entry.grid(row=i, column=1, padx=10, pady=5, sticky=tk.EW)
        setattr(config_state, attr, entry)
    
    # Load current values
    config_state.webhook_entry.insert(0, config.get_str(CONFIG_WEBHOOK) or "")
    config_state.id_entry.insert(0, config.get_str(CONFIG_CARRIER_ID) or "")
    config_state.name_entry.insert(0, config.get_str(CONFIG_CARRIER_NAME) or "")
    config_state.image_entry.insert(0, config.get_str(CONFIG_IMAGE_URL) or "")
    
    # Help text
    help_text = [
        "Webhook URL: Discord → Server Settings → Integrations → Webhooks → New Webhook",
        "Carrier ID: Your Fleet Carrier ID (e.g., K3B-43M)",
        "Carrier Name: Your Fleet Carrier Name (e.g., VOYAGER I)",
        "Image URL: URL for carrier image. Leave blank for no image."
    ]
    
    for i, text in enumerate(help_text, 6):
        nb.Label(frame, text=text, justify=tk.LEFT).grid(
            row=i, column=0, columnspan=2, padx=10, pady=2, sticky=tk.W
        )
    
    # Test button
    test_frame = nb.Frame(frame)
    test_frame.grid(row=11, column=0, columnspan=2, padx=10, pady=10)
    
    nb.Button(test_frame, text="Test Webhook", command=test_webhook).grid(row=0, column=0, padx=5)
    
    return frame


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    if config_state.webhook_entry:
        config.set(CONFIG_WEBHOOK, config_state.webhook_entry.get().strip())
    if config_state.id_entry:
        config.set(CONFIG_CARRIER_ID, config_state.id_entry.get().strip())
    if config_state.name_entry:
        config.set(CONFIG_CARRIER_NAME, config_state.name_entry.get().strip())
    if config_state.image_entry:
        config.set(CONFIG_IMAGE_URL, config_state.image_entry.get().strip())


def get_carrier_display_name() -> str:
    carrier_id = config.get_str(CONFIG_CARRIER_ID) or ""
    carrier_name = config.get_str(CONFIG_CARRIER_NAME) or ""
    
    if carrier_id and carrier_name:
        return f"{carrier_id} {carrier_name}"
    elif carrier_id:
        return carrier_id
    elif carrier_name:
        return carrier_name
    return "Fleet Carrier"


def get_current_body(station: str, system: str) -> str:
    return station if station and station != "Orbiting" else f"{system} (Orbiting)"


def calculate_times(departure_time: str) -> tuple:
    try:
        departure_dt = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
        lockdown_dt = departure_dt - timedelta(minutes=3, seconds=20)
        
        lockdown_str = f"<t:{int(lockdown_dt.timestamp())}:R>"
        jump_str = f"<t:{int(departure_dt.timestamp())}:R>"
        return lockdown_str, jump_str
    except Exception:
        return "<t:0:R>", "<t:0:R>"


def create_discord_embed(cmdr: str, system: str, station: str, entry: Dict[str, Any], image_url: str = "") -> Dict[str, Any]:
    event_type = entry["event"]
    carrier_name = get_carrier_display_name()
    current_body = get_current_body(station, system)
    
    embed = {
        "timestamp": entry.get("timestamp", ""),
        "footer": {"text": f"EDMC FCDN • CMDR {cmdr}"}
    }
    
    if image_url:
        embed["image"] = {"url": image_url}
    
    if event_type == "CarrierJumpRequest":
        departure_time = entry.get("DepartureTime", "")
        lockdown_time, jump_time = calculate_times(departure_time)
        destination_body = entry.get("Body", "Unknown")
        
        embed.update({
            "title": "Frame Shift Drive Charging",
            "description": f"**{carrier_name}** is jumping.",
            "color": 0x3498db,
            "fields": [
                {"name": "Departing from", "value": f"```{system}```", "inline": False},
                {"name": "Currently Orbiting", "value": f"```{current_body}```", "inline": False},
                {"name": "Headed to", "value": f"```{destination_body}```", "inline": False},
                {"name": "Estimated lockdown time", "value": lockdown_time, "inline": True},
                {"name": "Estimated jump time", "value": jump_time, "inline": True}
            ]
        })
        
    elif event_type == "CarrierJumpCancelled":
        embed.update({
            "title": "Jump Sequence Cancelled",
            "description": f"**{carrier_name}** jump has been cancelled.",
            "color": 0xe74c3c,
            "fields": [
                {"name": "Current Location", "value": f"```{system}```", "inline": False},
                {"name": "Currently Orbiting", "value": f"```{current_body}```", "inline": False},
            ]
        })
    
    return embed


def test_webhook() -> None:
    webhook_url = config_state.webhook_entry.get().strip() if config_state.webhook_entry else ""
    image_url = config_state.image_entry.get().strip() if config_state.image_entry else ""
    
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return
    
    embed = {
        "title": "Webhook Test",
        "description": "Your Fleet Carrier Discord Notifier is working correctly!\nIf you've entered a fleet carrier image URL, your image should be visible below.",
        "color": 0x00ff00,
        "footer": {"text": "EDMC FCDN Test"}
    }
    
    if image_url:
        embed["image"] = {"url": image_url}
    
    try:
        payload = {"embeds": [embed]}
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception:
        pass


def journal_entry(cmdr: str, is_beta: bool, system: str, station: str, entry: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    event_type = entry.get("event")
    
    if event_type not in ["CarrierJumpRequest", "CarrierJumpCancelled"] or is_beta:
        return None
    
    webhook_url = config.get_str(CONFIG_WEBHOOK) or ""
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return "FCDN: Configure Discord webhook URL in settings."
    
    if not config.get_str(CONFIG_CARRIER_ID) and not config.get_str(CONFIG_CARRIER_NAME):
        return "FCDN: Configure Fleet Carrier ID and Name in settings."
    
    image_url = config.get_str(CONFIG_IMAGE_URL) or ""
    embed = create_discord_embed(cmdr, system, station, entry, image_url)
    
    try:
        response = requests.post(webhook_url, json={"embeds": [embed]}, timeout=30)
        return None if response.status_code in [200, 204] else "FCDN: Discord webhook error."
    except Exception:
        return "FCDN: Error sending to Discord."