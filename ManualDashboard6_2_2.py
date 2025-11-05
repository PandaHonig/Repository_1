# -*- coding: utf-8 -*-
"""
Created on Sat Mar 15 11:19:52 2025
Updated on Fri Aug 08 01:19:52 2025
Baseline: 0 % reuse, 0 % recycle, 100 % fossil (worst-case scenario)a
@author: tobias
@author: Junhao
"""

import tkinter as tk
from tkinter import ttk
import math
import requests
import xml.etree.ElementTree as ET
import datetime
from zoneinfo import ZoneInfo
import re
import threading, time
try:
    import serial  # 需要: pip install pyserial
except ImportError:
    serial = None

# Reference values for material consumption
REF_BRASS = 0.5   # kg per unit  0.8 → 0.5
REF_PLASTIC = 0.2  # kg per unit  0.02 → 0.2

# API 密钥 (需要替换为实际的密钥)
YOUR_API_KEY = "46b6d9c5-1c8a-4dc0-bb0b-eaf380ec0f6a"

# Energy mix CO2 factors (g CO2/kWh)
ENERGY_SOURCES = {
    "solar":  {"co2": 50,  "cost": 0.06},   # gCO2/kWh, €/kWh
    "wind":   {"co2": 20,  "cost": 0.05},
    "fossil": {"co2": 800, "cost": 0.14},
    "rest":   {"co2": 100, "cost": 0.11}   # estimated values
}

# Standard energy mix used for price correction
STANDARD_ENERGY_MIX = {
    "solar":  0.13,
    "wind":   0.31,
    "fossil": 0.47,
    "rest":   0.09
}

# Component costs
COMPONENT_COSTS = {
    "impeller": {"new": 0.20, "reman": 0.15, "reused": 0.10},
    "housing": {"new": 4.00, "reman": 3.00, "reused": 2.00}
}

# Energy consumption
ENERGY_CONSUMPTION = {
    "new": 20.0,    # kWh for completely new
    "reman": 16.5,  # kWh for remanufactured components
    "reused": 14.0  # kWh for completely reused
}


def compute_avg_co2_from_energy_mix(factors):
    """Return the average CO₂ intensity (kg/kWh) for a given energy mix."""

    return sum(ENERGY_SOURCES[src]["co2"] * factors[src] for src in factors) / 1000.0


def compute_avg_price_from_energy_mix(
    factors,
    use_realtime=False,
    realtime_price=0.0,
    price_source="本地加权均值",
):
    """Return the average electricity price (€/kWh) for a given energy mix."""

    custom = sum(ENERGY_SOURCES[src]["cost"] * factors[src] for src in factors)
    if use_realtime and price_source != "本地加权均值":
        standard = sum(
            ENERGY_SOURCES[src]["cost"] * STANDARD_ENERGY_MIX[src]
            for src in STANDARD_ENERGY_MIX
        )
        return realtime_price + (custom - standard)
    return custom

# Color scheme for futuristic design
COLORS = {
    "bg_dark": "#0d1117",        # Very dark blue background (main background)
    "bg_medium": "#1a1f2b",      # Medium blue for panels
    "bg_light": "#1e2532",       # Lighter blue for highlights
    "accent": "#00E0E0",         # Cyan accent (changed from red to match image)
    "text": "#F1F1F1",           # Light text
    "text_secondary": "#A0A0A0", # Secondary text
    "chart_bg": "#141926",       # Chart background
    "positive": "#4CAF50",       # Green for positive changes
    "negative": "#E94560",       # Red for negative changes
    "metric1": "#00BCD4",        # Cyan for energy
    "metric2": "#FFC107",        # Amber for cost
    "metric3": "#8BC34A",        # Light green for CO2
    "material1": "#FF5722",      # Deep orange for brass
    "material2": "#9C27B0"       # Purple for plastic
}

# --- Compact sizing (no autoscale) ---
COMPACT = True

GAUGE_RADIUS        = 45 if COMPACT else 55   # 左侧 6 个圆形控件半径（原 55）
CHART_H_METRICS     = 180 if COMPACT else 300 # 右上图表高度（原 300）
CHART_H_MATERIALS   = 150 if COMPACT else 270 # 右中图表高度（原 270）
CHART_H_SCENARIO    = 160 if COMPACT else 250 # 右下场景记录高度（原 250）
CHART_W_SCENARIO    = 750 if COMPACT else 900 # 场景记录画布宽度（原先实例化 1160）

PAD_X               = 10 if COMPACT else 12   # 通用水平内边距
PAD_Y_SMALL         = 3                        # 行内/图例间距
PAD_Y_PANEL         = 6                        # 面板之间的垂直间距

TITLE_FONT_SIZE     = 12 if COMPACT else 14
SUBTITLE_FONT_SIZE  = 10 if COMPACT else 11
SECTION_FONT_SIZE   = 9  if COMPACT else 10
VALUE_FONT_SIZE     = 9

# 压缩图表边距与图例密度
MARGIN_LEFT         = 46 if COMPACT else 50
MARGIN_RIGHT        = 16 if COMPACT else 20
MARGIN_TOP          = 12 if COMPACT else 20
MARGIN_BOTTOM       = 24 if COMPACT else 40
LEGEND_SPACING      = 14 if COMPACT else 22
LEGEND_BOX          = 8

SHOW_CALC_TABS = False

