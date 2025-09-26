"""
Fleet Carrier Discord Notifier - EDMC Plugin
Posts fleet carrier jump events to Discord via webhook.
"""

import tkinter as tk
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests
import math
import logging
import os
# lru_cache to avoid repeated EDSM lookups
from functools import lru_cache  

# EDMC imports
try:
    from config import config, appname, appversion
    import myNotebook as nb
except ImportError:
    from edmc_mocks import *

# Set up logging
plugin_name = Path(__file__).resolve().parent.name
logger = logging.getLogger(f'{appname}.{plugin_name}')

# Only set up logging if not already configured by EDMC
if not logger.hasHandlers():
    level = logging.INFO
    logger.setLevel(level)
    logger_channel = logging.StreamHandler()
    logger_formatter = logging.Formatter(f'%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d:%(funcName)s: %(message)s')
    logger_formatter.default_time_format = '%Y-%m-%d %H:%M:%S'
    logger_formatter.default_msec_format = '%s.%03d'
    logger_channel.setFormatter(logger_formatter)
    logger.addHandler(logger_channel)

# Configuration keys
CONFIG_WEBHOOK = "fcms_discord_webhook"
CONFIG_CARRIER_NAME = "fcms_carrier_name"
CONFIG_IMAGE_URL = "fcms_carrier_image"
CONFIG_FUEL_MODE = "fcms_fuel_mode"
CONFIG_SHOW_DISTANCE = "fcms_show_distance"
CONFIG_SHOW_USAGE = "fcms_show_usage"
CONFIG_SHOW_REMAINING = "fcms_show_remaining"
CONFIG_SHOW_TRITIUM_CANCEL = "fcms_show_tritium_cancel"
CONFIG_SHOW_UI = "fcms_show_ui"

showUI = False

class PluginConfig:
    def __init__(self):
        self.plugin_name = "Fleet Carrier Discord Notifier"
        self.version = "1.1.3"
        self.webhook_entry = None
        self.id_entry = None
        self.name_entry = None
        self.image_entry = None
        self.fuel_mode_var = None
        self.show_distance_var = None
        self.show_usage_var = None
        self.show_remaining_var = None
        self.show_tritium_cancel_var = None
        self.show_ui_var = None  # Add this line
        self.latest_version = None  # Store the latest version from GitHub


config_state = PluginConfig()



def is_valid_url(url: str) -> bool:
    """ Basic URL validation """
    if not url or not url.strip():
        return False
    url = url.strip()
    return url.startswith(('http://', 'https://'))


def plugin_start3(plugin_dir: str) -> str:
    logger.info("Plugin started")
    
    global showUI
    showUI = config.get_bool(CONFIG_SHOW_UI) if config.get_bool(CONFIG_SHOW_UI) is not None else False
    logger.debug(f"Initialized showUI from config: {showUI}")
    
    # Check for latest version on plugin boot
    try:
        response = requests.get("https://raw.githubusercontent.com/aweeri/FCDN/refs/heads/main/VERSION", timeout=5)
        if response.status_code == 200:
            config_state.latest_version = response.text.strip()
            logger.info(f"Latest version available: {config_state.latest_version}")
        else:
            logger.warning(f"Failed to fetch version file. Status code: {response.status_code}")
    except Exception as e:
        logger.warning(f"Error checking for latest version: {e}")
    
    return "FCDN"


def plugin_stop() -> None:
    logger.info("Plugin stopped")



