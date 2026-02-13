# -*- coding: utf-8 -*-
"""Responsive Circular Economy Dashboard (ManualDashboard6_2).

This module refactors the legacy dashboard into a DPI-aware, touch friendly
Tkinter application that scales from small tablets to desktop displays without
breaking existing business logic. The refactor keeps the public API surface of
``CircularControl`` and ``CircularEconomyDashboard`` compatible with previous
versions while introducing opt-in responsive behaviour for new layouts.
"""

from __future__ import annotations

import datetime
import math
import re
import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

import requests
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

try:
    import serial  # 需要: pip install pyserial
except ImportError:  # pragma: no cover - optional dependency
    serial = None

# ---------------------------------------------------------------------------
# Core constants and domain specific defaults (kept for compatibility)
# ---------------------------------------------------------------------------

REF_BRASS = 0.5   # kg per unit  0.8 → 0.5
REF_PLASTIC = 0.2  # kg per unit  0.02 → 0.2

YOUR_API_KEY = "46b6d9c5-1c8a-4dc0-bb0b-eaf380ec0f6a"

ENERGY_SOURCES = {
    "solar": {"co2": 50, "cost": 0.06},
    "wind": {"co2": 20, "cost": 0.05},
    "fossil": {"co2": 800, "cost": 0.14},
    "rest": {"co2": 100, "cost": 0.11},
}

STANDARD_ENERGY_MIX = {
    "solar": 0.13,
    "wind": 0.31,
    "fossil": 0.47,
    "rest": 0.09,
}

COMPONENT_COSTS = {
    "impeller": {"new": 0.20, "reman": 0.15, "reused": 0.10},
    "housing": {"new": 4.00, "reman": 3.00, "reused": 2.00},
}

ENERGY_CONSUMPTION = {
    "new": 20.0,
    "reman": 16.5,
    "reused": 14.0,
}

COLORS = {
    "bg_dark": "#0d1117",
    "bg_medium": "#1a1f2b",
    "bg_light": "#1e2532",
    "accent": "#00E0E0",
    "text": "#F1F1F1",
    "text_secondary": "#A0A0A0",
    "chart_bg": "#141926",
    "positive": "#4CAF50",
    "negative": "#E94560",
    "metric1": "#00BCD4",
    "metric2": "#FFC107",
    "metric3": "#8BC34A",
    "material1": "#FF5722",
    "material2": "#9C27B0",
}

# ---------------------------------------------------------------------------
# Responsive constants and helpers
# ---------------------------------------------------------------------------

# [RESPONSIVE] Minimum touch target size (px)
TOUCH_MIN_SIZE = 44

# [RESPONSIVE] DPI aware scaling defaults
DEFAULT_DPI = 96.0

# [RESPONSIVE] Breakpoints for layout modes (width + height)
BREAKPOINTS = {
    "SM": {"width": 900, "height": 700},
    "MD": {"width": 1200, "height": 900},
    "LG": {"width": 1600, "height": 1080},
}

# [RESPONSIVE] Font scaling table
FONT_SCALE = {
    "SM": 0.92,
    "MD": 1.0,
    "LG": 1.12,
}

# [RESPONSIVE] Dataclass to cache chart payloads for lazy redraw
@dataclass
class ChartPayload:
    args: Tuple
    kwargs: Dict


# ---------------------------------------------------------------------------
# Utility functions retained from the legacy module
# ---------------------------------------------------------------------------

def compute_avg_co2_from_energy_mix(factors: Dict[str, float]) -> float:
    """Return the average CO₂ intensity (kg/kWh) for a given energy mix."""

    return sum(ENERGY_SOURCES[src]["co2"] * factors[src] for src in factors) / 1000.0

def compute_avg_price_from_energy_mix(
    factors: Dict[str, float],
    use_realtime: bool = False,
    realtime_price: float = 0.0,
    price_source: str = "本地加权均值",
) -> float:
    """Return the average electricity price (€/kWh) for a given energy mix."""

    custom = sum(ENERGY_SOURCES[src]["cost"] * factors[src] for src in factors)
    if use_realtime and price_source != "本地加权均值":
        standard = sum(
            ENERGY_SOURCES[src]["cost"] * STANDARD_ENERGY_MIX[src]
            for src in STANDARD_ENERGY_MIX
        )
        return realtime_price + (custom - standard)
    return custom