class CircularControl(tk.Canvas):
    """A futuristic circular control for setting percentage values"""
    
    def __init__(self, parent, variable, label="", radius=50, callback=None, **kwargs):
        """Initialize the circular control
        
        Parameters:
        -----------
        parent : tkinter widget
            The parent widget
        variable : tkinter.DoubleVar
            The variable to control
        label : str
            The label for the control
        radius : int
            The radius of the circular control
        callback : function
            Function to call when value changes
        """
        # Calculate dimensions
        self.radius = radius
        self.width = radius * 2 + 20
        self.height = radius * 2 + 40  # Extra space for label
        
        # Get parent background color if not specified
        if 'bg' not in kwargs:
            kwargs['bg'] = COLORS["bg_medium"]  # Use panel background color
            
        # Make sure there's no border/highlight
        kwargs['highlightthickness'] = 0
        kwargs['bd'] = 0
        
        # Initialize canvas
        super().__init__(parent, width=self.width, height=self.height, **kwargs)
        
        # Store parameters
        self.variable = variable
        self.label = label
        self.callback = callback
        
        # Set colors
        self.bg_color = kwargs['bg']  # Use the background color from kwargs
        self.track_color = "#2A3445"  # Darker track for better contrast
        self.progress_color = COLORS["accent"]
        self.text_color = COLORS["text"]
        
        # Draw initial state
        self._draw_control()
        
        # Add event handlers
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
    
    def _draw_control(self):
        """Draw the circular control"""
        self.delete("all")
        
        # Calculate center point
        cx = self.width // 2
        cy = (self.height - 20) // 2  # Adjust for label space
        
        # Draw track circle with better contrast
        thickness = self.radius * 0.15
        track_radius = self.radius - thickness // 2
        self.create_oval(
            cx - track_radius, cy - track_radius,
            cx + track_radius, cy + track_radius,
            outline=self.track_color, width=thickness, tags="track"
        )
        
        # Get current value
        value = self.variable.get()
        
        # Draw progress arc
        start_angle = 90
        extent_angle = -value * 3.6  # Convert percentage to degrees (negative for clockwise)
        
        if abs(extent_angle) > 0.1:  # Only draw if there's a visible arc
            self.create_arc(
                cx - track_radius, cy - track_radius,
                cx + track_radius, cy + track_radius,
                start=start_angle, extent=extent_angle, 
                outline=self.progress_color, width=thickness,
                style="arc", tags="progress"
            )
        
        # Draw value text
        self.create_text(
            cx, cy, text=f"{int(value)}%", 
            fill=self.text_color, font=("Segoe UI", 12, "bold"),
            tags="value"
        )
        
        # Draw label
        self.create_text(
            cx, self.height - 15, text=self.label,
            fill=self.text_color, font=("Segoe UI", 9),
            tags="label"
        )
    
    def _on_press(self, event):
        """Handle mouse press event"""
        self._update_value(event)
    
    def _on_drag(self, event):
        """Handle mouse drag event"""
        self._update_value(event)
    
    def _on_release(self, event):
        """Handle mouse release event"""
        self._update_value(event)
    
    def _update_value(self, event):
        """Update value based on mouse position"""
        # Calculate center point
        cx = self.width // 2
        cy = (self.height - 20) // 2
        
        # Calculate angle from center to mouse position
        dx = event.x - cx
        dy = event.y - cy
        
        # Calculate angle in degrees
        angle = math.degrees(math.atan2(dy, dx))
        
        # Convert angle to value (0-100)
        # Adjust angle to start from top (90 degrees)
        angle = (angle - 90) % 360
        
        # Convert to percentage (clockwise)
        value = 100 - (angle / 360 * 100)
        
        # Ensure value is between 0 and 100
        value = max(0, min(100, value))
        
        # Update variable
        old_value = self.variable.get()
        self.variable.set(round(value, 1))
        
        # Redraw control
        self._draw_control()
        
        # Trigger callback if provided and value changed
        if self.callback and abs(old_value - value) > 0.1:
            self.callback()