def plugin_app(parent: tk.Frame) -> Optional[tk.Frame]:
    """
    EDMC main window plugin UI
    """
    # Create main frame
    frame = tk.Frame(parent)
    
    # Boolean to control section visibility
    show_section = showUI
    
    # Create collapsible section for Market Announcements
    market_frame = tk.LabelFrame(frame, text="FCDN", padx=5, pady=5)
    
    # Only pack the market frame if show_section is True
    if show_section:
        market_frame.pack(fill="x", expand=False, pady=5, padx=5)
    
        # Create button frame inside the market section
        button_frame = tk.Frame(market_frame)
        button_frame.pack(fill="x", expand=True, pady=5)
    
        sell_button = tk.Button(button_frame, text="Selling", command=fcdn_sell_action, width=10)
        sell_button.pack(side="left", padx=5, expand=True)
    
        buy_button = tk.Button(button_frame, text="Buying", command=fcdn_buy_action, width=10)
        buy_button.pack(side="left", padx=5, expand=True)
    
        # Add some informational text
        info_label = tk.Label(market_frame, text="Announce market operations to Discord", font=("", 8), fg="gray")
        info_label.pack(pady=(0, 5))
    
    return frame


def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> Optional[tk.Frame]:
    """
    FCDN settings UI
    """
    logger.debug("Loading plugin preferences UI")
    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)
    
    current_row = 0
    
    nb.Label(frame, text="FCDN - Fleet Carrier Discord Notifier", font=("", 10, "bold")).grid(
        row=current_row, column=0, padx=10, pady=(10, 5), sticky=tk.W
    )
    nb.Label(frame, text=f"Version: {config_state.version}").grid(
        row=current_row, column=1, padx=10, pady=(10, 5), sticky=tk.E
    )
    
    current_row += 1
    
    settings = [
        ("Discord Webhook URL:", "webhook_entry"),
        ("Fleet Carrier Name:", "name_entry"),
        ("Carrier Image URL:", "image_entry")
    ]
    
    for label, attr in settings:
        current_row += 1
        nb.Label(frame, text=label).grid(row=current_row, column=0, padx=10, pady=5, sticky=tk.W)
        entry = nb.Entry(frame, width=60)
        entry.grid(row=current_row, column=1, padx=10, pady=5, sticky=tk.EW)
        setattr(config_state, attr, entry)
    
    # Load current values
    config_state.webhook_entry.insert(0, config.get_str(CONFIG_WEBHOOK) or "")
    config_state.name_entry.insert(0, config.get_str(CONFIG_CARRIER_NAME) or "")
    config_state.image_entry.insert(0, config.get_str(CONFIG_IMAGE_URL) or "")
    
    help_text = [
        "Webhook URL: Discord â†’ Server Settings â†’ Integrations â†’ Webhooks â†’ New Webhook",
        "Carrier Name: Your Fleet Carrier Name (e.g., VOYAGER I)",
        "Image URL: URL for carrier image. Must start with http:// or https://"
    ]
    
    for text in help_text:
        current_row += 1
        nb.Label(frame, text=text, justify=tk.LEFT).grid(
            row=current_row, column=0, columnspan=2, padx=10, pady=2, sticky=tk.W
        )
    
    current_row += 1
    
    def update_fuel_options():
        state = tk.NORMAL if config_state.fuel_mode_var.get() else tk.DISABLED
        config_state.show_distance_checkbox.config(state=state)
        config_state.show_usage_checkbox.config(state=state)
        config_state.show_remaining_checkbox.config(state=state)
        
        # Deselect checkboxes when integration is disabled
        if not config_state.fuel_mode_var.get():
            config_state.show_distance_var.set(False)
            config_state.show_usage_var.set(False)
            config_state.show_remaining_var.set(False)
    
    fuel_mode_default = config.get_bool(CONFIG_FUEL_MODE) if config.get_bool(CONFIG_FUEL_MODE) is not None else True
    config_state.fuel_mode_var = tk.BooleanVar(value=fuel_mode_default)
    fuel_mode_checkbox = nb.Checkbutton(frame, text="Enable EDSM Integration", variable=config_state.fuel_mode_var, command=update_fuel_options)
    fuel_mode_checkbox.grid(row=current_row, column=0, columnspan=2, padx=10, pady=(15, 5), sticky=tk.W)
    
    current_row += 1
    
    fuel_options_frame = nb.Frame(frame)
    fuel_options_frame.grid(row=current_row, column=0, columnspan=2, padx=25, pady=(0, 5), sticky=tk.W)
    
    show_distance_default = config.get_bool(CONFIG_SHOW_DISTANCE) if config.get_bool(CONFIG_SHOW_DISTANCE) is not None else True
    config_state.show_distance_var = tk.BooleanVar(value=show_distance_default)
    config_state.show_distance_checkbox = nb.Checkbutton(fuel_options_frame, text="Show calculated jump distance", variable=config_state.show_distance_var)
    config_state.show_distance_checkbox.grid(row=0, column=0, sticky=tk.W)
    
    show_usage_default = config.get_bool(CONFIG_SHOW_USAGE) if config.get_bool(CONFIG_SHOW_USAGE) is not None else True
    config_state.show_usage_var = tk.BooleanVar(value=show_usage_default)
    config_state.show_usage_checkbox = nb.Checkbutton(fuel_options_frame, text="Show estimated fuel usage", variable=config_state.show_usage_var)
    config_state.show_usage_checkbox.grid(row=1, column=0, sticky=tk.W)
    
    show_remaining_default = config.get_bool(CONFIG_SHOW_REMAINING) if config.get_bool(CONFIG_SHOW_REMAINING) is not None else True
    config_state.show_remaining_var = tk.BooleanVar(value=show_remaining_default)
    config_state.show_remaining_checkbox = nb.Checkbutton(fuel_options_frame, text="Show estimated fuel after jump", variable=config_state.show_remaining_var)
    config_state.show_remaining_checkbox.grid(row=2, column=0, sticky=tk.W)
    
    update_fuel_options()
    
    current_row += 1
    
    # Tritium on cancel checkbox
    show_tritium_cancel_default = config.get_bool(CONFIG_SHOW_TRITIUM_CANCEL) if config.get_bool(CONFIG_SHOW_TRITIUM_CANCEL) is not None else True
    config_state.show_tritium_cancel_var = tk.BooleanVar(value=show_tritium_cancel_default)
    config_state.show_tritium_cancel_checkbox = nb.Checkbutton(frame, text="Show Tritium on Jump cancel", variable=config_state.show_tritium_cancel_var)
    config_state.show_tritium_cancel_checkbox.grid(row=current_row, column=0, columnspan=2, padx=10, pady=(10, 5), sticky=tk.W)
    
    current_row += 1
    
    # Show UI checkbox
    show_ui_default = config.get_bool(CONFIG_SHOW_UI) if config.get_bool(CONFIG_SHOW_UI) is not None else False
    config_state.show_ui_var = tk.BooleanVar(value=show_ui_default)
    config_state.show_ui_checkbox = nb.Checkbutton(frame, text="Show extras in main UI (Needs restart)", variable=config_state.show_ui_var)
    config_state.show_ui_checkbox.grid(row=current_row, column=0, columnspan=2, padx=10, pady=(10, 5), sticky=tk.W)
    
    current_row += 1
    
    test_frame = nb.Frame(frame)
    test_frame.grid(row=current_row, column=0, columnspan=2, padx=10, pady=10, sticky=tk.W)
    
    nb.Button(test_frame, text="Test Webhook", command=test_webhook).grid(row=0, column=0, padx=5)
    
    # Version information at the end of settings
    current_row += 1
    
    version_frame = nb.Frame(frame)
    version_frame.grid(row=current_row, column=0, columnspan=2, padx=10, pady=(20, 10), sticky=tk.W)
    
    # Currently installed version
    nb.Label(version_frame, text=f"Currently installed version: {config_state.version}").grid(row=0, column=0, sticky=tk.W)
    
    # Latest version with hyperlink
    latest_version = config_state.latest_version or "Unknown"
    if latest_version != "Unknown":
        latest_label = nb.Label(version_frame, text=f"Latest version: {latest_version}", cursor="hand2", foreground="blue")
        latest_label.grid(row=1, column=0, sticky=tk.W)
        
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/aweeri/FCDN")
        
        latest_label.bind("<Button-1>", open_github)
    else:
        nb.Label(version_frame, text=f"Latest version: {latest_version}").grid(row=1, column=0, sticky=tk.W)
    
    return frame


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    logger.debug("Preferences changed")
    
    if config_state.webhook_entry:
        config.set(CONFIG_WEBHOOK, config_state.webhook_entry.get().strip())
    if config_state.name_entry:
        config.set(CONFIG_CARRIER_NAME, config_state.name_entry.get().strip())
    if config_state.image_entry:
        config.set(CONFIG_IMAGE_URL, config_state.image_entry.get().strip())
    
    if config_state.fuel_mode_var is not None:
        config.set(CONFIG_FUEL_MODE, config_state.fuel_mode_var.get())
        logger.debug(f"Integration mode set to: {config_state.fuel_mode_var.get()}")  # CHANGE
    
    if config_state.show_distance_var is not None:
        config.set(CONFIG_SHOW_DISTANCE, config_state.show_distance_var.get())
        logger.debug(f"Show distance set to: {config_state.show_distance_var.get()}")
    if config_state.show_usage_var is not None:
        config.set(CONFIG_SHOW_USAGE, config_state.show_usage_var.get())
        logger.debug(f"Show usage set to: {config_state.show_usage_var.get()}")
    if config_state.show_remaining_var is not None:
        config.set(CONFIG_SHOW_REMAINING, config_state.show_remaining_var.get())
        logger.debug(f"Show remaining set to: {config_state.show_remaining_var.get()}")
    if config_state.show_tritium_cancel_var is not None:
        config.set(CONFIG_SHOW_TRITIUM_CANCEL, config_state.show_tritium_cancel_var.get())
        logger.debug(f"Show tritium on cancel set to: {config_state.show_tritium_cancel_var.get()}")
    if config_state.show_ui_var is not None:
        config.set(CONFIG_SHOW_UI, config_state.show_ui_var.get())
        global showUI
        showUI = config_state.show_ui_var.get()
        logger.debug(f"Show UI set to: {showUI}")