class FuturisticStyle:
    """Apply futuristic styling to Tkinter widgets."""

    @staticmethod
    def configure_styles() -> None:
        style = ttk.Style()
        style.configure("TFrame", background=COLORS["bg_dark"])
        style.configure(
            "TLabel",
            background=COLORS["bg_dark"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Panel.TFrame",
            background=COLORS["bg_medium"],
            relief="flat",
        )
        style.configure(
            "Panel.TLabel",
            background=COLORS["bg_medium"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Title.TLabel",
            font=("Segoe UI", 18, "bold"),
            background=COLORS["bg_dark"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Subtitle.TLabel",
            font=("Segoe UI", 12, "bold"),
            background=COLORS["bg_medium"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Section.TLabel",
            font=("Segoe UI", 11, "bold"),
            background=COLORS["bg_medium"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Value.TLabel",
            font=("Segoe UI", 11, "bold"),
            background=COLORS["bg_medium"],
            foreground=COLORS["text"],
        )
        style.configure(
            "Accent.TLabel",
            font=("Segoe UI", 11, "bold"),
            background=COLORS["bg_medium"],
            foreground=COLORS["accent"],
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["bg_light"],
            foreground=COLORS["text"],
            font=("Segoe UI", 11, "bold"),
            borderwidth=0,
            padding=(14, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent"])],
            foreground=[("active", COLORS["bg_dark"])],
        )
        style.configure(
            "CyberDark.TButton",
            background=COLORS["bg_light"],
            foreground=COLORS["text"],
            font=("Segoe UI", 11, "bold"),
            borderwidth=0,
            padding=(12, 8),
        )
        style.map(
            "CyberDark.TButton",
            background=[("active", COLORS["accent"])],
            foreground=[("active", COLORS["bg_dark"])],
        )
        style.configure(
            "Responsive.Horizontal.TScale",
            background=COLORS["bg_medium"],
            troughcolor=COLORS["bg_light"],
            sliderthickness=TOUCH_MIN_SIZE,
            sliderlength=TOUCH_MIN_SIZE + 12,
        )
        style.configure(
            "TNotebook",
            background=COLORS["bg_dark"],
            tabposition="n",
        )
        style.configure(
            "TNotebook.Tab",
            background=COLORS["bg_medium"],
            foreground=COLORS["text"],
            padding=(16, 8),
            font=("Segoe UI", 11),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["bg_light"])],
            foreground=[("selected", COLORS["text"])],
        )


class CircularControl(tk.Canvas):
    """Circular control supporting responsive scaling."""

    def __init__(
        self,
        parent: tk.Widget,
        variable: tk.DoubleVar,
        label: str = "",
        radius: int = 50,
        callback=None,
        autosize: bool = False,
        min_radius: int = 36,
        max_radius: int = 64,
        **kwargs,
    ) -> None:
        self.radius = radius
        self._autosize = autosize
        self._min_radius = min_radius
        self._max_radius = max_radius
        self._scale_factor = 1.0
        self.variable = variable
        self.label = label
        self.callback = callback

        kwargs.setdefault("bg", COLORS["bg_medium"])
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)

        width = self._effective_radius * 2 + 20
        height = self._effective_radius * 2 + 48

        super().__init__(parent, width=width, height=height, **kwargs)

        self.track_color = "#2A3445"
        self.progress_color = COLORS["accent"]
        self.text_color = COLORS["text"]

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._draw_control()

    # [RESPONSIVE] property to compute radius based on scale factor
    @property
    def _effective_radius(self) -> int:
        radius = self.radius * self._scale_factor if self._autosize else self.radius
        return int(max(self._min_radius, min(self._max_radius, radius)))

    # [RESPONSIVE] API for layout manager to update scale factor
    def set_scale_factor(self, scale_factor: float) -> None:
        self._scale_factor = float(max(0.5, min(2.5, scale_factor)))
        width = self._effective_radius * 2 + TOUCH_MIN_SIZE // 2
        height = self._effective_radius * 2 + TOUCH_MIN_SIZE
        self.configure(width=width, height=height)
        self._draw_control()

    def _draw_control(self) -> None:
        self.delete("all")
        radius = self._effective_radius
        width = int(self["width"])
        height = int(self["height"])
        cx = width // 2
        cy = height // 2 - 12

        thickness = max(4, int(radius * 0.18))
        track_radius = radius - thickness // 2
        self.create_oval(
            cx - track_radius,
            cy - track_radius,
            cx + track_radius,
            cy + track_radius,
            outline=self.track_color,
            width=thickness,
            tags="track",
        )

        value = float(self.variable.get())
        extent_angle = -value * 3.6
        if abs(extent_angle) > 0.1:
            self.create_arc(
                cx - track_radius,
                cy - track_radius,
                cx + track_radius,
                cy + track_radius,
                start=90,
                extent=extent_angle,
                outline=self.progress_color,
                width=thickness,
                style="arc",
                tags="progress",
            )

        font_size = max(12, int(radius * 0.36))
        self.create_text(
            cx,
            cy,
            text=f"{int(value)}%",
            fill=self.text_color,
            font=("Segoe UI", font_size, "bold"),
            tags="value",
        )

        label_size = max(10, int(radius * 0.28))
        self.create_text(
            cx,
            height - 18,
            text=self.label,
            fill=self.text_color,
            font=("Segoe UI", label_size),
            tags="label",
        )

    def _on_press(self, event: tk.Event) -> None:
        self._update_value(event)

    def _on_drag(self, event: tk.Event) -> None:
        self._update_value(event)

    def _on_release(self, event: tk.Event) -> None:
        self._update_value(event)

    def _update_value(self, event: tk.Event) -> None:
        width = int(self["width"])
        height = int(self["height"])
        cx = width // 2
        cy = height // 2 - 12
        dx = event.x - cx
        dy = event.y - cy

        angle = (math.degrees(math.atan2(dy, dx)) - 90) % 360
        value = max(0, min(100, 100 - (angle / 360) * 100))

        old_value = self.variable.get()
        self.variable.set(round(value, 1))
        self._draw_control()
        if self.callback and abs(old_value - value) > 0.1:
            self.callback()


class AutoResizeCanvas(tk.Canvas):
    """Canvas that redraws itself when resized."""

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        kwargs.setdefault("bg", COLORS["chart_bg"])
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        super().__init__(parent, **kwargs)
        self._payload: Optional[ChartPayload] = None
        self._resize_job: Optional[str] = None
        self.bind("<Configure>", self._on_configure)

    def store_payload(self, *args, **kwargs) -> None:
        self._payload = ChartPayload(args=args, kwargs=kwargs)

    def _on_configure(self, _event: tk.Event) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(160, self._redraw_from_payload)

    def _redraw_from_payload(self) -> None:
        self._resize_job = None
        if self._payload is None:
            return
        self.delete("all")
        self.draw_grid()
        self.draw_content(*self._payload.args, **self._payload.kwargs)

    def draw_grid(self) -> None:  # pragma: no cover - to be implemented by subclasses
        pass

    def draw_content(self, *args, **kwargs) -> None:  # pragma: no cover
        pass


class ComparisonChart(AutoResizeCanvas):
    """Grouped bar chart for baseline vs current values."""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.baseline_color = COLORS["negative"]
        self.current_color = COLORS["metric1"]

    def draw_grid(self) -> None:
        width = self.winfo_width() or 400
        height = self.winfo_height() or 240
        margin_left, margin_right = 48, 24
        margin_top, margin_bottom = 24, 40
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        for i in range(5):
            y = margin_top + (chart_height / 4) * i
            self.create_line(
                margin_left,
                y,
                margin_left + chart_width,
                y,
                fill=COLORS["bg_light"],
                width=1,
                dash=(2, 6),
            )
        for i in range(6):
            x = margin_left + (chart_width / 5) * i
            self.create_line(
                x,
                margin_top,
                x,
                margin_top + chart_height,
                fill=COLORS["bg_light"],
                width=1,
                dash=(2, 6),
            )
        self.create_line(
            margin_left,
            margin_top + chart_height,
            margin_left + chart_width,
            margin_top + chart_height,
            fill=COLORS["text_secondary"],
            width=2,
        )
        self.create_line(
            margin_left,
            margin_top,
            margin_left,
            margin_top + chart_height,
            fill=COLORS["text_secondary"],
            width=2,
        )

    def update_chart(
        self,
        categories: Sequence[str],
        baseline_values: Sequence[float],
        current_values: Sequence[float],
        colors: Optional[Sequence[str]] = None,
        units: Optional[Sequence[str]] = None,
    ) -> None:
        self.store_payload(
            categories,
            baseline_values,
            current_values,
            colors,
            units,
        )
        self._redraw_from_payload()

    def draw_content(
        self,
        categories: Sequence[str],
        baseline_values: Sequence[float],
        current_values: Sequence[float],
        colors: Optional[Sequence[str]],
        units: Optional[Sequence[str]],
    ) -> None:
        if not categories:
            return
        width = self.winfo_width() or 400
        height = self.winfo_height() or 240
        margin_left, margin_right = 48, 24
        margin_top, margin_bottom = 24, 48
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom

        if colors and len(colors) >= 2:
            self.baseline_color = colors[0]
            self.current_color = colors[1]

        max_value = max(
            max(baseline_values) if baseline_values else 0,
            max(current_values) if current_values else 0,
            1,
        )
        num_categories = len(categories)
        group_width = chart_width / max(num_categories, 1)
        bar_width = group_width / 3

        for index, category in enumerate(categories):
            base = baseline_values[index]
            curr = current_values[index]
            unit = units[index] if units and index < len(units) else ""
            cx = margin_left + index * group_width + group_width / 2
            base_height = (base / max_value) * chart_height
            curr_height = (curr / max_value) * chart_height
            base_x0 = cx - bar_width
            base_x1 = base_x0 + bar_width * 0.8
            curr_x0 = cx + bar_width * 0.2
            curr_x1 = curr_x0 + bar_width * 0.8
            y_bottom = height - margin_bottom
            y_base = y_bottom - base_height
            y_curr = y_bottom - curr_height
            self.create_rectangle(
                base_x0,
                y_base,
                base_x1,
                y_bottom,
                fill=self.baseline_color,
                outline="",
                tags="bar",
            )
            self.create_rectangle(
                curr_x0,
                y_curr,
                curr_x1,
                y_bottom,
                fill=self.current_color,
                outline="",
                tags="bar",
            )
            self.create_text(
                cx,
                height - margin_bottom / 2,
                text=f"{category}{unit}",
                fill=COLORS["text"],
                anchor="center",
                font=("Segoe UI", 10),
            )
            self.create_text(
                (base_x0 + base_x1) / 2,
                y_base - 6,
                text=f"{base:.1f}",
                fill=COLORS["text_secondary"],
                font=("Segoe UI", 9),
            )
            self.create_text(
                (curr_x0 + curr_x1) / 2,
                y_curr - 6,
                text=f"{curr:.1f}",
                fill=COLORS["text"],
                font=("Segoe UI", 9),
            )

        self.create_text(
            margin_left - 6,
            margin_top,
            text=f"{max_value:.1f}",
            fill=COLORS["text_secondary"],
            anchor="e",
            font=("Segoe UI", 9),
        )
        self.create_text(
            margin_left - 6,
            height - margin_bottom,
            text="0",
            fill=COLORS["text_secondary"],
            anchor="e",
            font=("Segoe UI", 9),
        )


class RecordBarChart(AutoResizeCanvas):
    """Chart showing saved records."""

    def __init__(self, parent: tk.Widget, max_records: int = 3) -> None:
        super().__init__(parent)
        self.max_records = max_records
        self.records: List[Dict[str, float]] = []
        self.colors = {
            "energy": COLORS["metric1"],
            "co2": COLORS["metric3"],
            "cost": COLORS["metric2"],
            "brass": COLORS["material1"],
            "plastic": COLORS["material2"],
        }

    def draw_grid(self) -> None:
        width = self.winfo_width() or 520
        height = self.winfo_height() or 260
        margin_left, margin_right = 56, 24
        margin_top, margin_bottom = 24, 48
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        for i in range(5):
            y = margin_top + chart_height / 4 * i
            self.create_line(
                margin_left,
                y,
                margin_left + chart_width,
                y,
                fill=COLORS["bg_light"],
                width=1,
                dash=(2, 6),
            )
        self.create_line(
            margin_left,
            margin_top + chart_height,
            margin_left + chart_width,
            margin_top + chart_height,
            fill=COLORS["text_secondary"],
            width=2,
        )

    def draw_content(self, *_: Tuple) -> None:
        if not self.records:
            return
        width = self.winfo_width() or 520
        height = self.winfo_height() or 260
        margin_left, margin_right = 56, 24
        margin_top, margin_bottom = 24, 48
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        metrics = ["energy", "co2", "cost", "brass", "plastic"]
        max_value = max(
            max(record[metric] for metric in metrics) for record in self.records
        )
        if max_value <= 0:
            max_value = 1
        num_records = len(self.records)
        group_width = chart_width / max(num_records, 1)
        bar_width = group_width / (len(metrics) + 2)
        for idx, record in enumerate(self.records):
            cx = margin_left + idx * group_width + group_width / 2
            for j, metric in enumerate(metrics):
                value = record[metric]
                height_ratio = value / max_value
                bar_height = height_ratio * chart_height
                x0 = cx - (len(metrics) / 2) * bar_width + j * bar_width
                x1 = x0 + bar_width * 0.8
                y_bottom = height - margin_bottom
                y_top = y_bottom - bar_height
                self.create_rectangle(
                    x0,
                    y_top,
                    x1,
                    y_bottom,
                    fill=self.colors[metric],
                    outline="",
                    tags="bar",
                )
                self.create_text(
                    (x0 + x1) / 2,
                    y_top - 6,
                    text=f"{value:.1f}",
                    fill=COLORS["text"],
                    anchor="s",
                    font=("Segoe UI", 9),
                )
            self.create_text(
                cx,
                height - margin_bottom / 2,
                text=record["label"],
                fill=COLORS["text_secondary"],
                anchor="center",
                font=("Segoe UI", 10),
            )
        self.create_text(
            margin_left - 6,
            margin_top,
            text=f"{max_value:.1f}",
            fill=COLORS["text_secondary"],
            anchor="e",
            font=("Segoe UI", 9),
        )
        self.create_text(
            margin_left - 6,
            height - margin_bottom,
            text="0",
            fill=COLORS["text_secondary"],
            anchor="e",
            font=("Segoe UI", 9),
        )

    def add_record(self, record: Dict[str, float]) -> None:
        if len(self.records) >= self.max_records:
            self.records.pop(0)
        self.records.append(record)
        self.store_payload()
        self._redraw_from_payload()

    def clear_records(self) -> None:
        self.records.clear()
        self.store_payload()
        self._redraw_from_payload()


# [RESPONSIVE] layout mode helper prioritising orientation

def layout_mode(width: int, height: int) -> str:
    landscape = width >= height
    if landscape:
        if height < BREAKPOINTS["SM"]["height"] or width < BREAKPOINTS["SM"]["width"]:
            return "L_SM"
        if height < BREAKPOINTS["MD"]["height"] or width < BREAKPOINTS["MD"]["width"]:
            return "L_MD"
        return "L_LG"
    if height < BREAKPOINTS["SM"]["height"] or width < BREAKPOINTS["SM"]["width"]:
        return "P_SM"
    if height < BREAKPOINTS["MD"]["height"] or width < BREAKPOINTS["MD"]["width"]:
        return "P_MD"
    return "P_LG"


class CircularEconomyDashboard:
    """Responsive dashboard coordinating widgets and business logic."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Circular Economy Dashboard")
        self.root.configure(bg=COLORS["bg_dark"])

        self._install_scaling()
        FuturisticStyle.configure_styles()

        default_energy = ENERGY_CONSUMPTION["new"]
        default_cost = (
            COMPONENT_COSTS["housing"]["new"]
            + COMPONENT_COSTS["impeller"]["new"]
        )
        default_energy_cost = default_energy * ENERGY_SOURCES["fossil"]["cost"]

        self.energy_baseline = tk.DoubleVar(value=default_energy)
        self.co2_baseline = tk.DoubleVar(value=9.0)
        self.brass_baseline = tk.DoubleVar(value=REF_BRASS)
        self.plastic_baseline = tk.DoubleVar(value=REF_PLASTIC)
        self.cost_baseline = tk.DoubleVar(value=default_cost)
        self.energy_cost_baseline = tk.DoubleVar(value=default_energy_cost)

        self.energy_current = tk.DoubleVar(value=default_energy)
        self.co2_current = tk.DoubleVar(value=9.0)
        self.brass_current = tk.DoubleVar(value=REF_BRASS)
        self.plastic_current = tk.DoubleVar(value=REF_PLASTIC)
        self.cost_current = tk.DoubleVar(value=default_cost)
        self.energy_cost_current = tk.DoubleVar(value=default_energy_cost)

        self.meter_reuse_pct = tk.DoubleVar(value=0.0)
        self.reman_impeller_pct = tk.DoubleVar(value=0.0)
        self.reman_housing_pct = tk.DoubleVar(value=0.0)
        self.recycle_impeller_pct = tk.DoubleVar(value=0.0)
        self.recycle_housing_pct = tk.DoubleVar(value=0.0)
        self.solar_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["solar"] * 100))
        self.wind_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["wind"] * 100))
        self.fossil_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["fossil"] * 100))
        self.rest_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["rest"] * 100))
        self.use_realtime_price = tk.BooleanVar(value=False)
        self.realtime_price = tk.DoubleVar(value=0.15)
        self.price_source = tk.StringVar(value="本地加权均值")

        self.energy_mix_display = tk.StringVar()
        self.price_display = tk.StringVar()

        self.factors = {
            "solar": STANDARD_ENERGY_MIX["solar"],
            "wind": STANDARD_ENERGY_MIX["wind"],
            "fossil": STANDARD_ENERGY_MIX["fossil"],
            "rest": STANDARD_ENERGY_MIX["rest"],
        }

        self.current_layout: Optional[str] = None
        self._resize_job: Optional[str] = None
        self._minimal_mode = False

        self._solar_state = "A"
        self._wind_state = "STOPPED"
        self._manual_lock = False
        self._auto_ramping = False
        self._solar_target = self.solar_pct.get()
        self._ramp_up_sec = 15
        self._ramp_dn_sec = 12
        self._ramp_interval_ms = 320
        self._auto_updating = False
        self._wind_manual_lock = False
        self._wind_auto_ramping = False
        self._wind_auto_updating = False
        self._wind_target = self.wind_pct.get()
        self._wind_ramp_up_sec = 18

        self._build_structure()
        self.calculate_and_update()
        self._ramp_tick()
        self.root.bind("<Configure>", self._on_root_resize)

    # [RESPONSIVE] DPI + maximise setup
    def _install_scaling(self) -> None:
        try:
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
            except tk.TclError:
                w = self.root.winfo_screenwidth()
                h = self.root.winfo_screenheight()
                self.root.geometry(f"{int(w * 0.99)}x{int(h * 0.98)}+0+0")
        scale = 1.0
        try:  # pragma: no cover - platform specific
            import sys
            import ctypes

            if sys.platform.startswith("win"):
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            dpi = self.root.winfo_fpixels("1i")
            scale = max(1.0, dpi / DEFAULT_DPI)
        except Exception:
            pass
        if abs(scale - 1.0) > 0.15:
            self.root.call("tk", "scaling", scale)
        self.root.minsize(980, 650)

    def _build_structure(self) -> None:
        # [RESPONSIVE] 构建弹性布局骨架
        self.main_container = ttk.Frame(self.root)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.header_frame = ttk.Frame(self.main_container)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))

        ttk.Label(
            self.header_frame,
            text="Circular Economy Dashboard",
            style="Title.TLabel",
        ).grid(row=0, column=0, sticky="w")

        self.mode_badge = ttk.Label(
            self.header_frame,
            text="",
            style="Accent.TLabel",
        )
        self.mode_badge.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.view_notebook = ttk.Notebook(self.main_container)
        self.view_notebook.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.main_container.grid_rowconfigure(2, weight=1)

        self.core_view = ttk.Frame(self.view_notebook, style="Panel.TFrame")
        self.input_view = ttk.Frame(self.view_notebook, style="Panel.TFrame")
        self.visual_view = ttk.Frame(self.view_notebook, style="Panel.TFrame")
        self.records_view = ttk.Frame(self.view_notebook, style="Panel.TFrame")

        self.view_notebook.add(self.core_view, text="核心视图")
        self.view_notebook.add(self.input_view, text="输入设置")
        self.view_notebook.add(self.visual_view, text="图表")
        self.view_notebook.add(self.records_view, text="记录")

        self.core_view.grid_rowconfigure(1, weight=1)
        self.core_view.grid_columnconfigure(0, weight=1)
        self.core_view.grid_columnconfigure(1, weight=1)

        self._build_kpi_panel(self.core_view)
        self._build_energy_mix_summary(self.core_view)
        self._build_primary_chart(self.visual_view)
        self._build_material_chart(self.visual_view)
        self._build_records_panel(self.records_view)
        self._build_inputs(self.input_view)

    def _build_kpi_panel(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] KPI 面板随断点自适应列宽
        self.kpi_panel = ttk.Frame(parent, style="Panel.TFrame")
        self.kpi_panel.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=18)
        for i in range(3):
            self.kpi_panel.grid_columnconfigure(i, weight=1)
        self._kpi_widgets = []
        items = [
            ("能源 (kWh)", self.energy_current, self.energy_baseline),
            ("CO₂ (kg)", self.co2_current, self.co2_baseline),
            ("成本 (€)", self.cost_current, self.cost_baseline),
        ]
        for column, (label, current, baseline) in enumerate(items):
            frame = ttk.Frame(self.kpi_panel, style="Panel.TFrame")
            frame.grid(row=0, column=column, sticky="nsew", padx=12, pady=12)
            ttk.Label(frame, text=label, style="Section.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            value_label = ttk.Label(
                frame,
                textvariable=tk.StringVar(),
                style="Value.TLabel",
            )
            value_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
            delta_label = ttk.Label(
                frame,
                text="",
                style="Accent.TLabel",
            )
            delta_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
            self._kpi_widgets.append((label, value_label, delta_label, current, baseline))

    def _build_energy_mix_summary(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 能源总结在不同模式下自动换行
        self.mix_panel = ttk.Frame(parent, style="Panel.TFrame")
        self.mix_panel.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=18, pady=(0, 18))
        self.mix_panel.grid_columnconfigure(0, weight=1)
        ttk.Label(
            self.mix_panel,
            text="能源构成",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        self.mix_value_label = ttk.Label(
            self.mix_panel,
            textvariable=self.energy_mix_display,
            style="Value.TLabel",
        )
        self.mix_value_label.grid(row=1, column=0, sticky="w", padx=12)
        self.price_value_label = ttk.Label(
            self.mix_panel,
            textvariable=self.price_display,
            style="Value.TLabel",
        )
        self.price_value_label.grid(row=2, column=0, sticky="w", padx=12, pady=(4, 12))

    def _build_primary_chart(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 主要图表绑定自动重绘
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="能源与成本", style="Subtitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 12)
        )
        self.energy_chart = ComparisonChart(parent)
        self.energy_chart.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))

    def _build_material_chart(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 材料图表在断点切换时更新
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="材料消耗", style="Subtitle.TLabel").grid(
            row=2, column=0, sticky="w", padx=18, pady=(0, 12)
        )
        self.material_chart = ComparisonChart(parent)
        self.material_chart.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))

    def _build_records_panel(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 记录面板支持触控按钮
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="场景对比", style="Subtitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 12)
        )
        button_frame = ttk.Frame(parent, style="Panel.TFrame")
        button_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        ttk.Button(
            button_frame,
            text="保存当前场景",
            command=self.save_record,
            style="CyberDark.TButton",
        ).grid(row=0, column=0, padx=(0, 12))
        ttk.Button(
            button_frame,
            text="清空记录",
            command=self.clear_records,
            style="CyberDark.TButton",
        ).grid(row=0, column=1)
        button_frame.grid_columnconfigure(2, weight=1)
        self.records_chart = RecordBarChart(parent)
        self.records_chart.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))

    def _build_inputs(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 输入面板采用网格布局便于缩放
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text="输入参数", style="Subtitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=18, pady=(18, 12)
        )

        self.control_frame = ttk.Frame(parent, style="Panel.TFrame")
        self.control_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        for idx in range(3):
            self.control_frame.grid_columnconfigure(idx, weight=1)
        self.circular_controls: List[CircularControl] = []

        def add_control(row: int, column: int, var: tk.DoubleVar, text: str) -> None:
            frame = ttk.Frame(self.control_frame, style="Panel.TFrame")
            frame.grid(row=row, column=column, sticky="nsew", padx=12, pady=12)
            control = CircularControl(
                frame,
                var,
                label=text,
                radius=48,
                callback=self.calculate_and_update,
                autosize=True,
            )
            control.grid(row=0, column=0, padx=12, pady=12)
            self.circular_controls.append(control)

        add_control(0, 0, self.meter_reuse_pct, "整表复用")
        add_control(0, 1, self.reman_impeller_pct, "叶轮再制造")
        add_control(0, 2, self.reman_housing_pct, "壳体再制造")
        add_control(1, 0, self.recycle_impeller_pct, "叶轮回收")
        add_control(1, 1, self.recycle_housing_pct, "壳体回收")

        self._build_energy_mix_controls(parent)

    def _build_energy_mix_controls(self, parent: tk.Widget) -> None:
        # [RESPONSIVE] 能源滑块满足触控目标尺寸
        mix_card = ttk.Frame(parent, style="Panel.TFrame")
        mix_card.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        mix_card.grid_columnconfigure(1, weight=1)
        ttk.Label(mix_card, text="能源构成", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 8)
        )
        ttk.Checkbutton(
            mix_card,
            text="使用实时电价",
            variable=self.use_realtime_price,
            command=self.on_realtime_price_toggle,
        ).grid(row=0, column=1, sticky="e", padx=12, pady=(12, 8))
        ttk.Label(mix_card, text="实时电价 €/kWh", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=12
        )
        self.realtime_price_entry = ttk.Entry(
            mix_card,
            textvariable=self.realtime_price,
            width=6,
        )
        self.realtime_price_entry.grid(row=1, column=1, sticky="e", padx=12)
        self.realtime_price_entry.configure(state="disabled")

        slider_specs = [
            ("solar", "太阳能"),
            ("wind", "风能"),
            ("fossil", "化石"),
            ("rest", "其他"),
        ]
        for index, (key, label) in enumerate(slider_specs, start=2):
            row_frame = ttk.Frame(mix_card, style="Panel.TFrame")
            row_frame.grid(row=index, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
            row_frame.grid_columnconfigure(1, weight=1)
            ttk.Label(row_frame, text=f"{label} (%)", style="Value.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            var = getattr(self, f"{key}_pct")
            scale = ttk.Scale(
                row_frame,
                from_=0,
                to=100,
                orient="horizontal",
                variable=var,
                command=lambda value, name=key: self.on_slider_change(name, float(value)),
                style="Responsive.Horizontal.TScale",
            )
            scale.grid(row=0, column=1, sticky="ew", padx=12)
            value_label = ttk.Label(row_frame, text=f"{var.get():.0f}%", style="Value.TLabel")
            value_label.grid(row=0, column=2, padx=(12, 0))
            setattr(self, f"{key}_val_label", value_label)

        self.energy_sum_label = ttk.Label(mix_card, text="合计: 100%", style="Value.TLabel")
        self.energy_sum_label.grid(row=6, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 12))

    def _on_root_resize(self, event: tk.Event) -> None:
        # [RESPONSIVE] 窗口尺寸去抖处理
        if event.widget is not self.root:
            return
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(180, self._apply_layout)

    def _apply_layout(self) -> None:
        # [RESPONSIVE] 根据断点和极简模式重排布局
        self._resize_job = None
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        mode = layout_mode(width, height)
        minimal_trigger = min(width, height) < 650
        self._minimal_mode = minimal_trigger
        if mode == self.current_layout and not minimal_trigger:
            self._update_font_scale(mode)
            return
        self.current_layout = mode
        self._update_font_scale(mode)
        badge = mode.replace("_", " ")
        if self._minimal_mode:
            badge += " · 极简"
        self.mode_badge.configure(text=badge)

        if self._minimal_mode:
            self.view_notebook.select(self.core_view)
            for tab in self.view_notebook.tabs()[1:]:
                self.view_notebook.tab(tab, state="hidden")
        else:
            for tab in self.view_notebook.tabs():
                self.view_notebook.tab(tab, state="normal")

        if mode.startswith("L") and not self._minimal_mode:
            self.view_notebook.grid_remove()
            if not hasattr(self, "landscape_frame"):
                self.landscape_frame = ttk.Frame(self.main_container)
            self.landscape_frame.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))
            self.main_container.grid_rowconfigure(2, weight=1)
            self.landscape_frame.grid_rowconfigure(0, weight=1)
            self.landscape_frame.grid_columnconfigure(0, weight=1)
            self.landscape_frame.grid_columnconfigure(1, weight=1)
            self._show_landscape_columns(mode)
        else:
            if hasattr(self, "landscape_frame"):
                for child in self.landscape_frame.grid_slaves():
                    child.grid_forget()
                self.landscape_frame.grid_forget()
            self.view_notebook.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))

    def _show_landscape_columns(self, mode: str) -> None:
        # [RESPONSIVE] 横屏模式下的列布局策略
        self.core_view.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 18))
        self.input_view.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        self.visual_view.grid(row=1, column=1, sticky="nsew", padx=(12, 0))
        if mode == "L_LG":
            self.records_view.grid(row=2, column=1, sticky="nsew", pady=(18, 0))
            self.landscape_frame.grid_rowconfigure(2, weight=1)
        else:
            self.records_view.grid(row=2, column=1, sticky="ew", pady=(18, 0))
            self.landscape_frame.grid_rowconfigure(2, weight=0)
        self.landscape_frame.grid_rowconfigure(1, weight=1)

        scale_factor = 1.0 if mode == "L_LG" else 0.9
        for control in self.circular_controls:
            control.set_scale_factor(scale_factor)

    def _update_font_scale(self, mode: str) -> None:
        # [RESPONSIVE] 不同断点对应字体缩放
        size_key = "LG" if mode.endswith("LG") else ("MD" if mode.endswith("MD") else "SM")
        factor = FONT_SCALE[size_key]
        ttk.Style().configure("TLabel", font=("Segoe UI", int(10 * factor)))

    def update_kpis(self) -> None:
        # [RESPONSIVE] KPI 文本颜色与箭头按实时数据调整
        for label, value_label, delta_label, current_var, baseline_var in self._kpi_widgets:
            current = current_var.get()
            baseline = baseline_var.get()
            delta = current - baseline
            value_label.configure(text=f"{current:.2f}")
            if delta > 0:
                sign = "↑"
                color = COLORS["negative"]
            elif delta < 0:
                sign = "↓"
                color = COLORS["positive"]
            else:
                sign = "→"
                color = COLORS["text_secondary"]
            delta_label.configure(text=f"{sign} {delta:.2f} vs baseline", foreground=color)

    def update_energy_mix(self, *_: Iterable) -> None:
        # [RESPONSIVE] 能源构成随滑块实时更新
        s = self.solar_pct.get()
        w = self.wind_pct.get()
        f = self.fossil_pct.get()
        r = self.rest_pct.get()
        total = s + w + f + r
        if total <= 0:
            self.factors = {"solar": 0.0, "wind": 0.0, "fossil": 1.0, "rest": 0.0}
        else:
            self.factors = {
                "solar": s / total,
                "wind": w / total,
                "fossil": f / total,
                "rest": r / total,
            }
        for key in ("solar", "wind", "fossil", "rest"):
            label = getattr(self, f"{key}_val_label")
            label.configure(text=f"{getattr(self, f'{key}_pct').get():.0f}%")
        if abs(total - 100) > 0.5:
            self.energy_sum_label.configure(
                text=f"合计: {total:.0f}% (请调整)",
                foreground=COLORS["negative"],
            )
        else:
            self.energy_sum_label.configure(
                text=f"合计: {total:.0f}%",
                foreground=COLORS["positive"],
            )
        self.energy_mix_display.set(
            f"太阳能 {s:.0f}%, 风能 {w:.0f}%, 化石 {f:.0f}%, 其他 {r:.0f}%"
        )
        self.update_price_display()
        self.calculate_and_update()

    def update_price_display(self) -> None:
        try:
            cost = compute_avg_price_from_energy_mix(
                self.factors,
                use_realtime=self.use_realtime_price.get(),
                realtime_price=self.realtime_price.get(),
                price_source=self.price_source.get(),
            )
            source = (
                self.price_source.get()
                if self.use_realtime_price.get() and self.price_source.get() != "本地加权均值"
                else "本地加权均值"
            )
            self.price_display.set(f"当前电价: {cost:.2f} €/kWh (来源: {source})")
        except Exception as exc:  # pragma: no cover - defensive
            print("更新电价显示时出错:", exc)
            self.price_display.set(f"当前电价: {self.realtime_price.get():.2f} €/kWh")

    def on_slider_change(self, changed: str, value: float) -> None:
        # [RESPONSIVE] 断点式能源配比调整
        sources = ["solar", "wind", "fossil", "rest"]
        values = {key: getattr(self, f"{key}_pct").get() for key in sources}
        values[changed] = value
        total = sum(values.values())
        if total > 100:
            others = [s for s in sources if s != changed]
            other_sum = sum(values[o] for o in others)
            if other_sum == 0:
                for o in others:
                    values[o] = 0
                values[changed] = 100
            else:
                excess = total - 100
                for o in others:
                    reduction = excess * (values[o] / other_sum)
                    values[o] = max(0, values[o] - reduction)
        for key in sources:
            getattr(self, f"{key}_pct").set(values[key])
        self.update_energy_mix()

    def on_realtime_price_toggle(self) -> None:
        # [RESPONSIVE] 实时电价切换保持兼容
        if self.use_realtime_price.get():
            self.realtime_price_entry.configure(state="normal")
            self.fetch_realtime_price()
        else:
            self.realtime_price_entry.configure(state="disabled")
            self.price_source.set("本地加权均值")
            self.update_price_display()
        self.calculate_and_update()

    def compute_avg_cost(self, factors: Dict[str, float]) -> float:
        return compute_avg_price_from_energy_mix(
            factors,
            use_realtime=self.use_realtime_price.get(),
            realtime_price=self.realtime_price.get(),
            price_source=self.price_source.get(),
        )

    def calculate_metrics(
        self,
        meter_reuse_pct: float,
        reman_housing_pct: float,
        reman_impeller_pct: float,
        recycle_housing_pct: float,
        recycle_impeller_pct: float,
        factors: Dict[str, float],
    ) -> Dict[str, float]:
        meter_reuse_pct = float(meter_reuse_pct)
        reman_housing_pct = float(reman_housing_pct)
        reman_impeller_pct = float(reman_impeller_pct)
        recycle_housing_pct = float(recycle_housing_pct)
        recycle_impeller_pct = float(recycle_impeller_pct)

        R_meter = meter_reuse_pct / 100.0
        R_rem_h = reman_housing_pct / 100.0
        R_rem_i = reman_impeller_pct / 100.0
        R_rec_h = recycle_housing_pct / 100.0
        R_rec_i = recycle_impeller_pct / 100.0

        Q_whole = R_meter
        Q_rem_housing = (1 - R_meter) * R_rem_h
        Q_rem_impeller = (1 - R_meter) * R_rem_i
        Q_new_housing = (1.0 - R_meter) * (1.0 - R_rem_h)
        Q_new_impeller = (1.0 - R_meter) * (1.0 - R_rem_i)

        Q_sec_brass = (1 - R_meter) * (1 - R_rem_h) * R_rec_h
        Q_sec_plastic = (1 - R_meter) * (1 - R_rem_i) * R_rec_i

        share_sec_housing = 0.0 if Q_new_housing <= 1e-12 else R_rec_h
        share_sec_impeller = 0.0 if Q_new_impeller <= 1e-12 else R_rec_i

        virgin_brass = REF_BRASS * Q_new_housing * (1 - share_sec_housing)
        secondary_brass = REF_BRASS * Q_new_housing * share_sec_housing
        virgin_plastic = REF_PLASTIC * Q_new_impeller * (1 - share_sec_impeller)
        secondary_plastic = REF_PLASTIC * Q_new_impeller * share_sec_impeller

        brass_kg = virgin_brass + secondary_brass
        plastic_kg = virgin_plastic + secondary_plastic

        housing_new = COMPONENT_COSTS["housing"]["new"]
        impeller_new = COMPONENT_COSTS["impeller"]["new"]
        w_h = housing_new / (housing_new + impeller_new)
        w_i = 1.0 - w_h

        energy_kwh = (
            Q_whole * ENERGY_CONSUMPTION["reused"]
            + (1 - R_meter)
            * (
                w_h
                * (
                    R_rem_h * ENERGY_CONSUMPTION["reman"]
                    + (1 - R_rem_h) * ENERGY_CONSUMPTION["new"]
                )
                + w_i
                * (
                    R_rem_i * ENERGY_CONSUMPTION["reman"]
                    + (1 - R_rem_i) * ENERGY_CONSUMPTION["new"]
                )
            )
        )

        C_h_new = COMPONENT_COSTS["housing"]["new"]
        C_h_reman = COMPONENT_COSTS["housing"]["reman"]
        C_h_reused = COMPONENT_COSTS["housing"]["reused"]
        C_i_new = COMPONENT_COSTS["impeller"]["new"]
        C_i_reman = COMPONENT_COSTS["impeller"]["reman"]
        C_i_reused = COMPONENT_COSTS["impeller"]["reused"]

        cost_housing = Q_whole * C_h_reused + (1 - R_meter) * (
            R_rem_h * C_h_reman + (1 - R_rem_h) * C_h_new
        )
        cost_impeller = Q_whole * C_i_reused + (1 - R_meter) * (
            R_rem_i * C_i_reman + (1 - R_rem_i) * C_i_new
        )

        component_cost_eur = cost_housing + cost_impeller

        avg_co2_kg_per_kwh = compute_avg_co2_from_energy_mix(factors)
        avg_price_eur_per_kwh = compute_avg_price_from_energy_mix(
            factors,
            use_realtime=self.use_realtime_price.get(),
            realtime_price=self.realtime_price.get(),
            price_source=self.price_source.get(),
        )

        total_material = brass_kg + plastic_kg
        secondary_share = (
            0.0
            if total_material <= 1e-9
            else (secondary_brass + secondary_plastic) / total_material
        )

        co2_kg = energy_kwh * avg_co2_kg_per_kwh * (1 - 0.5 * secondary_share)
        energy_cost_eur = energy_kwh * avg_price_eur_per_kwh
        total_cost_for_plot = component_cost_eur + energy_cost_eur

        return {
            "energy": energy_kwh,
            "energy_cost": energy_cost_eur,
            "co2": co2_kg,
            "brass": brass_kg,
            "plastic": plastic_kg,
            "component_cost": component_cost_eur,
            "total_cost": total_cost_for_plot,
        }

    def calculate_and_update(self) -> None:
        # [RESPONSIVE] 统一触发所有可视组件刷新
        try:
            meter_reuse = float(self.meter_reuse_pct.get())
            reman_impeller = float(self.reman_impeller_pct.get())
            reman_housing = float(self.reman_housing_pct.get())
            recycle_impeller = float(self.recycle_impeller_pct.get())
            recycle_housing = float(self.recycle_housing_pct.get())

            baseline_factors = {"solar": 0.0, "wind": 0.0, "fossil": 1.0, "rest": 0.0}
            baseline_metrics = self.calculate_metrics(0, 0, 0, 0, 0, baseline_factors)

            current_metrics = self.calculate_metrics(
                meter_reuse,
                reman_housing,
                reman_impeller,
                recycle_housing,
                recycle_impeller,
                self.factors,
            )

            self.energy_current.set(current_metrics["energy"])
            self.co2_current.set(current_metrics["co2"])
            self.cost_current.set(current_metrics["total_cost"])
            self.energy_cost_current.set(current_metrics["energy_cost"])
            self.brass_current.set(current_metrics["brass"])
            self.plastic_current.set(current_metrics["plastic"])

            self.energy_baseline.set(baseline_metrics["energy"])
            self.co2_baseline.set(baseline_metrics["co2"])
            self.cost_baseline.set(baseline_metrics["total_cost"])
            self.energy_cost_baseline.set(baseline_metrics["energy_cost"])
            self.brass_baseline.set(baseline_metrics["brass"])
            self.plastic_baseline.set(baseline_metrics["plastic"])

            self.update_kpis()

            self.energy_chart.update_chart(
                ["能源", "能源成本"],
                [
                    self.energy_baseline.get(),
                    self.energy_cost_baseline.get(),
                ],
                [
                    self.energy_current.get(),
                    self.energy_cost_current.get(),
                ],
                colors=[COLORS["negative"], COLORS["metric1"]],
                units=["", ""],
            )

            self.material_chart.update_chart(
                ["铜", "塑料"],
                [
                    self.brass_baseline.get(),
                    self.plastic_baseline.get(),
                ],
                [
                    self.brass_current.get(),
                    self.plastic_current.get(),
                ],
                colors=[COLORS["material1"], COLORS["material2"]],
                units=[" kg", " kg"],
            )
        except Exception as exc:  # pragma: no cover - UI resilience
            print("计算更新失败:", exc)

    def save_record(self) -> None:
        # [RESPONSIVE] 保存记录触发懒加载图表
        record = {
            "label": datetime.datetime.now().strftime("%H:%M"),
            "meter_reuse": self.meter_reuse_pct.get(),
            "reman_impeller": self.reman_impeller_pct.get(),
            "reman_housing": self.reman_housing_pct.get(),
            "recycle_impeller": self.recycle_impeller_pct.get(),
            "recycle_housing": self.recycle_housing_pct.get(),
            "energy": self.energy_current.get(),
            "co2": self.co2_current.get(),
            "brass": self.brass_current.get(),
            "plastic": self.plastic_current.get(),
            "cost": self.cost_current.get(),
        }
        self.records_chart.add_record(record)

    def clear_records(self) -> None:
        self.records_chart.clear_records()

    def fetch_realtime_price(self) -> None:
        # [RESPONSIVE] 网络失败自动回退本地价格
        try:
            berlin = ZoneInfo("Europe/Berlin")
            today_local = datetime.datetime.now(berlin).date()
            yesterday = today_local - datetime.timedelta(days=1)

            local_start = datetime.datetime.combine(
                yesterday,
                datetime.time(0, 0),
                tzinfo=berlin,
            )
            local_end = datetime.datetime.combine(
                yesterday + datetime.timedelta(days=1),
                datetime.time(0, 0),
                tzinfo=berlin,
            )

            utc = ZoneInfo("UTC")
            start_utc = local_start.astimezone(utc)
            end_utc = local_end.astimezone(utc)

            params = {
                "securityToken": YOUR_API_KEY,
                "documentType": "A44",
                "in_Domain": "10Y1001A1001A82H",
                "out_Domain": "10Y1001A1001A82H",
                "periodStart": start_utc.strftime("%Y%m%d%H%M"),
                "periodEnd": end_utc.strftime("%Y%m%d%H%M"),
            }
            resp = requests.get(
                "https://web-api.tp.entsoe.eu/api",
                params=params,
                headers={"Accept": "application/xml"},
                timeout=10,
            )
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            m = re.match(r"\{(.+)\}", root.tag)
            ns = {"ns": m.group(1)} if m else {}

            if root.tag.endswith("Acknowledgement_MarketDocument"):
                txt = root.find(".//ns:text", ns)
                reason = txt.text if txt is not None else "无详细原因"
                raise RuntimeError(f"ENTSO‑E 响应：{reason}")

            points = root.findall(".//ns:Point", ns)
            prices = []
            for pt in points:
                pe = pt.find("ns:price.amount", ns)
                if pe is not None and pe.text:
                    prices.append(float(pe.text))
            if not prices:
                raise RuntimeError("解析后无任何价格点")

            avg_mwh = sum(prices) / len(prices)
            avg_kwh = avg_mwh / 1000.0
            self.realtime_price.set(avg_kwh)
            self.price_source.set("ENTSO‑E 日平均")
        except Exception as err:  # pragma: no cover - network resilience
            self.price_source.set("本地加权均值")
            print("获取实时电价失败:", err)
        finally:
            if self.use_realtime_price.get():
                self.update_price_display()
            self.root.after(3600_000, self.fetch_realtime_price)

    def _start_serial(self, port_hint: str = "COM3", baud: int = 9600) -> None:
        # [RESPONSIVE] 串口线程在新布局下保持工作
        self._serial_stop = False
        if serial is None:
            print("pyserial 未安装，串口功能禁用")
            return

        def worker() -> None:
            ports_to_try = [
                port_hint,
                "COM4",
                "COM5",
                "/dev/ttyUSB0",
                "/dev/ttyACM0",
                "/dev/tty.usbserial-1410",
            ]
            ser = None
            for port in ports_to_try:
                if not port:
                    continue
                try:
                    ser = serial.Serial(port, baudrate=baud, timeout=1)
                    ser.reset_input_buffer()
                    print(f"串口连接成功: {port}")
                    break
                except Exception:
                    continue
            if ser is None:
                print("未能连接到任何串口")
                return

            pat = re.compile(
                r"raw\s*=\s*(\d+(?:\.\d+)?)\s*,\s*base\s*=\s*(\d+(?:\.\d+)?)\s*,\s*state\s*=\s*([ALB])",
                re.I,
            )
            pat_wind = re.compile(r"\[(SPINNING|STOPPED)\]", re.I)
            while not self._serial_stop:
                try:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    match = pat.search(line)
                    if match:
                        state = match.group(3).upper()
                        self._process_arduino_state(state)
                        continue
                    match_wind = pat_wind.search(line)
                    if match_wind:
                        wind_state = match_wind.group(1).upper()
                        self._process_wind_state(wind_state)
                        continue
                except Exception as exc:
                    print("串口读取异常：", exc)
                    time.sleep(0.2)
            try:
                ser.close()
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _process_arduino_state(self, new_state: str) -> None:
        # [RESPONSIVE] 自动推进与手动锁配合
        old_state = getattr(self, "_solar_state", "A")
        self._solar_state = new_state
        if old_state != new_state:
            print(f"Arduino状态变化: {old_state} -> {new_state}")
            if new_state == "L":
                self._manual_lock = False
                self._solar_target = 100.0
                self._auto_ramping = True
            elif new_state == "B":
                self._manual_lock = False
                self._solar_target = 0.0
                self._auto_ramping = True
            else:
                if old_state in ["L", "B"]:
                    self._auto_ramping = False
                    self._solar_target = float(self.solar_pct.get())

    def _process_wind_state(self, new_state: str) -> None:
        # [RESPONSIVE] 风能推进的断点兼容
        normalized = (new_state or "").upper()
        old_state = getattr(self, "_wind_state", "STOPPED")
        self._wind_state = normalized
        if old_state != normalized:
            print(f"Wind状态变化: {old_state} -> {normalized}")
        if normalized == "SPINNING":
            self._wind_manual_lock = False
            self._wind_target = 100.0
            self._wind_auto_ramping = True
        elif normalized == "STOPPED":
            self._wind_auto_ramping = False
            self._wind_target = float(self.wind_pct.get())

    def _ramp_tick(self) -> None:
        # [RESPONSIVE] 自动推进去抖
        try:
            solar_changed = False
            wind_changed = False

            current_value = float(self.solar_pct.get())
            if self._auto_ramping and not self._manual_lock:
                target = float(self._solar_target)
                tolerance = 0.5
                if abs(current_value - target) > tolerance:
                    if target > current_value:
                        step_per_sec = 100.0 / max(0.1, self._ramp_up_sec)
                        step = step_per_sec * (self._ramp_interval_ms / 1000.0)
                        new_val = min(target, current_value + step)
                    else:
                        step_per_sec = 100.0 / max(0.1, self._ramp_dn_sec)
                        step = step_per_sec * (self._ramp_interval_ms / 1000.0)
                        new_val = max(target, current_value - step)
                    self._auto_updating = True
                    try:
                        self.solar_pct.set(new_val)
                        self.solar_val_label.configure(text=f"{new_val:.0f}%")
                    finally:
                        self._auto_updating = False
                    solar_changed = True
                else:
                    if self._auto_ramping:
                        self._auto_ramping = False

            current_wind = float(self.wind_pct.get())
            if self._wind_auto_ramping and not self._wind_manual_lock:
                target_wind = float(self._wind_target)
                tolerance = 0.5
                if abs(current_wind - target_wind) > tolerance:
                    step_per_sec = 100.0 / max(0.1, self._wind_ramp_up_sec)
                    step = step_per_sec * (self._ramp_interval_ms / 1000.0)
                    new_wind = min(target_wind, current_wind + step)
                    self._wind_auto_updating = True
                    try:
                        self.wind_pct.set(new_wind)
                        self.wind_val_label.configure(text=f"{new_wind:.0f}%")
                    finally:
                        self._wind_auto_updating = False
                    wind_changed = True
                else:
                    if self._wind_auto_ramping:
                        self._wind_auto_ramping = False

            if solar_changed or wind_changed:
                self.update_energy_mix()
        except Exception as exc:  # pragma: no cover - resilience
            print("ramp出错：", exc)
        finally:
            self.root.after(self._ramp_interval_ms, self._ramp_tick)


def main() -> None:
    root = tk.Tk()
    CircularEconomyDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