class FuturisticStyle:
    """Apply futuristic styling to Tkinter widgets"""
    
    @staticmethod
    def configure_styles():
        """Configure ttk styles for a futuristic look"""
        style = ttk.Style()
        #style.theme_use("clam")
        
        # Configure common elements
        style.configure("TFrame", background=COLORS["bg_dark"])
        style.configure("TLabel", background=COLORS["bg_dark"], foreground=COLORS["text"], font=("Segoe UI", 9))
        style.configure("TButton", background=COLORS["bg_light"], foreground=COLORS["text"], 
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("TButton", background=[("active", COLORS["accent"])])
        
        # Style for panels
        style.configure("Panel.TFrame", background=COLORS["bg_medium"])
        style.configure("Panel.TLabel", background=COLORS["bg_medium"], foreground=COLORS["text"])
        
        # Special styles
        style.configure("Title.TLabel",    font=("Segoe UI", TITLE_FONT_SIZE, "bold"),    foreground=COLORS["text"], background=COLORS["bg_dark"])
        style.configure("Subtitle.TLabel", font=("Segoe UI", SUBTITLE_FONT_SIZE, "bold"), foreground=COLORS["text"], background=COLORS["bg_medium"])
        style.configure("Section.TLabel",  font=("Segoe UI", SECTION_FONT_SIZE, "bold"),  foreground=COLORS["text"], background=COLORS["bg_medium"])
        style.configure("Value.TLabel",    font=("Segoe UI", VALUE_FONT_SIZE, "bold"),    foreground=COLORS["text"], background=COLORS["bg_medium"])
        style.configure("Accent.TLabel", foreground=COLORS["accent"], background=COLORS["bg_medium"])
        
        # Configure checkbox
        style.configure("TCheckbutton", background=COLORS["bg_medium"], foreground=COLORS["text"])
        
        # Configure notebook (tabs)
        style.configure("TNotebook", background=COLORS["bg_dark"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["bg_medium"], foreground=COLORS["text"],
                       padding=[10, 5], font=("Segoe UI", 9))
        style.map("TNotebook.Tab", background=[("selected", COLORS["bg_light"])], 
                 foreground=[("selected", COLORS["text"])])
        
        # Configure progressbar
        style.configure("TProgressbar", background=COLORS["accent"], troughcolor=COLORS["bg_light"])

        # Create blue accent button style matching cyber theme
        style.configure(
            "Accent.TButton",
            background=COLORS["bg_light"],
            foreground=COLORS["text"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent"])],
            foreground=[("active", COLORS["text"])],
        )
        
        # Style for LabelFrame
        style.configure("TLabelframe", background=COLORS["bg_medium"], foreground=COLORS["text"])
        style.configure("TLabelframe.Label", background=COLORS["bg_medium"], foreground=COLORS["text"], 
                      font=("Segoe UI", 10, "bold"))

        style.configure("Futuristic.Horizontal.TScale",
            background=COLORS["bg_medium"],
            troughcolor=COLORS["bg_light"],
            sliderthickness=18,
            sliderlength=28
        )
        #“Save / Clear”的深色按钮
        style.configure(
           "CyberDark.TButton",
           background=COLORS["bg_light"],     # 深灰蓝
           foreground=COLORS["text"],         # 亮字
           font=("Segoe UI", 9, "bold"),
           borderwidth=0,
           relief="flat",
        )
        style.map(
           "CyberDark.TButton",
           background=[
               ("active", COLORS["accent"]),   # 悬浮 / 按下：赛博青
               ("pressed", COLORS["accent"]),
           ],
           foreground=[
               ("active", COLORS["bg_dark"]),
               ("pressed", COLORS["bg_dark"]),
           ],
        )
        style.layout(
            "CyberDark.TButton",
            [("Button.padding",
              {"sticky": "nswe",
               "children": [("Button.label", {"sticky": "nswe"})]})]
        )
class FuturisticChart(tk.Canvas):
    """A futuristic styled chart"""
    
    def __init__(self, parent, width=400, height=200, bg=COLORS["chart_bg"]):
        """Initialize the chart"""
        super().__init__(parent, width=width, height=height, bg=bg, 
                        highlightthickness=0, bd=0)
        
        self.width = width
        self.height = height
        self.margin_left, self.margin_right = MARGIN_LEFT, MARGIN_RIGHT
        self.margin_top,  self.margin_bottom = MARGIN_TOP, MARGIN_BOTTOM
        self.chart_width = width - self.margin_left - self.margin_right
        self.chart_height = height - self.margin_top - self.margin_bottom
        
        # Set up chart area
        self.draw_grid()
    
    def draw_grid(self):
        """Draw a subtle grid on the chart"""
        # Draw horizontal grid lines
        for i in range(5):
            y = self.margin_top + (i * self.chart_height / 4)
            self.create_line(
                self.margin_left, y, 
                self.margin_left + self.chart_width, y,
                fill=COLORS["bg_light"], width=1, dash=(2, 4), tags="grid"
            )
        
        # Draw vertical grid lines
        for i in range(6):
            x = self.margin_left + (i * self.chart_width / 5)
            self.create_line(
                x, self.margin_top,
                x, self.margin_top + self.chart_height,
                fill=COLORS["bg_light"], width=1, dash=(2, 4), tags="grid"
            )
            
        # Draw axis lines
        self.create_line(
            self.margin_left, self.margin_top + self.chart_height,
            self.margin_left + self.chart_width, self.margin_top + self.chart_height,
            fill=COLORS["text_secondary"], width=2, tags="axis"
        )
        
        self.create_line(
            self.margin_left, self.margin_top,
            self.margin_left, self.margin_top + self.chart_height,
            fill=COLORS["text_secondary"], width=2, tags="axis"
        )

class ComparisonChart(FuturisticChart):
    """A futuristic bar chart for comparing baseline vs current values"""
    
    def __init__(self, parent, width=550, height=300):
        """Initialize the chart"""
        super().__init__(parent, width, height)
        self.baseline_color = COLORS["negative"]
        self.current_color = COLORS["metric1"]
    
    def update_chart(self, categories, baseline_values, current_values, colors=None, units=None):
        """Update the chart with new data"""
        # Clear existing chart elements (not grid or axes)
        self.delete("bar", "label", "value", "unit", "legend")

        if not categories or not baseline_values or not current_values:
            self.draw_legend()
            return
        
        # Set colors if provided
        if colors:
            if len(colors) >= 2:
                self.baseline_color = colors[0]
                self.current_color = colors[1]
        
        # Default units if not provided
        if not units:
            units = [""] * len(categories)
        
        # Find the maximum value for scaling
        max_value = max(max(baseline_values), max(current_values))
        if max_value == 0:
            max_value = 1  # Avoid division by zero
        
        # Calculate bar width and spacing
        num_groups = len(categories)
        group_width = self.chart_width / (num_groups + 1)  # +1 for spacing
        bar_width = group_width * 0.4
        
        # Draw each group of bars
        for i, category in enumerate(categories):
            # Calculate x positions
            x_center = self.margin_left + (i + 1) * group_width
            x_baseline = x_center - bar_width/2 - 5
            x_current = x_center + bar_width/2 + 5
            
            # Calculate bar heights
            baseline_height = (baseline_values[i] / max_value) * self.chart_height
            current_height = (current_values[i] / max_value) * self.chart_height
            
            # Ensure minimum visible height
            if baseline_height < 1 and baseline_values[i] > 0:
                baseline_height = 1
            if current_height < 1 and current_values[i] > 0:
                current_height = 1
            
            # Draw baseline bar
            y_baseline_top = self.height - self.margin_bottom - baseline_height
            self.create_rectangle(
                x_baseline - bar_width/2, y_baseline_top,
                x_baseline + bar_width/2, self.height - self.margin_bottom,
                fill=self.baseline_color, outline="", tags="bar",
                width=0, stipple=""
            )
            
            # Add a gradient effect to baseline bar
            for j in range(10):
                alpha = (10-j) / 20
                y_pos = y_baseline_top + (j * baseline_height / 10)
                self.create_line(
                    x_baseline - bar_width/2, y_pos,
                    x_baseline + bar_width/2, y_pos,
                    fill=self.baseline_color, width=1,
                    tags="bar", stipple=""
                )
            
            # Draw current bar
            y_current_top = self.height - self.margin_bottom - current_height
            self.create_rectangle(
                x_current - bar_width/2, y_current_top,
                x_current + bar_width/2, self.height - self.margin_bottom,
                fill=self.current_color, outline="", tags="bar",
                width=0, stipple=""
            )
            
            # Add a gradient effect to current bar
            for j in range(10):
                alpha = (10-j) / 20
                y_pos = y_current_top + (j * current_height / 10)
                self.create_line(
                    x_current - bar_width/2, y_pos,
                    x_current + bar_width/2, y_pos,
                    fill=self.current_color, width=1,
                    tags="bar", stipple=""
                )
            
            # Draw category label with unit
            unit_text = f" ({units[i]})" if units[i] else ""
            self.create_text(
                x_center, self.height - self.margin_bottom/2,
                text=f"{category}{unit_text}", anchor="center", tags="label",
                fill=COLORS["text"], font=("Segoe UI", 9)
            )
            
            # Draw baseline value
            self.create_text(
                x_baseline, y_baseline_top - 5,
                text=f"{baseline_values[i]:.1f}", anchor="s",
                font=("Segoe UI", 8), tags="value", fill=COLORS["text_secondary"]
            )
            
            # Draw current value
            self.create_text(
                x_current, y_current_top - 5,
                text=f"{current_values[i]:.1f}", anchor="s",
                font=("Segoe UI", 8), tags="value", fill=COLORS["text"]
            )
        
        # Draw scale on y-axis
        self.create_text(
            self.margin_left - 5, self.margin_top,
            text=f"{max_value:.1f}", anchor="e", tags="value",
            fill=COLORS["text_secondary"], font=("Segoe UI", 8)
        )
        self.create_text(
            self.margin_left - 5, self.height - self.margin_bottom,
            text="0", anchor="e", tags="value",
            fill=COLORS["text_secondary"], font=("Segoe UI", 8)
        )

        self.draw_legend()

    def draw_legend(self):
        """Draw the chart legend inside the top-right corner"""
        items = [
            ("Baseline", self.baseline_color),
            ("Current", self.current_color),
        ]

        spacing = LEGEND_SPACING
        box_size = LEGEND_BOX
        legend_x = self.width - self.margin_right - 80
        legend_y = self.margin_top

        for i, (label, color) in enumerate(items):
            y = legend_y + i * spacing
            self.create_rectangle(
                legend_x, y,
                legend_x + box_size, y + box_size,
                fill=color, outline="", tags="legend"
            )
            self.create_text(
                legend_x + box_size + 5, y + box_size / 2,
                text=label, anchor="w", fill=COLORS["text"],
                tags="legend", font=("Segoe UI", 8)
            )

class RecordBarChart(FuturisticChart):
    """A chart showing up to three saved records as grouped bars"""

    def __init__(self, parent, width=900, height=250, max_records=3):
        """Initialize the chart"""
        super().__init__(parent, width, height)

        if self.margin_bottom < 32:
            self.margin_bottom = 32
            self.chart_height = self.height - self.margin_top - self.margin_bottom
            self.delete("grid", "axis")
            self.draw_grid()

        self.max_records = max_records
        self.records = []
        self.colors = {
            "energy": COLORS["metric1"],
            "co2": COLORS["metric3"],
            "cost": COLORS["metric2"],
            "brass": COLORS["material1"],
            "plastic": COLORS["material2"],
        }

        self.update_chart()

    def add_record(self, record):
        """Add a new record to the chart"""
        if len(self.records) >= self.max_records:
            self.records.pop(0)
        self.records.append(record)
        self.update_chart()

    def clear_records(self):
        """Remove all saved records"""
        self.records.clear()
        self.update_chart()

    def update_chart(self):
        """Redraw the bar chart with current records"""
        self.delete("bar", "label", "legend", "value")

        if not self.records:
            self.draw_legend()
            return

        metrics = ["energy", "co2", "cost", "brass", "plastic"]
        max_value = max(max(record[m] for m in metrics) for record in self.records)
        if max_value == 0:
            max_value = 1

        num_records = len(self.records)
        group_width = self.chart_width / (num_records + 1)
        bar_width = group_width / (len(metrics) + 1)

        for i, record in enumerate(self.records):
            x_center = self.margin_left + (i + 1) * group_width
            for j, key in enumerate(metrics):
                value = record[key]
                bar_height = (value / max_value) * self.chart_height
                if bar_height < 1 and value > 0:
                    bar_height = 1
                x0 = x_center - (len(metrics) / 2) * bar_width + j * bar_width
                x1 = x0 + bar_width * 0.8
                y1 = self.height - self.margin_bottom
                y0 = y1 - bar_height
                self.create_rectangle(
                    x0, y0, x1, y1,
                    fill=self.colors[key], outline="", tags="bar"
                )
                self.create_text(
                    (x0 + x1) / 2, y0 - 5,
                    text=f"{value:.1f}", anchor="s",
                    font=("Segoe UI", 8), tags="value", fill=COLORS["text"]
                )

            self.create_text(
                x_center, self.height - self.margin_bottom + 10,
                text=record["label"], anchor="n", tags="label",
                fill=COLORS["text_secondary"]
            )

        # Draw scale on y-axis
        self.create_text(
            self.margin_left - 5, self.margin_top,
            text=f"{max_value:.1f}", anchor="e", tags="value",
            fill=COLORS["text_secondary"], font=("Segoe UI", 8)
        )
        self.create_text(
            self.margin_left - 5, self.height - self.margin_bottom,
            text="0", anchor="e", tags="value",
            fill=COLORS["text_secondary"], font=("Segoe UI", 8)
        )

        self.draw_legend()

    def draw_legend(self):
        """Draw the chart legend at the top-right corner"""
        items = [
            ("Energy (kWh)", "energy"),
            ("CO2 (kg)", "co2"),
            ("Cost (EUR)", "cost"),
            ("Brass (kg)", "brass"),
            ("Plastic (kg)", "plastic"),
        ]

        spacing = LEGEND_SPACING
        box_size = LEGEND_BOX
        legend_x = self.width - self.margin_right - 100
        legend_y = self.margin_top

        for i, (label, key) in enumerate(items):
            y = legend_y + i * spacing
            self.create_rectangle(
                legend_x, y,
                legend_x + box_size, y + box_size,
                fill=self.colors[key], outline="", tags="legend"
            )
            self.create_text(
                legend_x + box_size + 5, y + box_size // 2,
                text=label, anchor="w", tags="legend",
                fill=COLORS["text"]
            )

class CircularEconomyDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Circular Economy Dashboard")
        self.root.geometry("1200x800")
        self.root.configure(bg=COLORS["bg_dark"])
        
        # Apply futuristic styling
        FuturisticStyle.configure_styles()
        
        # Create main container
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create top frame for header
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(header_frame, text="Circular Economy Dashboard", style="Title.TLabel").pack(side="left")
        
        # Create content frame with two columns
        content_frame = ttk.Frame(main_container)
        content_frame.pack(fill="both", expand=True)
        
        # Left column for inputs
        self.input_column = ttk.Frame(content_frame)
        self.input_column.pack(side="left", fill="both", padx=(0, 10))
        
        # Right column for visualizations
        self.viz_column = ttk.Frame(content_frame)
        self.viz_column.pack(side="left", fill="both", expand=True)
        
        # Create panels
        self.create_input_panel()
        self.create_visualization_panels()
        self.create_livegraph_panel()
        
        # Create input variables
        self.meter_reuse_pct = tk.DoubleVar(value=0.0)
        self.reman_impeller_pct = tk.DoubleVar(value=0.0)
        self.reman_housing_pct = tk.DoubleVar(value=0.0)
        # Individual recycling rates for each component
        self.recycle_impeller_pct = tk.DoubleVar(value=0.0)
        self.recycle_housing_pct = tk.DoubleVar(value=0.0)
        
        self.solar_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["solar"] * 100))
        self.wind_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["wind"] * 100))
        self.fossil_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["fossil"] * 100))
        self.rest_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["rest"] * 100))
        self.use_realtime_price = tk.BooleanVar(value=False)
        self.realtime_price = tk.DoubleVar(value=0.15)
        self.price_source = tk.StringVar(value="本地加权均值")
        
        # Create result variables
        default_energy = ENERGY_CONSUMPTION["new"]
        default_cost = COMPONENT_COSTS["housing"]["new"] + COMPONENT_COSTS["impeller"]["new"]
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
        
        # Create input widget elements
        self.create_input_widgets()
        
        # Initialize energy mix factors and display
        self.update_energy_mix()
        
        # Initial calculation
        self.calculate_and_update()

        # Create notebooks for calculation details and info (minimized)
        if SHOW_CALC_TABS:
            self.create_calculation_tabs()

        # Fetch realtime price and schedule updates
        self.fetch_realtime_price()


        # ===== Solar/Wind 控制参数 =====
        self._solar_target = float(self.solar_pct.get())   # 当前 Solar 目标值
        self._ramp_interval_ms = 50                        # 步进周期
        self._ramp_up_sec = 10.0                           # Solar 0→100 用时（秒）
        self._ramp_dn_sec = 10.0                           # Solar 100→0 用时（秒）

        # Solar 状态量
        self._solar_state = 'A'            # 当前 Arduino 状态 A/L/B
        self._last_solar_state = 'A'       # 上一次状态（备用）
        self._manual_lock = False          # 手动调节后锁定，直到 L/B 再次出现
        self._auto_updating = False        # 内部自动推进时置 True，避免误判为“手动”
        self._auto_ramping = False         # 是否处于自动推进中

        # Wind 状态量
        self._wind_target = float(self.wind_pct.get())
        self._wind_state = 'STOPPED'
        self._wind_manual_lock = False
        self._wind_auto_ramping = False
        self._wind_auto_updating = False
        self._wind_ramp_up_sec = 10.0       # Wind 0→100 用时（秒）

        # 启动串口读取（根据你的端口修改，如 Win: 'COM3' / Mac: '/dev/tty.usbserial-xxxx' / Linux: '/dev/ttyUSB0'）
        self._start_serial(port_hint='COM5', baud=9600)

        # 开始定时匀速推进
        self.root.after(self._ramp_interval_ms, self._ramp_tick)
    
    def create_input_panel(self):
        """Create the input parameters panel"""
        input_panel = ttk.LabelFrame(self.input_column, text="Input Parameters")
        input_panel.pack(fill="both", expand=True)
        
        # We'll add the actual widgets later
        self.input_panel = input_panel
    
    def create_visualization_panels(self):
        """Create visualization panels for metrics and materials"""
        # Create metrics panel
        metrics_panel = ttk.LabelFrame(self.viz_column, text="Metrics Comparison", style="TLabelframe")
        metrics_panel.pack(fill="x", expand=False, pady=(0, PAD_Y_PANEL))

        # Create metrics chart
        self.metrics_chart = ComparisonChart(metrics_panel, width=550, height=CHART_H_METRICS)
        self.metrics_chart.pack(fill="x", expand=False, padx=PAD_X, pady=(0, PAD_Y_SMALL))

        # Create materials panel
        materials_panel = ttk.LabelFrame(self.viz_column, text="Materials Breakdown", style="TLabelframe")
        materials_panel.pack(fill="x", expand=False, pady=(0, PAD_Y_PANEL))

        # Create materials chart
        self.materials_chart = ComparisonChart(materials_panel, width=550, height=CHART_H_MATERIALS)
        self.materials_chart.pack(fill="x", expand=False, padx=PAD_X, pady=(0, PAD_Y_SMALL))
        
    def create_livegraph_panel(self):
        """Create panel for saving and comparing records"""
        # old version:  Live Metrics Visualization
        livegraph_panel = ttk.LabelFrame(self.viz_column, text="Scenario Comparison")
        livegraph_panel.pack(fill="both", expand=False, pady=(0, PAD_Y_PANEL))

        control_frame = ttk.Frame(livegraph_panel)
        control_frame.pack(side="top", fill="x", padx=PAD_X, pady=(0, PAD_Y_SMALL))

        ttk.Button(
            control_frame,
            text="Save Record",
            command=self.save_record,
            style="CyberDark.TButton",
        ).pack(side="left", padx=(0, PAD_X))

        ttk.Button(
            control_frame,
            text="Clear All Records",
            command=self.clear_records,
            style="CyberDark.TButton",
        ).pack(side="left")

        self.records_chart = RecordBarChart(
            livegraph_panel, width=CHART_W_SCENARIO, height=CHART_H_SCENARIO, max_records=3
        )
        self.records_chart.pack(
            side="top", fill="x", expand=False, padx=PAD_X, pady=(0, PAD_Y_PANEL)
        )
    
    def create_calculation_tabs(self):
        """Create tabs for calculation details and info"""
        notebook_frame = ttk.Frame(self.root)
        notebook_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        notebook = ttk.Notebook(notebook_frame)
        notebook.pack(fill="x")
        
        # Create calculations tab
        calc_tab = ttk.Frame(notebook, style="TFrame")
        self.create_calc_tab_content(calc_tab)
        
        # Create info tab
        info_tab = ttk.Frame(notebook, style="TFrame")
        self.create_info_tab_content(info_tab)
        
        # Add tabs to notebook
        notebook.add(calc_tab, text="Calculations")
        notebook.add(info_tab, text="Info")
    
    def create_input_widgets(self):
        """Create the actual input widgets with circular controls"""
        # Configure panel for dark background
        self.input_panel.configure(style="TLabelframe")
        
        # Meter reuse control
        ttk.Label(
            self.input_panel,
            text="Reuse",
            style="Section.TLabel"
        ).pack(pady=(10, 5))

        meter_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        meter_frame.pack(fill="x", pady=5, padx=10)

        CircularControl(
            meter_frame,
            self.meter_reuse_pct,
            label="Meter",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update,
        ).pack(side="left", padx=10)

        # Remanufacturing controls
        ttk.Label(self.input_panel, text="Remanufacturing",
                 style="Section.TLabel").pack(pady=(15, 5))

        reman_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        reman_frame.pack(fill="x", pady=5, padx=10)

        CircularControl(
            reman_frame,
            self.reman_impeller_pct,
            label="Impeller",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        ).pack(side="left", padx=10)

        CircularControl(
            reman_frame,
            self.reman_housing_pct,
            label="Housing",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        ).pack(side="left", padx=10)

        # Recycling controls
        ttk.Label(self.input_panel, text="Recycling",
                 style="Section.TLabel").pack(pady=(15, 5))

        recycle_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        recycle_frame.pack(fill="x", pady=5, padx=10)

        recycle_impeller_control = CircularControl(
            recycle_frame,
            self.recycle_impeller_pct,
            label="Impeller",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        recycle_impeller_control.pack(side="left", padx=10)

        recycle_housing_control = CircularControl(
            recycle_frame,
            self.recycle_housing_pct,
            label="Housing",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        recycle_housing_control.pack(side="left", padx=10)
        
        # Energy mix inputs
        ttk.Label(self.input_panel, text="能源构成", style="Section.TLabel").pack(
            pady=(20, 10), anchor="w", padx=10)

        mix_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        mix_frame.pack(fill="x", padx=10, pady=5)
        # ——— 电价面板 ———
        price_frame = ttk.Frame(mix_frame, style="Panel.TFrame")
        price_frame.pack(fill="x", pady=5)

        ttk.Checkbutton(
            price_frame,
            text="使用实时电价",
            variable=self.use_realtime_price,
            command=self.on_realtime_price_toggle
        ).pack(side="left")
        # Create entry for realtime price
        self.realtime_price_entry = ttk.Entry(
            price_frame,
            textvariable=self.realtime_price,
            width=6
        )
        self.realtime_price_entry.pack(side="left", padx=(10,2))
        ttk.Label(price_frame, text="€/kWh", style="Panel.TLabel").pack(side="left")

        # 默认禁用，只有勾选"使用实时电价"才可编辑
        self.realtime_price_entry.config(state="disabled")

        # 太阳能
        solar_row = ttk.Frame(mix_frame, style="Panel.TFrame")
        solar_row.pack(fill="x", pady=2)
        ttk.Label(solar_row, text="阳Solar (%)", style="Value.TLabel", width=10).pack(side="left")
        solar_scale = ttk.Scale(solar_row, from_=0, to=100, orient="horizontal",
            variable=self.solar_pct, command=lambda v: self.on_slider_change('solar', float(v)),
            style="Futuristic.Horizontal.TScale")
        solar_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.solar_val_label = ttk.Label(solar_row, text=f"{self.solar_pct.get():.0f}%", style="Value.TLabel", width=4)
        self.solar_val_label.pack(side="right")

        # 风能
        wind_row = ttk.Frame(mix_frame, style="Panel.TFrame")
        wind_row.pack(fill="x", pady=2)
        ttk.Label(wind_row, text="风Wind (%)", style="Value.TLabel", width=10).pack(side="left")
        wind_scale = ttk.Scale(wind_row, from_=0, to=100, orient="horizontal",
            variable=self.wind_pct, command=lambda v: self.on_slider_change('wind', float(v)),
            style="Futuristic.Horizontal.TScale")
        wind_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.wind_val_label = ttk.Label(wind_row, text=f"{self.wind_pct.get():.0f}%", style="Value.TLabel", width=4)
        self.wind_val_label.pack(side="right")

        # 化石能源
        fossil_row = ttk.Frame(mix_frame, style="Panel.TFrame")
        fossil_row.pack(fill="x", pady=2)
        ttk.Label(fossil_row, text="化Fossil (%)", style="Value.TLabel", width=10).pack(side="left")
        fossil_scale = ttk.Scale(fossil_row, from_=0, to=100, orient="horizontal",
            variable=self.fossil_pct, command=lambda v: self.on_slider_change('fossil', float(v)),
            style="Futuristic.Horizontal.TScale")
        fossil_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.fossil_val_label = ttk.Label(fossil_row, text=f"{self.fossil_pct.get():.0f}%", style="Value.TLabel", width=4)
        self.fossil_val_label.pack(side="right")

        # 其他
        rest_row = ttk.Frame(mix_frame, style="Panel.TFrame")
        rest_row.pack(fill="x", pady=2)
        ttk.Label(rest_row, text="其Rest (%)", style="Value.TLabel", width=10).pack(side="left")
        rest_scale = ttk.Scale(rest_row, from_=0, to=100, orient="horizontal",
            variable=self.rest_pct, command=lambda v: self.on_slider_change('rest', float(v)),
            style="Futuristic.Horizontal.TScale")
        rest_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.rest_val_label = ttk.Label(rest_row, text=f"{self.rest_pct.get():.0f}%", style="Value.TLabel", width=4)
        self.rest_val_label.pack(side="right")

        # 总和校验
        self.energy_sum_label = ttk.Label(mix_frame, text="合计: 100%", style="Value.TLabel")
        self.energy_sum_label.pack(pady=(5, 0))
        
        # Current energy mix display - 使用 StringVar 动态更新
        mix_display_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        mix_display_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 创建动态更新的 StringVar
        self.energy_mix_display = tk.StringVar()
        self.price_display = tk.StringVar()
        
        ttk.Label(mix_display_frame, text="当前能源构成:", style="Panel.TLabel").pack(side="left", padx=10)
        ttk.Label(mix_display_frame, textvariable=self.energy_mix_display, style="Value.TLabel").pack(side="left", padx=5)
        ttk.Label(mix_display_frame, textvariable=self.price_display, style="Value.TLabel").pack(side="left", padx=5)
        
        
    def create_calc_tab_content(self, parent):
        """Create the calculations tab content"""
        # Create a scrollable text area
        calc_frame = ttk.Frame(parent, style="TFrame")
        calc_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(calc_frame)
        scrollbar.pack(side="right", fill="y")
        
        # Create a text widget with scrollbar
        calc_text = tk.Text(calc_frame, wrap="word", yscrollcommand=scrollbar.set, height=8,
                           bg=COLORS["bg_medium"], fg=COLORS["text"], bd=0, highlightthickness=0)
        calc_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=calc_text.yview)
        
        # Insert calculation explanations
        calc_text.insert("end", "CALCULATION FORMULAS\n\n", "heading")
        
        # Energy calculation
        calc_text.insert("end", "1. ENERGY CONSUMPTION\n", "subheading")
        calc_text.insert("end", "Formula: energy = Q_whole*E_reused + (1-R_meter)*(w_h*(R_rem_h*E_reman + (1-R_rem_h)*E_new) + w_i*(R_rem_i*E_reman + (1-R_rem_i)*E_new))\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- Q_whole = meter_reuse_pct / 100\n")
        calc_text.insert("end", "- R_rem_h / R_rem_i = remanufacturing shares of housing / impeller\n")
        calc_text.insert("end", "- w_h / w_i = cost weights based on new component prices\n")
        calc_text.insert("end", "- E_new = 20.0 kWh, E_reman = 16.5 kWh, E_reused = 14.0 kWh\n\n")

        # CO2 calculation
        calc_text.insert("end", "2. CO2 EMISSIONS\n", "subheading")
        calc_text.insert("end", "Formula: co2 = energy * avg_co2_mix * (1 - 0.5 * secondary_share)\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- avg_co2_mix = weighted CO₂ factor from the selected energy mix (kg/kWh)\n")
        calc_text.insert("end", "- secondary_share = secondary_material / total_material\n")
        calc_text.insert("end", "- Secondary materials cut emissions by up to 50%\n\n")

        # Energy cost calculation
        calc_text.insert("end", "3. ENERGY COST\n", "subheading")
        calc_text.insert("end", "Formula: energy_cost = energy * avg_price_mix\n")
        calc_text.insert("end", "- avg_price_mix follows the active energy mix and realtime adjustments\n\n")

        # Component cost calculation
        calc_text.insert("end", "4. COMPONENT COST\n", "subheading")
        calc_text.insert("end", "Housing cost = Q_whole*C_reused + (1-R_meter)*(R_rem_h*C_reman + (1-R_rem_h)*C_new)\n")
        calc_text.insert("end", "Impeller cost = Q_whole*C_reused + (1-R_meter)*(R_rem_i*C_reman + (1-R_rem_i)*C_new)\n")
        calc_text.insert("end", "Component cost = housing cost + impeller cost\n\n")

        # Material calculation
        calc_text.insert("end", "5. MATERIALS\n", "subheading")
        calc_text.insert(
            "end",
            "Brass: REF_BRASS * Q_new_housing split into virgin / secondary by share_sec_housing\n",
        )
        calc_text.insert(
            "end",
            "Plastic: REF_PLASTIC * Q_new_impeller split into virgin / secondary by share_sec_impeller\n\n",
        )
        
        # Configure tags for styling
        calc_text.tag_configure("heading", font=("Segoe UI", 12, "bold"), foreground=COLORS["accent"])
        calc_text.tag_configure("subheading", font=("Segoe UI", 10, "bold"), foreground=COLORS["text"])
        
        # Make the text widget read-only
        calc_text.config(state="disabled")
    
    def create_info_tab_content(self, parent):
        """Create the info tab content"""
        info_frame = ttk.Frame(parent, style="TFrame")
        info_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        info_text = """
Circular Economy Dashboard

This dashboard simulates the impact of meter reuse, component remanufacturing, and recycling:

Input Parameters:
- Meter Reuse (QM): Percentage of complete meters that remain in service without disassembly.
- Component Remanufacturing (Impeller/Housing): Share of dismantled components that are remanufactured.
    - Impeller: €0.20 new, €0.15 reman, €0.10 reused
    - Housing: €4.00 new, €3.00 reman, €2.00 reused
- Component Recycling (Impeller/Housing): Percentage of remaining material demand sourced from secondary feedstock.
- Energy Mix: Simulated by activating solar and/or wind power
    - Neither active = USA mix (28.01¢/kWh)
    - Solar active = EU mix (36.01¢/kWh)
    - Wind active = German mix (40.11¢/kWh)
    - Both active = German eco mix (44.12¢/kWh)

Energy Consumption:
- Completely new components require 20 kWh
- Remanufactured components require 16.5 kWh on average
- Fully reused units require 14 kWh

Material Consumption:
- Remanufacturing lowers demand in proportion to each component's reman share
- Recycling supplies secondary feedstock for the remaining new-build fraction
- Secondary feedstock can reduce lifecycle CO₂ emissions by up to 50%

The dashboard compares the baseline scenario (0% reuse, 0% recycle, USA energy) with your current settings.

The Scenario Comparison panel lets you save up to three records and compare their energy, cost, CO₂, brass, and plastic values.
"""
        
        # Create a text widget for the info content
        info_text_widget = tk.Text(info_frame, wrap="word", height=15, 
                                  bg=COLORS["bg_medium"], fg=COLORS["text"], 
                                  bd=0, highlightthickness=0)
        info_text_widget.pack(fill="both", expand=True)
        info_text_widget.insert("1.0", info_text)
        info_text_widget.config(state="disabled")  # Make read-only
    
    def update_comp_value(self, var):
        var.set(round(var.get(), 1))
        self.calculate_and_update()
    
    def on_slider_change(self, changed, new_value):
        """滑块变化处理"""
        # 只有真实的用户拖动 Solar 才触发手动锁
        if changed == 'solar' and not self._auto_updating:
            print(f"用户手动调整Solar: {new_value:.1f}%")
            self._manual_lock = True
            self._solar_target = float(new_value)
            self._auto_ramping = False  # 停止自动推进

        if changed == 'wind' and not self._wind_auto_updating:
            print(f"用户手动调整Wind: {new_value:.1f}%")
            self._wind_manual_lock = True
            self._wind_target = float(new_value)
            self._wind_auto_ramping = False

        # changed: one of the energy sources
        sources = ['solar', 'wind', 'fossil', 'rest']
        values = {s: getattr(self, f"{s}_pct").get() for s in sources}
        values[changed] = new_value
        total = sum(values.values())
        if total > 100:
            others = [s for s in sources if s != changed]
            other_sum = sum(values[o] for o in others)
            if other_sum == 0:
                values[changed] = 100
                for o in others:
                    values[o] = 0
            else:
                excess = total - 100
                for o in others:
                    reduction = excess * (values[o] / other_sum)
                    values[o] = max(0, values[o] - reduction)
        for s in sources:
            getattr(self, f"{s}_pct").set(values[s])
        # 更新显示和计算
        self.update_energy_mix()
    
    def on_realtime_price_toggle(self):
        """当实时电价开关切换时调用"""
        if self.use_realtime_price.get():
            # 启用编辑，并立刻拉取最新价格
            self.realtime_price_entry.config(state="normal")
            self.fetch_realtime_price()
        else:
            # 禁用编辑，回退到本地加权
            self.realtime_price_entry.config(state="disabled")
            self.price_source.set("本地加权均值")
            self.update_price_display()
        self.calculate_and_update()

    def compute_avg_cost(self, factors):
        """Calculate average electricity cost based on mix and price mode"""
        return compute_avg_price_from_energy_mix(
            factors,
            use_realtime=self.use_realtime_price.get(),
            realtime_price=self.realtime_price.get(),
            price_source=self.price_source.get(),
        )

    def update_price_display(self):
        """更新电价显示"""
        try:
            factors = getattr(self, 'factors', {'solar':0,'wind':0,'fossil':1,'rest':0})
            val = self.compute_avg_cost(factors)
            src = self.price_source.get() if (self.use_realtime_price.get() and self.price_source.get() != "本地加权均值") else "本地加权均值"
            self.price_display.set(f"当前电价: {val:.2f} €/kWh (来源: {src})")
        except Exception as e:
            val = self.realtime_price.get()
            self.price_display.set(f"当前电价: {val:.2f} €/kWh (来源: 默认值)")
            print("更新电价显示时出错:", e)
    
    def update_energy_mix(self, *args):
        """更新能源构成比例和显示"""
        s = self.solar_pct.get()
        w = self.wind_pct.get()
        f = self.fossil_pct.get()
        r = self.rest_pct.get()
        total = s + w + f + r
        if total == 0:
            self.factors = {'solar':0, 'wind':0, 'fossil':1.0, 'rest':0}
            total_display = 0
        else:
            self.factors = {
                'solar': s/total,
                'wind': w/total,
                'fossil': f/total,
                'rest': r/total
            }
            total_display = total
        self.solar_val_label.config(text=f"{s:.0f}%")
        self.wind_val_label.config(text=f"{w:.0f}%")
        self.fossil_val_label.config(text=f"{f:.0f}%")
        self.rest_val_label.config(text=f"{r:.0f}%")
        if abs(total_display-100) > 0.1:
            self.energy_sum_label.config(text=f"合计: {total_display:.0f}% (请调整为100%)", foreground=COLORS["negative"])
        else:
            self.energy_sum_label.config(text=f"合计: {total_display:.0f}%", foreground=COLORS["positive"])

        # 更新动态显示的能源构成和电价
        self.energy_mix_display.set(
            f"太阳能: {s:.0f}%, 风能: {w:.0f}%, 化石: {f:.0f}%, 其他: {r:.0f}%"
        )
        self.update_price_display()

        self.calculate_and_update()
    
    def calculate_metrics(
        self,
        meter_reuse_pct,
        reman_housing_pct,
        reman_impeller_pct,
        recycle_housing_pct,
        recycle_impeller_pct,
        factors,
    ):
        """计算所有指标"""

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

        Q_new_housing  = (1.0 - R_meter) * (1.0 - R_rem_h)
        Q_new_impeller = (1.0 - R_meter) * (1.0 - R_rem_i)

        Q_sec_brass = (1 - R_meter) * (1 - R_rem_h) * R_rec_h
        Q_sec_plastic = (1 - R_meter) * (1 - R_rem_i) * R_rec_i

        share_sec_housing  = 0.0 if Q_new_housing  <= 1e-12 else R_rec_h
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
    
    def calculate_and_update(self):
        try:
            meter_reuse = float(self.meter_reuse_pct.get())
            reman_impeller = float(self.reman_impeller_pct.get())
            reman_housing = float(self.reman_housing_pct.get())

            recycle_impeller = float(self.recycle_impeller_pct.get())
            recycle_housing = float(self.recycle_housing_pct.get())

            # 强制 baseline 为 0% reuse/recycle + 100% fossil
            baseline_factors = {'solar': 0.0, 'wind': 0.0, 'fossil': 1.0, 'rest': 0.0}
            baseline_metrics = self.calculate_metrics(0, 0, 0, 0, 0, baseline_factors)

            # Calculate current metrics
            current_metrics = self.calculate_metrics(
                meter_reuse,
                reman_housing,
                reman_impeller,
                recycle_housing,
                recycle_impeller,
                self.factors,
            )
            
            # Update the result variables
            self.energy_baseline.set(baseline_metrics['energy'])
            self.energy_cost_baseline.set(baseline_metrics['energy_cost'])
            self.co2_baseline.set(baseline_metrics['co2'])
            self.brass_baseline.set(baseline_metrics['brass'])
            self.plastic_baseline.set(baseline_metrics['plastic'])
            self.cost_baseline.set(baseline_metrics['component_cost'])
            
            self.energy_current.set(current_metrics['energy'])
            self.energy_cost_current.set(current_metrics['energy_cost'])
            self.co2_current.set(current_metrics['co2'])
            self.brass_current.set(current_metrics['brass'])
            self.plastic_current.set(current_metrics['plastic'])
            self.cost_current.set(current_metrics['component_cost'])
            
            # Update charts
            # First chart: Metrics comparison with units
            self.metrics_chart.update_chart(
                ["Energy", "Cost", "CO2"],
                [
                    baseline_metrics['energy'],
                    baseline_metrics['total_cost'],
                    baseline_metrics['co2']
                ],
                [
                    current_metrics['energy'],
                    current_metrics['total_cost'],
                    current_metrics['co2']
                ],
                [COLORS["negative"], COLORS["metric1"]],
                ["kWh", "EUR", "kg"]  # Changed € to EUR for encoding compatibility
            )
            
            # Second chart: Materials comparison with units
            self.materials_chart.update_chart(
                ["Brass", "Plastic"],
                [
                    baseline_metrics['brass'],
                    baseline_metrics['plastic']
                ],
                [
                    current_metrics['brass'],
                    current_metrics['plastic']
                ],
                [COLORS["negative"], COLORS["material1"]],
                ["kg", "kg"]  # Units for materials
            )
            
            
        except Exception as e:
            print(f"Error in calculation: {e}")
    def save_record(self):
        """Save the current metrics as a record"""
        meter_reuse = int(self.meter_reuse_pct.get())
        reman_impeller = int(self.reman_impeller_pct.get())
        reman_housing = int(self.reman_housing_pct.get())
        recycle_impeller = int(self.recycle_impeller_pct.get())
        recycle_housing = int(self.recycle_housing_pct.get())

        current_metrics = self.calculate_metrics(
            meter_reuse,
            reman_housing,
            reman_impeller,
            recycle_housing,
            recycle_impeller,
            self.factors,
        )

        record = {
            "label": f"Record {len(self.records_chart.records) + 1}",
            "meter_reuse": meter_reuse,
            "reman_impeller": reman_impeller,
            "reman_housing": reman_housing,
            "recycle_impeller": recycle_impeller,
            "recycle_housing": recycle_housing,
            "energy": current_metrics['energy'],
            "co2": current_metrics['co2'],
            "brass": current_metrics['brass'],
            "plastic": current_metrics['plastic'],
            "cost": current_metrics['total_cost'],
        }
        self.records_chart.add_record(record)

    def clear_records(self):
        """Clear all saved records"""
        self.records_chart.clear_records()

    def fetch_realtime_price(self):
        """按当地时区取德国日内 24 小时平均电价，并更新界面"""
        try:
            # 1) 计算当地“昨天00:00→次日00:00”并转 UTC 
            berlin = ZoneInfo("Europe/Berlin")
            today_local = datetime.datetime.now(berlin).date()
            yesterday = today_local - datetime.timedelta(days=1)

            local_start = datetime.datetime.combine(
                yesterday, 
                datetime.time(0, 0), 
                tzinfo=berlin
            )
            # 注意：这里用 yesterday+1 天的 00:00
            local_end = datetime.datetime.combine(
                yesterday + datetime.timedelta(days=1),
                datetime.time(0, 0),
                tzinfo=berlin
            )

            utc = ZoneInfo("UTC")
            start_utc = local_start.astimezone(utc)
            end_utc   = local_end.astimezone(utc)

            # 2) 发请求
            params = {
                "securityToken": YOUR_API_KEY,
                "documentType":  "A44",
                "in_Domain":     "10Y1001A1001A82H",
                "out_Domain":    "10Y1001A1001A82H",
                "periodStart":   start_utc.strftime("%Y%m%d%H%M"),
                "periodEnd":     end_utc.strftime("%Y%m%d%H%M"),
            }
            resp = requests.get(
                "https://web-api.tp.entsoe.eu/api",
                params=params,
                headers={"Accept": "application/xml"},
                timeout=10
            )
            # 调试输出 
            #print("Request URL:", resp.url)
            #print("Status Code:", resp.status_code)
            #print("Raw Response:\n", resp.text)
            resp.raise_for_status()

            # 3) 解析 XML + 命名空间 + 容错 
            root = ET.fromstring(resp.content)
            m = re.match(r'\{(.+)\}', root.tag)
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

            # ——— 4) 计算平均并更新界面 ———
            avg_mwh = sum(prices) / len(prices)
            avg_kwh = avg_mwh / 1000.0
            self.realtime_price.set(avg_kwh)
            self.price_source.set("ENTSO‑E 日平均")

        except Exception as err:
            self.price_source.set("本地加权均值")
            print("获取实时电价失败:", err)

        finally:
            if self.use_realtime_price.get():
                self.update_price_display()
            self.root.after(3600_000, self.fetch_realtime_price)
            
    def _start_serial(self, port_hint='COM3', baud=9600):
        """启动串口线程，读取 Arduino 发来的 Solar/Wind 状态"""
        self._serial_stop = False
        if serial is None:
            print("pyserial 未安装，串口功能禁用")
            return

        def worker():
            ports_to_try = [port_hint, 'COM4', 'COM5', '/dev/ttyUSB0', '/dev/ttyACM0', '/dev/tty.usbserial-1410']
            ser = None
            for p in ports_to_try:
                if not p:
                    continue
                try:
                    ser = serial.Serial(p, baudrate=baud, timeout=1)
                    ser.reset_input_buffer()
                    print(f"串口连接Serial: {p}")
                    break
                except Exception:
                    continue
            if ser is None:
                print("未能连接到任何串口No serial port connected")
                return

            pat = re.compile(
                r"raw\s*=\s*(\d+(?:\.\d+)?)\s*,\s*base\s*=\s*(\d+(?:\.\d+)?)\s*,\s*state\s*=\s*([ALB])",
                re.I,
            )
            pat_wind = re.compile(r"\[(SPINNING|STOPPED)\]", re.I)
            while not self._serial_stop:
                try:
                    line = ser.readline().decode(errors='ignore').strip()
                    if not line:
                        continue

                    m = pat.search(line)
                    if m:
                        raw = int(float(m.group(1)))
                        base = int(float(m.group(2)))
                        st = m.group(3).upper()
                        self._process_arduino_state(st)
                        continue

                    m_wind = pat_wind.search(line)
                    if m_wind:
                        wind_state = m_wind.group(1).upper()
                        self._process_wind_state(wind_state)
                        continue
                except Exception as e:
                    print("串口读取异常：", e)
                    time.sleep(0.2)
            try:
                ser.close()
            except:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _process_arduino_state(self, new_state):
        """处理 Arduino 状态变化"""
        old_state = self._solar_state
        self._solar_state = new_state
        if old_state != new_state:
            print(f"Arduino状态变化: {old_state} -> {new_state}")
            if new_state == 'L':
                print("检测到直射，开始向上推进")
                self._manual_lock = False
                self._solar_target = 100.0
                self._auto_ramping = True
            elif new_state == 'B':
                print("检测到遮挡，开始向下推进")
                self._manual_lock = False
                self._solar_target = 0.0
                self._auto_ramping = True
            else:  # Ambient
                if old_state in ['L', 'B']:
                    print("回到环境光，停止自动推进")
                    self._auto_ramping = False
                    self._solar_target = float(self.solar_pct.get())

    def _process_wind_state(self, new_state: str):
        """处理风力状态变化"""
        normalized = (new_state or '').upper()
        old_state = self._wind_state
        self._wind_state = normalized
        if old_state != normalized:
            print(f"Wind状态变化: {old_state} -> {normalized}")

        if normalized == 'SPINNING':
            print("检测到风机旋转，启动向上推进")
            self._wind_manual_lock = False
            self._wind_target = 100.0
            self._wind_auto_ramping = True
        elif normalized == 'STOPPED':
            #if not self._wind_manual_lock:
            #    print("检测到风机停止，维持当前风能比例")'
            self._wind_auto_ramping = False
            self._wind_target = float(self.wind_pct.get())

    def _ramp_tick(self):
        """定时推进 Solar/Wind 进度"""
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
                        self.solar_val_label.config(text=f"{new_val:.0f}%")
                    finally:
                        self._auto_updating = False
                    solar_changed = True
                else:
                    if self._auto_ramping:
                        print(f"到达目标值 {target:.1f}%，停止推进")
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
                        self.wind_val_label.config(text=f"{new_wind:.0f}%")
                    finally:
                        self._wind_auto_updating = False
                    wind_changed = True
                else:
                    if self._wind_auto_ramping:
                        print(f"风能到达目标值 {target_wind:.1f}%，停止推进")
                        self._wind_auto_ramping = False

            if solar_changed or wind_changed:
                self.update_energy_mix()
        except Exception as e:
            print("ramp出错：", e)
        finally:
            self.root.after(self._ramp_interval_ms, self._ramp_tick)






# Create the main window and dashboard application
def main():
    root = tk.Tk()
    app = CircularEconomyDashboard(root)
    root.mainloop()

if __name__ == "__main__":
    main()