def calculate_times(departure_time: str) -> tuple:
    try:
        departure_dt = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
        lockdown_dt = departure_dt - timedelta(minutes=3, seconds=20)
        
        lockdown_str = f"<t:{int(lockdown_dt.timestamp())}:R>"
        jump_str = f"<t:{int(departure_dt.timestamp())}:R>"
        return lockdown_str, jump_str
    except Exception as e:
        logger.warning(f"Failed to parse departure time: {e}")
        return "<t:0:R>", "<t:0:R>"
    

# cache EDSM responses to reduce API load
@lru_cache(maxsize=4096)
def edsm_coords(system_name: str):
    try:
        r = requests.get(
            "https://www.edsm.net/api-v1/system",
            params={"systemName": system_name, "showCoordinates": 1},
            timeout=10,
        )
        js = r.json()
        if isinstance(js, dict) and "coords" in js:
            c = js["coords"]
            return float(c["x"]), float(c["y"]), float(c["z"])
        logger.debug(f"EDSM coordinates not found for system: {system_name}")
        return None
    except Exception as e:
        logger.warning(f"EDSM API error for {system_name}: {e}")
        return None


def ly_distance(a_name: str, b_name: str) -> float | None:
    a = edsm_coords(a_name)
    b = edsm_coords(b_name)
    if not a or not b:
        return None
    (x1, y1, z1), (x2, y2, z2) = a, b
    return math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)

