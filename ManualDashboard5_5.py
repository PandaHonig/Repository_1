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

# Reference values for material consumption (UPDATED)
REF_BRASS = 0.500  # kg per unit 
REF_PLASTIC = 0.200  # kg per unit

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
    "cover": {"new": 0.70, "reused": 0.30},
    "impeller": {"new": 0.11, "reused": 0.20},
    "housing": {"new": 4.00, "reused": 2.00}
}

# Energy consumption
ENERGY_CONSUMPTION = {
    "new": 20.0,    # kWh for completely new
    "reused": 14.0  # kWh for completely reused
}

# Material influence factors
MATERIAL_INFLUENCE = {
    "housing_to_brass": 1.0,     # Housing 100% influences brass
    "cover_to_plastic": 1.0,     # Cover 100% influences plastic
    "impeller_to_plastic": 0.3   # Impeller 30% influences plastic compared to cover
}

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
        self.cover_var = tk.DoubleVar(value=0)
        self.impeller_var = tk.DoubleVar(value=0)
        self.housing_var = tk.DoubleVar(value=0)
        # Individual recycling rates for each component
        self.recycle_cover_var = tk.DoubleVar(value=0)
        self.recycle_impeller_var = tk.DoubleVar(value=0)
        self.recycle_housing_var = tk.DoubleVar(value=0)
        # Deprecated global recycling variable (kept for compatibility)
        self.material_recycling_var = tk.DoubleVar(value=0)
        
        self.solar_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["solar"] * 100))
        self.wind_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["wind"] * 100))
        self.fossil_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["fossil"] * 100))
        self.rest_pct = tk.DoubleVar(value=int(STANDARD_ENERGY_MIX["rest"] * 100))
        self.use_realtime_price = tk.BooleanVar(value=False)
        self.realtime_price = tk.DoubleVar(value=0.15)
        self.price_source = tk.StringVar(value="本地加权均值")
        
        # Create result variables
        self.energy_baseline = tk.DoubleVar(value=20.0)
        self.co2_baseline = tk.DoubleVar(value=9.0)
        self.brass_baseline = tk.DoubleVar(value=0.5)
        self.plastic_baseline = tk.DoubleVar(value=0.2)
        self.cost_baseline = tk.DoubleVar(value=4.81)
        self.energy_cost_baseline = tk.DoubleVar(value=5.60)
        
        self.energy_current = tk.DoubleVar(value=20.0)
        self.co2_current = tk.DoubleVar(value=9.0)
        self.brass_current = tk.DoubleVar(value=0.5)
        self.plastic_current = tk.DoubleVar(value=0.2)
        self.cost_current = tk.DoubleVar(value=4.81)
        self.energy_cost_current = tk.DoubleVar(value=5.60)
        
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
        
        # Reuse controls
        ttk.Label(self.input_panel, text="Component Reusability",
                 style="Section.TLabel").pack(pady=(10, 5))

        reuse_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        reuse_frame.pack(fill="x", pady=5, padx=10)

        cover_control = CircularControl(
            reuse_frame,
            self.cover_var,
            label="Cover",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        cover_control.pack(side="left", padx=10)

        impeller_control = CircularControl(
            reuse_frame,
            self.impeller_var,
            label="Impeller",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        impeller_control.pack(side="left", padx=10)

        housing_control = CircularControl(
            reuse_frame,
            self.housing_var,
            label="Housing",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        housing_control.pack(side="left", padx=10)

        # Recycling controls
        ttk.Label(self.input_panel, text="Component Recycling",
                 style="Section.TLabel").pack(pady=(15, 5))

        recycle_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        recycle_frame.pack(fill="x", pady=5, padx=10)

        recycle_cover_control = CircularControl(
            recycle_frame,
            self.recycle_cover_var,
            label="Cover",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        recycle_cover_control.pack(side="left", padx=10)

        recycle_impeller_control = CircularControl(
            recycle_frame,
            self.recycle_impeller_var,
            label="Impeller",
            radius=GAUGE_RADIUS,
            callback=self.calculate_and_update
        )
        recycle_impeller_control.pack(side="left", padx=10)

        recycle_housing_control = CircularControl(
            recycle_frame,
            self.recycle_housing_var,
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
        calc_text.insert("end", "Base formula: energy = base_energy - (weighted_avg_reuse / 100) * (base_energy - reused_energy)\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- base_energy = 20.0 kWh (for completely new component)\n")
        calc_text.insert("end", "- reused_energy = 14.0 kWh (for completely reused component)\n")
        calc_text.insert("end", "- weighted_avg_reuse = weighted average of component reuse percentages\n\n")
        
        calc_text.insert("end", "Weighted average calculation:\n")
        calc_text.insert("end", "1. Total new cost = sum of all component new costs\n")
        calc_text.insert("end", "2. For each component:\n")
        calc_text.insert("end", "   weighted_component_reuse = (component_reuse_pct / 100) * (component_new_cost / total_new_cost)\n")
        calc_text.insert("end", "3. weighted_avg_reuse = sum of all weighted_component_reuse * 100\n\n")
        
        # CO2 calculation
        calc_text.insert("end", "2. CO2 EMISSIONS\n", "subheading")
        calc_text.insert("end", "Formula: co2 = energy * co2_factor * (1 - 0.5 * effective_recycle_pct / 100)\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- energy = calculated energy consumption\n")
        calc_text.insert("end", "- co2_factor = ENERGY_SOURCES[energy_mix_type] / 1000 (converts g/kWh to kg/kWh)\n")
        calc_text.insert("end", "- effective_recycle_pct = material-weighted recycling percentage\n\n")
        calc_text.insert("end", "Note: 100% effective recycling reduces CO2 emissions by 50%\n\n")
        
        calc_text.insert("end", "Energy mix CO2 factors (g CO2/kWh):\n")
        calc_text.insert("end", "- USA: 450\n")
        calc_text.insert("end", "- EU: 300\n")
        calc_text.insert("end", "- DT: 250\n")
        calc_text.insert("end", "- DTeco: 50\n\n")

        # Energy cost calculation
        calc_text.insert("end", "3. ENERGY COST\n", "subheading")
        calc_text.insert("end", "Formula: energy_cost = energy * (ENERGY_COSTS[energy_mix_type] / 100)\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- energy = calculated energy consumption\n")
        calc_text.insert("end", "- ENERGY_COSTS[energy_mix_type] / 100 converts cents to euros\n\n")

        # Component cost calculation
        calc_text.insert("end", "4. COMPONENT COST\n", "subheading")
        calc_text.insert("end", "For each component: cost = new_cost*(1 - reuse_pct/100) + reused_cost*(reuse_pct/100)\n")
        calc_text.insert("end", "Then cost *= (1 + 0.3 * component_recycle_pct/100)\n")
        calc_text.insert("end", "Total component cost = sum of all component costs\n\n")

        # Material calculation
        calc_text.insert("end", "5. MATERIALS\n", "subheading")
        calc_text.insert("end", "Brass: reuse by housing (80%) + recycling of remaining 20%\n")
        calc_text.insert("end", "Plastic: reuse and recycling weighted by cover and impeller influence (80%/20%)\n\n")
        
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

This dashboard simulates the impact of reusing and recycling components:

Input Parameters:
- Component Reusability: Percentage of each component that is reused
    - Cover: €0.70 new, €0.30 reused (influences plastic)
    - Impeller: €0.11 new, €0.20 reused (influences plastic at 30% level)
    - Housing: €4.00 new, €2.00 reused (influences brass)
- Component Recycling (Cover/Impeller/Housing): Percentage of each component's materials that are recycled
    - Each component's cost increases by up to 30% when fully recycled
    - Reuse affects up to 80% of material needs; recycling reduces the remaining 20%
    - Effective recycling, weighted by brass and plastic masses, can cut CO₂ up to 50%
- Energy Mix: Simulated by activating solar and/or wind power
    - Neither active = USA mix (28.01¢/kWh)
    - Solar active = EU mix (36.01¢/kWh)
    - Wind active = German mix (40.11¢/kWh)
    - Both active = German eco mix (44.12¢/kWh)

Energy Consumption:
- A completely new part requires 20 kWh
- A completely reused part requires 14 kWh

Material Consumption:
- Reuse can reduce material usage by max 80%
- Recycling can reduce material usage by max 20%
- Both combined can reduce material usage to zero

The dashboard compares the baseline scenario (0% reuse, 0% recycle, USA energy) with your current settings.

The Live Metrics Visualization panel lets you save up to three records and compare their energy, cost, CO₂, brass, and plastic values.
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
        # Weighted cost of the user's selected energy mix
        # (当前能源组合的加权成本)
        custom = sum(ENERGY_SOURCES[s]['cost'] * factors[s] for s in factors)
        # If using realtime price, adjust based on the standard mix
        if self.use_realtime_price.get() and self.price_source.get() != "本地加权均值":
            standard = sum(ENERGY_SOURCES[s]['cost'] * STANDARD_ENERGY_MIX[s] for s in STANDARD_ENERGY_MIX)
            return self.realtime_price.get() + (custom - standard)
        return custom

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
    
    def calculate_metrics(self, cover_reuse_pct, impeller_reuse_pct, housing_reuse_pct,
                          recycle_cover_pct, recycle_impeller_pct, recycle_housing_pct,
                          energy_mix_type, factors):
        """计算所有指标"""
        # Energy calculation
        base_energy = ENERGY_CONSUMPTION["new"]  # kWh for a new part
        reused_energy = ENERGY_CONSUMPTION["reused"]  # kWh for a reused part
        
        # Calculate average reuse percentage weighted by component cost
        total_new_cost = (
            COMPONENT_COSTS["cover"]["new"] + 
            COMPONENT_COSTS["impeller"]["new"] + 
            COMPONENT_COSTS["housing"]["new"]
        )
        
        weighted_cover_reuse = (cover_reuse_pct / 100) * (COMPONENT_COSTS["cover"]["new"] / total_new_cost)
        weighted_impeller_reuse = (impeller_reuse_pct / 100) * (COMPONENT_COSTS["impeller"]["new"] / total_new_cost)
        weighted_housing_reuse = (housing_reuse_pct / 100) * (COMPONENT_COSTS["housing"]["new"] / total_new_cost)
        
        weighted_avg_reuse = (weighted_cover_reuse + weighted_impeller_reuse + weighted_housing_reuse) * 100
        
        # Calculate component costs
        cover_cost = (COMPONENT_COSTS["cover"]["new"] * (1 - cover_reuse_pct/100)) + (COMPONENT_COSTS["cover"]["reused"] * (cover_reuse_pct/100))
        impeller_cost = (COMPONENT_COSTS["impeller"]["new"] * (1 - impeller_reuse_pct/100)) + (COMPONENT_COSTS["impeller"]["reused"] * (impeller_reuse_pct/100))
        housing_cost = (COMPONENT_COSTS["housing"]["new"] * (1 - housing_reuse_pct/100)) + (COMPONENT_COSTS["housing"]["reused"] * (housing_reuse_pct/100))

        cover_cost *= (1 + 0.3 * recycle_cover_pct/100.0)
        impeller_cost *= (1 + 0.3 * recycle_impeller_pct/100.0)
        housing_cost *= (1 + 0.3 * recycle_housing_pct/100.0)

        total_component_cost = cover_cost + impeller_cost + housing_cost
        
        # Linear interpolation between new and reused energy based on weighted average reuse
        energy = base_energy - (weighted_avg_reuse / 100) * (base_energy - reused_energy)
        
        # CO2 is affected by energy consumption and energy mix
        # Add recycling factor that reduces CO2 by up to 50%
        # 计算 CO₂ 强度（kgCO2/kWh）
        avg_co2 = sum(ENERGY_SOURCES[src]['co2'] * factors[src] for src in factors) / 1000.0

        avg_cost = self.compute_avg_cost(factors)

        # Calculate materials with reuse and recycling effects
        brass = REF_BRASS * (1 - housing_reuse_pct/100.0) * 0.8 \
                + REF_BRASS * 0.2 * (1 - recycle_housing_pct/100.0)

        total_w = MATERIAL_INFLUENCE["cover_to_plastic"] + MATERIAL_INFLUENCE["impeller_to_plastic"]
        wC = MATERIAL_INFLUENCE["cover_to_plastic"] / total_w
        wI = MATERIAL_INFLUENCE["impeller_to_plastic"] / total_w

        reuse_factor_plastic = (wC * (1 - cover_reuse_pct/100.0)) + (wI * (1 - impeller_reuse_pct/100.0))
        recycle_plastic_pct = (wC * recycle_cover_pct) + (wI * recycle_impeller_pct)

        plastic = REF_PLASTIC * reuse_factor_plastic * 0.8 \
                + REF_PLASTIC * 0.2 * (1 - recycle_plastic_pct/100.0)

        effective_recycle_pct = (REF_BRASS * recycle_housing_pct + REF_PLASTIC * recycle_plastic_pct) / (REF_BRASS + REF_PLASTIC)
        co2 = energy * avg_co2 * (1 - 0.5 * effective_recycle_pct/100.0)

        # 计算能源成本
        energy_cost = energy * avg_cost

        return {
            "energy": energy,
            "energy_cost": energy_cost,
            "co2": co2,
            "brass": brass,
            "plastic": plastic,
            "component_cost": total_component_cost
        }
    
    def calculate_and_update(self):
        try:
            # Get the component reuse percentages
            cover_reuse = float(self.cover_var.get())
            impeller_reuse = float(self.impeller_var.get())
            housing_reuse = float(self.housing_var.get())
            
            rc = float(self.recycle_cover_var.get())
            ri = float(self.recycle_impeller_var.get())
            rh = float(self.recycle_housing_var.get())

            # 强制 baseline 为 0% reuse/recycle + 100% fossil
            baseline_factors = {'solar': 0.0, 'wind': 0.0, 'fossil': 1.0, 'rest': 0.0}
            baseline_metrics = self.calculate_metrics(0, 0, 0, 0, 0, 0, None, baseline_factors)

            # Calculate current metrics
            current_metrics = self.calculate_metrics(cover_reuse, impeller_reuse, housing_reuse, rc, ri, rh, None, self.factors)
            
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
                    baseline_metrics['component_cost'] + baseline_metrics['energy_cost'],
                    baseline_metrics['co2']
                ],
                [
                    current_metrics['energy'],
                    current_metrics['component_cost'] + current_metrics['energy_cost'],
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
        cover_reuse = int(self.cover_var.get())
        impeller_reuse = int(self.impeller_var.get())
        housing_reuse = int(self.housing_var.get())
        recycle_cover = int(self.recycle_cover_var.get())
        recycle_impeller = int(self.recycle_impeller_var.get())
        recycle_housing = int(self.recycle_housing_var.get())

        current_metrics = self.calculate_metrics(
            cover_reuse,
            impeller_reuse,
            housing_reuse,
            recycle_cover,
            recycle_impeller,
            recycle_housing,
            None,
            self.factors,
        )

        record = {
            "label": f"Record {len(self.records_chart.records) + 1}",
            "reuse_cover": cover_reuse,
            "reuse_impeller": impeller_reuse,
            "reuse_housing": housing_reuse,
            "recycle_cover": recycle_cover,
            "recycle_impeller": recycle_impeller,
            "recycle_housing": recycle_housing,
            "energy": current_metrics['energy'],
            "co2": current_metrics['co2'],
            "brass": current_metrics['brass'],
            "plastic": current_metrics['plastic'],
            "cost": current_metrics['component_cost'] + current_metrics['energy_cost'],
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