_carrier_state = {"fuel": 0, "used": 0, "id": "Unknown"}

def update_carrier_state(entry: Dict[str, Any]) -> None:
    #Update carrier state cache from a CarrierStats event
    global _carrier_state
    _carrier_state["fuel"] = int(entry.get("FuelLevel") or 0)

    space = entry.get("SpaceUsage") or {}
    used = space.get("UsedSpace")
    # UsedSpace is a bit fucked sometimes, back up option needed
    if used is None:
        total, free = space.get("TotalCapacity"), space.get("FreeSpace")
        if total is not None and free is not None:
            used = total - free
    
    _carrier_state["used"] = int(used or 0)

    _carrier_state["id"] = entry.get("Callsign")
    
    logger.debug(f"Carrier state updated - fuel: {_carrier_state['fuel']}, used: {_carrier_state['used']}")


def get_carrier_state() -> tuple[int, int]:
    return _carrier_state["fuel"], _carrier_state["used"], _carrier_state["id"]


# obey integration flag; never call EDSM when disabled
def carrier_fuel_cost(start_system, end_system, fuel_level, used_space, integration_enabled: bool):
    if not integration_enabled:  
        return None, None, None  
    
    jump_distance = ly_distance(start_system, end_system)
    
    if jump_distance is None:
        logger.debug(f"Could not calculate distance between {start_system} and {end_system}")
        return None, None, fuel_level
    
    if jump_distance > 500:
        logger.debug(f"Jump distance {jump_distance} ly exceeds 500 ly limit")
        return None, None, fuel_level

    # clamp distance incase something else is wrong
    d = max(0.0, min(500.0, float(jump_distance)))
    total_mass = (fuel_level or 0) + (used_space or 0)

    # community formula for fuel cost: 5 + d*(25_000 + mass)/200_000, rounded up
    fuel_cost = math.ceil(5 + d * (25000 + total_mass) / 200000)

    remaining_fuel = max(0, (fuel_level or 0) - fuel_cost)
    
    logger.debug(f"Fuel calculation: distance={d:.2f} ly, cost={fuel_cost} t, remaining={remaining_fuel} t")
    return jump_distance, fuel_cost, remaining_fuel


def is_player_on_their_carrier(state: Dict[str, Any], carrier_id) -> bool:
    station_name = state.get('StationName', '')
    
    logger.debug(f"Carrier validation - Configured ID: '{carrier_id}', Station: '{station_name}'")
    
    if not carrier_id:
        logger.warning("No carrier ID configured in settings")
        return False
    
    if not station_name:
        logger.debug("Player not at a station (may be in space or on foot)")
        return False
    
    # Check if the configured carrier ID appears in the station name
    carrier_id_clean = carrier_id.replace('-', '').replace(' ', '').upper()
    station_clean = station_name.replace('-', '').replace(' ', '').upper()
    
    # Also check if station name contains the full carrier ID with dashes
    contains_id = (carrier_id_clean in station_clean) or (carrier_id.upper() in station_name.upper())
    
    logger.debug(f"Carrier validation - Clean ID: '{carrier_id_clean}', Clean Station: '{station_clean}', Match: {contains_id}")
    
    if contains_id:
        logger.info(f"Player confirmed on their carrier: {station_name} matches configured ID {carrier_id}")
        return True
    else:
        logger.warning(f"Player not on their carrier. Station '{station_name}' doesn't match configured ID '{carrier_id}'")
        return False


def create_discord_embed(cmdr: str, system: str, station: str,
                         entry: Dict[str, Any], fuel_level: int, used_space: int, carrier_id : int,
                         image_url: str = "", on_own_carrier: bool = True) -> Dict[str, Any]:
    
    event_type = entry["event"]
    carrier_name = config.get_str(CONFIG_CARRIER_NAME) + " (" + carrier_id + ")"
    logger.debug(f"Assigned carrier name is: {carrier_name}")

    embed = {
        "timestamp": entry.get("timestamp", ""),
        "footer": {"text": f"EDMC FCDN • CMDR {cmdr}"}
    }
    
    # Add image only if URL is valid
    if is_valid_url(image_url):
        embed["image"] = {"url": image_url.strip()}
        logger.debug(f"Added image URL to embed: {image_url}")
    elif image_url and image_url.strip():
        logger.warning(f"Invalid image URL format (must start with http:// or https://): {image_url}")
    
    if event_type == "CarrierJumpRequest":
        departure_time = entry.get("DepartureTime", "")
        lockdown_time, jump_time = calculate_times(departure_time)
        destination_system = entry.get("SystemName")
        destination_body = entry.get("Body", "Unknown")

        if on_own_carrier:
            # Player is on their carrier - calculate everything normally
            integration_enabled = bool(config.get_bool(CONFIG_FUEL_MODE))  
            jump_distance, fuel_cost, remaining_fuel = carrier_fuel_cost(  
                system, destination_system, fuel_level, used_space, integration_enabled
            ) 
            
            fields = [
                {"name": "Departing from", "value": f"```{system}```", "inline": False},
                {"name": "Headed to", "value": f"```{destination_system or destination_body}```", "inline": False},
            ]

            # Get current checkbox states
            show_distance = config.get_bool(CONFIG_SHOW_DISTANCE)
            show_usage = config.get_bool(CONFIG_SHOW_USAGE)
            show_remaining = config.get_bool(CONFIG_SHOW_REMAINING)

            
            logger.debug(f"Checkbox states - Distance: {show_distance}, Usage: {show_usage}, Remaining: {show_remaining}")
            
            #whether to add jump distance info
            if show_distance and jump_distance is not None:
                fields.append({
                    "name": "Jump Distance",
                    "value": f"```{jump_distance:.2f} ly```",
                    "inline": False
                })
            #whether to add fuel usage (when enabled and not invalid)
            if show_usage and fuel_cost not in (None, 0):
                fields.append({
                    "name": "Estimated Fuel Usage",
                    "value": f"```{fuel_cost} t```",
                    "inline": False
                })
            # whether to show remaining fuel (when valid, and enabled)
            if show_remaining and fuel_level not in (None, 0):  
                fields.append({
                    "name": "Tritium After Jump",
                    "value": f"```{remaining_fuel} t```",
                    "inline": False
                })
        else:
            # Player is not on their carrier - only show destination
            logger.info("Remote jump scheduling detected - showing destination only")
            fields = [
                {"name": "Headed to", "value": f"```{destination_system or destination_body}```", "inline": False},
                {"name": "Note", "value": "Jump scheduled remotely - location and fuel data unavailable", "inline": False},
            ]
            jump_distance, fuel_cost, remaining_fuel = None, None, None
        
        fields.extend([
            {"name": "Estimated lockdown time", "value": lockdown_time, "inline": True},
            {"name": "Estimated jump time", "value": jump_time, "inline": True},
        ])
    
        embed.update({
            "title": "Frame Shift Drive Charging",
            "description": f"**{carrier_name}** is jumping.",
            "color": 0x3498db,
            "fields": fields
        })
        
    elif event_type == "CarrierJumpCancelled":
        fields = [
            {"name": "Current Location", "value": f"```{system}```", "inline": False},
        ]

        # Check if we should show tritium on jump cancel
        show_tritium_cancel = config.get_bool(CONFIG_SHOW_TRITIUM_CANCEL)
        logger.debug(f"Show tritium on cancel: {show_tritium_cancel}, Fuel level: {fuel_level}")
        
        if show_tritium_cancel and fuel_level not in (None, 0):
            fields.append({"name": "Tritium Level", "value": f"```{fuel_level}t```", "inline": False})
        
        embed.update({
            "title": "Jump Sequence Cancelled",
            "description": f"**{carrier_name}** jump has been cancelled.",
            "color": 0xe74c3c,
            "fields": fields
        })
    
    return embed

def fcdn_sell_action() -> None:
    """
    Post fleet carrier sell action to Discord webhook with formatted market data.
    """
    # example data - replace with actual market data retrieval
    market_items = [
        ("Aluminum", 1500, 750000),
        ("Void Opals", 800, 950000),
        ("Tritium", 50000, 50000),
        ("Gold", 2500, 45000)
    ]
    
    # Use saved config
    webhook_url = config.get_str(CONFIG_WEBHOOK) or ""
    image_url = config.get_str(CONFIG_IMAGE_URL) or ""
    
    if not webhook_url.startswith(
        ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
    ):
        logger.warning("Invalid webhook URL format")
        return
    
    # Validate image URL
    if image_url and not is_valid_url(image_url):
        logger.warning(f"Image URL should start with http:// or https://: {image_url}")
    
    # Compact items description
    items_description = ""
    for name, supply, price in market_items:
        formatted_supply = f"{supply:,}" if isinstance(supply, int) else str(supply)
        formatted_price = f"{price:,}" if isinstance(price, (int, float)) else str(price)
        items_description += f"**{name}**\n`{formatted_supply} t` @ `{formatted_price} cr`\n"
    
    embed = {
        "title": "Fleet Carrier Market Update - WORK IN PROGRESS",
        "description": "### **Currently Selling:**\n" + items_description,
        "color": 0x00ff00,
        "footer": {"text": "EDMC FCDN - Manual Sell Announcement"}
    }
    
    # Add image only if URL is valid
    if is_valid_url(image_url):
        embed["image"] = {"url": image_url.strip()}
        logger.debug(f"Posting sell action with image URL: {image_url}")
    
    try:
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            logger.info(f"FCDN sell action posted successfully for {len(market_items)} items")
        else:
            logger.warning(f"FCDN sell action failed with status: {response.status_code}")
            logger.debug(f"Response content: {response.text}")
    except Exception as e:
        logger.error(f"FCDN sell action error: {e}")

def fcdn_buy_action():
    """
    Post fleet carrier buy action to Discord webhook with formatted market data.
    """
    # example data - replace with actual market data retrieval
    market_items = [
        ("Aluminum", 1500, 750000),
        ("Void Opals", 800, 950000),
        ("Tritium", 50000, 50000),
        ("Gold", 2500, 45000)
    ]
    
    # Use saved config
    webhook_url = config.get_str(CONFIG_WEBHOOK) or ""
    image_url = config.get_str(CONFIG_IMAGE_URL) or ""
    
    if not webhook_url.startswith(
        ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
    ):
        logger.warning("Invalid webhook URL format")
        return
    
    # Validate image URL
    if image_url and not is_valid_url(image_url):
        logger.warning(f"Image URL should start with http:// or https://: {image_url}")
    
    # Compact items description
    items_description = ""
    for name, demand, price in market_items:
        formatted_demand = f"{demand:,}" if isinstance(demand, int) else str(demand)
        formatted_price = f"{price:,}" if isinstance(price, (int, float)) else str(price)
        items_description += f"**{name}**\n`{formatted_demand} t` @ `{formatted_price} cr`\n"
    
    embed = {
        "title": "Fleet Carrier Market Update - WORK IN PROGRESS",
        "description": "### **Currently Buying:**\n" + items_description,
        "color": 0x00ff00,
        "footer": {"text": "EDMC FCDN - Manual Buy Announcement"}
    }
    
    # Add image only if URL is valid
    if is_valid_url(image_url):
        embed["image"] = {"url": image_url.strip()}
        logger.debug(f"Posting buy action with image URL: {image_url}")
    
    try:
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            logger.info(f"FCDN buy action posted successfully for {len(market_items)} items")
        else:
            logger.warning(f"FCDN buy action failed with status: {response.status_code}")
            logger.debug(f"Response content: {response.text}")
    except Exception as e:
        logger.error(f"FCDN buy action error: {e}")

def test_webhook() -> None:
    """
        Test webhook
    """
    webhook_url = config_state.webhook_entry.get().strip() if config_state.webhook_entry else ""
    image_url = config_state.image_entry.get().strip() if config_state.image_entry else ""
    
    if not webhook_url.startswith(
        ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
    ):
        logger.warning("Invalid webhook URL format")
        return
    
    # Validate image URL and provide feedback
    if image_url and not is_valid_url(image_url):
        logger.warning(f"Image URL should start with http:// or https://: {image_url}")
    
    embed = {
        "title": "Webhook Test",
        "description": "Your Fleet Carrier Discord Notifier is working correctly!",
        "color": 0x00ff00,
        "footer": {"text": "EDMC FCDN Test"}
    }
    
    # Add image only if URL is valid
    if is_valid_url(image_url):
        embed["image"] = {"url": image_url.strip()}
        embed["description"] += "\nIf you've entered a valid fleet carrier image URL, your image should be visible below."
        logger.debug(f"Testing webhook with image URL: {image_url}")
    else:
        embed["description"] += "\nNote: No valid image URL provided or URL format is incorrect."
    
    try:
        payload = {"embeds": [embed]}
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            logger.info("Test webhook sent successfully")
        else:
            logger.warning(f"Test webhook failed with status: {response.status_code}")
    except Exception as e:
        logger.error(f"Test webhook error: {e}")


def journal_entry(cmdr: str, is_beta: bool, system: str, station: str,
                  entry: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    
    event_type = entry.get("event")
    #integration is for EDSM configs
    integration_enabled = bool(config.get_bool(CONFIG_FUEL_MODE))          
    show_trit_on_cancel = bool(config.get_bool(CONFIG_SHOW_TRITIUM_CANCEL))

    # Grabs carrier info when management screen updated
    # update CarrierStats if *either* integration is on OR cancel-fuel is enabled
    if (integration_enabled or show_trit_on_cancel) and event_type == "CarrierStats": 
        update_carrier_state(entry)
        return None

    fuel_level, used_space, carrier_id = get_carrier_state()

    # logger.debug(f"Detected carrier callsign: {carrier_id}")

    if event_type not in ["CarrierJumpRequest", "CarrierJumpCancelled"] or is_beta:
        return None
    
    webhook_url = config.get_str(CONFIG_WEBHOOK) or ""
    if not webhook_url.startswith(
        ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
    ):
        logger.warning("Webhook URL not configured or invalid")
        return "FCDN: Configure Discord webhook URL in settings."
    
    if not config.get_str(CONFIG_CARRIER_NAME):
        logger.warning("Carrier Name not configured")
        return "FCDN: Configure Fleet Name in settings."
    
    # CRITICAL: Check if player is on their own carrier before processing
    on_own_carrier = is_player_on_their_carrier(state, carrier_id)
    logger.info(f"Processing {event_type} - Player on their carrier: {on_own_carrier}")
    
    image_url = config.get_str(CONFIG_IMAGE_URL) or ""
    
    # Log image URL status
    if image_url and not is_valid_url(image_url):
        logger.warning(f"Invalid image URL format (must start with http:// or https://): {image_url}")
    
    embed = create_discord_embed(cmdr, system, station, entry, fuel_level, used_space, carrier_id, image_url, on_own_carrier)
    
    try:
        logger.info(f"Sending {event_type} notification to Discord (on_own_carrier: {on_own_carrier})")
        response = requests.post(webhook_url, json={"embeds": [embed]}, timeout=30)
        if response.status_code in [200, 204]:
            logger.debug("Discord webhook sent successfully")
            return None
        else:
            logger.warning(f"Discord webhook failed with status: {response.status_code}")
            return "FCDN: Discord webhook error."
    except Exception as e:
        logger.error(f"Error sending to Discord: {e}")
        return "FCDN: Error sending to Discord."
