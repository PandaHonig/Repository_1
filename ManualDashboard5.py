# -*- coding: utf-8 -*-
"""
Created on Sat Mar 15 11:19:52 2025
Baseline: 0 % reuse, 0 % recycle, 100 % thermal (worst-case scenario)
@author: tobis
"""

import tkinter as tk
from tkinter import ttk
import math
from collections import deque
import requests
import xml.etree.ElementTree as ET
import datetime
import time
from zoneinfo import ZoneInfo
import re

# Reference values for material consumption (UPDATED)
REF_BRASS = 0.500  # kg per unit 
REF_PLASTIC = 0.200  # kg per unit

# API 密钥 (需要替换为实际的密钥)
YOUR_API_KEY = "46b6d9c5-1c8a-4dc0-bb0b-eaf380ec0f6a"

# Energy mix CO2 factors (g CO2/kWh)
ENERGY_SOURCES = {
    "solar": {"co2": 50, "cost": 0.12},   # gCO2/kWh, €/kWh
    "wind": {"co2": 20, "cost": 0.10},
    "thermal": {"co2": 800, "cost": 0.18}
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
        style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"), foreground=COLORS["text"], background=COLORS["bg_dark"])
        style.configure("Subtitle.TLabel", font=("Segoe UI", 11, "bold"), foreground=COLORS["text"], background=COLORS["bg_medium"])
        style.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), foreground=COLORS["text"], background=COLORS["bg_medium"])
        style.configure("Value.TLabel", font=("Segoe UI", 9, "bold"), foreground=COLORS["text"], background=COLORS["bg_medium"])
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

        # Create blue accent button style
        style.configure("Accent.TButton", background=COLORS["bg_light"], foreground=COLORS["text"])
        style.map("Accent.TButton", background=[("active", COLORS["accent"])])
        
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

class FuturisticChart(tk.Canvas):
    """A futuristic styled chart"""
    
    def __init__(self, parent, width=400, height=200, bg=COLORS["chart_bg"]):
        """Initialize the chart"""
        super().__init__(parent, width=width, height=height, bg=bg, 
                        highlightthickness=0, bd=0)
        
        self.width = width
        self.height = height
        self.margin_left = 50
        self.margin_right = 20
        self.margin_top = 20
        self.margin_bottom = 40
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
        self.delete("bar", "label", "value", "unit")
        
        if not categories or not baseline_values or not current_values:
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

class TimeSeriesChart(FuturisticChart):
    """A futuristic time series chart"""
    
    def __init__(self, parent, width=900, height=250, max_points=20):
        """Initialize the chart"""
        super().__init__(parent, width, height)
        
        # Data storage
        self.max_points = max_points
        self.time_points = deque(maxlen=max_points)
        self.energy_points = deque(maxlen=max_points)
        self.co2_points = deque(maxlen=max_points)
        self.brass_points = deque(maxlen=max_points)
        self.plastic_points = deque(maxlen=max_points)
        self.cost_points = deque(maxlen=max_points)
        
        # Colors for data series
        self.colors = {
            "energy": COLORS["metric1"],
            "co2": COLORS["metric3"],
            "brass": COLORS["material1"],
            "plastic": COLORS["material2"],
            "cost": COLORS["metric2"]
        }
        
        # Initialize with empty data to draw the axes
        self.update_chart()
    
    def add_data_point(self, energy, co2, brass, plastic, cost):
        """Add a new data point to the time series"""
        current_time = datetime.datetime.now()
        
        # Add data to deques
        self.time_points.append(current_time)
        self.energy_points.append(energy)
        self.co2_points.append(co2)
        self.brass_points.append(brass)
        self.plastic_points.append(plastic)
        self.cost_points.append(cost)
        
        # Update the chart
        self.update_chart()
    
    def update_chart(self):
        """Update the chart with current data"""
        # Clear existing chart elements (not grid or axes)
        self.delete("line", "point", "label", "legend")
        
        # Draw the legend regardless of whether we have data
        self.draw_legend()
        
        if len(self.time_points) < 2:
            # Draw time axis labels even if no data
            if len(self.time_points) == 1:
                self.draw_time_labels()
            return  # Need at least 2 points to draw lines
        
        # Get the normalization factors for each data series
        # We'll scale each series to fit within the chart height
        max_energy = max(self.energy_points) if self.energy_points else 1
        max_co2 = max(self.co2_points) if self.co2_points else 1
        max_brass = max(self.brass_points) if self.brass_points else 1
        max_plastic = max(self.plastic_points) if self.plastic_points else 1
        max_cost = max(self.cost_points) if self.cost_points else 1
        
        # Time scale - divide chart width by number of time intervals
        time_range = (self.time_points[-1] - self.time_points[0]).total_seconds()
        if time_range == 0:
            time_range = 1  # Avoid division by zero
        
        # Draw each data series
        self.draw_series("energy", self.energy_points, max_energy, time_range)
        self.draw_series("co2", self.co2_points, max_co2, time_range)
        self.draw_series("brass", self.brass_points, max_brass, time_range)
        self.draw_series("plastic", self.plastic_points, max_plastic, time_range)
        self.draw_series("cost", self.cost_points, max_cost, time_range)
        
        # Draw time axis labels
        self.draw_time_labels()
    
    def draw_series(self, name, data_points, max_value, time_range):
        """Draw a single data series on the chart"""
        if max_value == 0:
            max_value = 1  # Avoid division by zero
        
        points = []
        for i, value in enumerate(data_points):
            # Calculate x position based on time
            time_fraction = (self.time_points[i] - self.time_points[0]).total_seconds() / time_range
            x = self.margin_left + (time_fraction * self.chart_width)
            
            # Calculate y position based on value
            value_fraction = value / max_value
            y = self.height - self.margin_bottom - (value_fraction * self.chart_height)
            
            points.append((x, y))
        
        # Draw glow effect for line (subtle shadow)
        if len(points) > 1:
            for i in range(len(points) - 1):
                self.create_line(
                    points[i][0], points[i][1] + 2,
                    points[i+1][0], points[i+1][1] + 2,
                    fill="#ffffff", width=4, tags="line", smooth=True
                )
        
        # Draw lines connecting points
        if len(points) > 1:
            for i in range(len(points) - 1):
                self.create_line(
                    points[i][0], points[i][1],
                    points[i+1][0], points[i+1][1],
                    fill=self.colors[name], width=2, tags="line", smooth=True
                )
        
        # Draw points
        for x, y in points:
            # Draw point glow
            self.create_oval(
                x-5, y-5, x+5, y+5,
                fill=self.colors[name], outline="", tags="point", stipple=""
            )
            # Draw center point
            self.create_oval(
                x-2, y-2, x+2, y+2,
                fill="#ffffff", outline="", tags="point"
            )
    
    def draw_legend(self):
        """Draw the chart legend"""
        # Position the legend at the top of the chart
        legend_x = self.margin_left + 20
        legend_y = self.margin_top
        
        # Draw colored squares and labels for each series with units
        items = [
            ("Energy (kWh)", "energy"),
            ("CO2 (kg)", "co2"),
            ("Brass (kg)", "brass"),
            ("Plastic (kg)", "plastic"),
            ("Cost (EUR)", "cost")
        ]
        
        # Calculate spacing based on available width
        available_width = self.width - self.margin_left - self.margin_right - 40
        item_spacing = available_width / len(items)
        
        for i, (label, key) in enumerate(items):
            # Create colored square
            self.create_rectangle(
                legend_x + (i * item_spacing), legend_y,
                legend_x + 10 + (i * item_spacing), legend_y + 10,
                fill=self.colors[key], outline="", tags="legend"
            )
            
            # Create label
            self.create_text(
                legend_x + 15 + (i * item_spacing), legend_y + 5,
                text=label, anchor="w", tags="legend", fill=COLORS["text"]
            )
    
    def draw_time_labels(self):
        """Draw time labels on the x-axis"""
        if not self.time_points:
            return
        
        # Draw start and end time
        start_time = self.time_points[0].strftime("%H:%M:%S")
        end_time = self.time_points[-1].strftime("%H:%M:%S")
        
        self.create_text(
            self.margin_left, self.height - self.margin_bottom + 15,
            text=start_time, anchor="n", tags="label", fill=COLORS["text_secondary"]
        )
        
        self.create_text(
            self.width - self.margin_right, self.height - self.margin_bottom + 15,
            text=end_time, anchor="n", tags="label", fill=COLORS["text_secondary"]
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
        self.material_recycling_var = tk.DoubleVar(value=0)
        
        self.solar_pct = tk.DoubleVar(value=33)  # 默认33%
        self.wind_pct = tk.DoubleVar(value=27)
        self.thermal_pct = tk.DoubleVar(value=40)
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
        
        # Time series data for live graph
        self.last_update_time = time.time()
        
        # Initial calculation
        self.calculate_and_update()
        
        # Create notebooks for calculation details and info (minimized)
        self.create_calculation_tabs()
        
        # Start timeseries update loop
        self.update_timeseries()
        
        # Fetch realtime price and schedule updates
        self.fetch_realtime_price()
    
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
        metrics_panel.pack(fill="both", expand=True, pady=(0, 10))
        
        # Create metrics chart
        self.metrics_chart = ComparisonChart(metrics_panel, width=550, height=300)
        self.metrics_chart.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create metrics legend
        metrics_legend_frame = ttk.Frame(metrics_panel, style="Panel.TFrame")
        metrics_legend_frame.pack(pady=5)
        
        # Create legend items
        baseline_frame = ttk.Frame(metrics_legend_frame, width=15, height=15, style="Panel.TFrame")
        baseline_frame.grid(row=0, column=0, padx=5)
        baseline_label = ttk.Label(metrics_legend_frame, text="Baseline", style="Panel.TLabel")
        baseline_label.grid(row=0, column=1, padx=(0, 15))
        
        baseline_canvas = tk.Canvas(baseline_frame, width=15, height=15, bg=COLORS["bg_medium"], 
                                   highlightthickness=0)
        baseline_canvas.pack(fill="both", expand=True)
        baseline_canvas.create_rectangle(0, 0, 15, 15, fill=COLORS["negative"], outline="")
        
        current_frame = ttk.Frame(metrics_legend_frame, width=15, height=15, style="Panel.TFrame")
        current_frame.grid(row=0, column=2, padx=5)
        current_label = ttk.Label(metrics_legend_frame, text="Current", style="Panel.TLabel")
        current_label.grid(row=0, column=3, padx=5)
        
        current_canvas = tk.Canvas(current_frame, width=15, height=15, bg=COLORS["bg_medium"], 
                                   highlightthickness=0)
        current_canvas.pack(fill="both", expand=True)
        current_canvas.create_rectangle(0, 0, 15, 15, fill=COLORS["metric1"], outline="")
        
        # Create materials panel
        materials_panel = ttk.LabelFrame(self.viz_column, text="Materials Breakdown", style="TLabelframe")
        materials_panel.pack(fill="both", expand=True)
        
        # Create materials chart with reduced height to make room for legend
        self.materials_chart = ComparisonChart(materials_panel, width=550, height=270)
        self.materials_chart.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        
        # Create materials legend with more space
        materials_legend_frame = ttk.Frame(materials_panel, style="Panel.TFrame")
        materials_legend_frame.pack(fill="x", pady=(0, 20))  # Added more bottom padding
        
        # Create legend items - reuse same style as metrics legend
        baseline_frame2 = ttk.Frame(materials_legend_frame, width=15, height=15, style="Panel.TFrame")
        baseline_frame2.grid(row=0, column=0, padx=5)
        baseline_label2 = ttk.Label(materials_legend_frame, text="Baseline", style="Panel.TLabel")
        baseline_label2.grid(row=0, column=1, padx=(0, 15))
        
        baseline_canvas2 = tk.Canvas(baseline_frame2, width=15, height=15, bg=COLORS["bg_medium"], 
                                   highlightthickness=0)
        baseline_canvas2.pack(fill="both", expand=True)
        baseline_canvas2.create_rectangle(0, 0, 15, 15, fill=COLORS["negative"], outline="")
        
        current_frame2 = ttk.Frame(materials_legend_frame, width=15, height=15, style="Panel.TFrame")
        current_frame2.grid(row=0, column=2, padx=5)
        current_label2 = ttk.Label(materials_legend_frame, text="Current", style="Panel.TLabel")
        current_label2.grid(row=0, column=3, padx=5)
        
        current_canvas2 = tk.Canvas(current_frame2, width=15, height=15, bg=COLORS["bg_medium"], 
                                   highlightthickness=0)
        current_canvas2.pack(fill="both", expand=True)
        current_canvas2.create_rectangle(0, 0, 15, 15, fill=COLORS["material1"], outline="")
        
    def create_livegraph_panel(self):
        """Create live graph panel"""
        livegraph_panel = ttk.LabelFrame(self.root, text="Live Metrics Visualization")
        livegraph_panel.pack(fill="x", padx=10, pady=(0, 10))
        
        # Create time series chart
        self.timeseries_chart = TimeSeriesChart(livegraph_panel, width=1160, height=250)
        self.timeseries_chart.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create control panel
        control_frame = ttk.Frame(livegraph_panel)
        control_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Add controls
        ttk.Button(control_frame, text="Record Data Point", 
                  command=self.record_data_point, style="Accent.TButton").pack(side="left", padx=(0, 10))
        
        self.auto_record_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="Auto Record (every 0.5 seconds)", 
                       variable=self.auto_record_var).pack(side="left")
        
        ttk.Button(control_frame, text="Clear Data", 
                  command=self.clear_timeseries_data).pack(side="right")
    
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
        
        # Create title for circular controls
        ttk.Label(self.input_panel, text="Component Reusability & Recycling", 
                 style="Section.TLabel").pack(pady=(10, 15))
        
        # Create a frame for the circular controls in a grid layout
        circular_frame = ttk.Frame(self.input_panel, style="Panel.TFrame")
        circular_frame.pack(fill="x", pady=5, padx=10)
        
        # Create a 2x2 grid for circular controls
        # First row
        circular_top_frame = ttk.Frame(circular_frame, style="Panel.TFrame")
        circular_top_frame.pack(fill="x", pady=5)
        
        # Cover control
        cover_control = CircularControl(
            circular_top_frame, 
            self.cover_var, 
            label="Cover", 
            radius=55, 
            callback=self.calculate_and_update
        )
        cover_control.pack(side="left", padx=10)
        
        # Impeller control
        impeller_control = CircularControl(
            circular_top_frame, 
            self.impeller_var, 
            label="Impeller", 
            radius=55, 
            callback=self.calculate_and_update
        )
        impeller_control.pack(side="right", padx=10)
        
        # Second row
        circular_bottom_frame = ttk.Frame(circular_frame, style="Panel.TFrame")
        circular_bottom_frame.pack(fill="x", pady=5)
        
        # Housing control
        housing_control = CircularControl(
            circular_bottom_frame, 
            self.housing_var, 
            label="Housing", 
            radius=55, 
            callback=self.calculate_and_update
        )
        housing_control.pack(side="left", padx=10)
        
        # Recycling control
        recycling_control = CircularControl(
            circular_bottom_frame, 
            self.material_recycling_var, 
            label="Recycling", 
            radius=55, 
            callback=self.calculate_and_update
        )
        recycling_control.pack(side="right", padx=10)
        
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

        # 火力
        thermal_row = ttk.Frame(mix_frame, style="Panel.TFrame")
        thermal_row.pack(fill="x", pady=2)
        ttk.Label(thermal_row, text="火Kohl (%)", style="Value.TLabel", width=10).pack(side="left")
        thermal_scale = ttk.Scale(thermal_row, from_=0, to=100, orient="horizontal",
            variable=self.thermal_pct, command=lambda v: self.on_slider_change('thermal', float(v)),
            style="Futuristic.Horizontal.TScale")
        thermal_scale.pack(side="left", fill="x", expand=True, padx=5)
        self.thermal_val_label = ttk.Label(thermal_row, text=f"{self.thermal_pct.get():.0f}%", style="Value.TLabel", width=4)
        self.thermal_val_label.pack(side="right")

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
        calc_text.insert("end", "Formula: co2 = energy * co2_factor * (1 - (recycle_pct / 100) * 0.5)\n\n")
        calc_text.insert("end", "Where:\n")
        calc_text.insert("end", "- energy = calculated energy consumption\n")
        calc_text.insert("end", "- co2_factor = ENERGY_SOURCES[energy_mix_type] / 1000 (converts g/kWh to kg/kWh)\n")
        calc_text.insert("end", "- recycle_pct = material recycling percentage\n\n")
        calc_text.insert("end", "Note: 100% recycling reduces CO2 emissions by 50%\n\n")
        
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
- Material Recycling: Percentage of materials that are recycled
    - Increases costs by up to 30% at 100% recycling
    - Reduces CO2 emissions by up to 50% at 100% recycling
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

The Live Graph tab shows how metrics change over time as you adjust the parameters, updating every 0.5 seconds.
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
    
    def update_material_value(self):
        self.material_recycling_var.set(round(self.material_recycling_var.get(), 1))
        self.calculate_and_update()
    
    def on_slider_change(self, changed, new_value):
        # changed: 'solar'/'wind'/'thermal'
        # new_value: float, 用户希望的新值
        values = {
            'solar': self.solar_pct.get(),
            'wind': self.wind_pct.get(),
            'thermal': self.thermal_pct.get()
        }
        values[changed] = new_value
        total = sum(values.values())
        if total <= 100:
            # 不超限，直接赋值
            self.solar_pct.set(values['solar'])
            self.wind_pct.set(values['wind'])
            self.thermal_pct.set(values['thermal'])
        else:
            # 超限，需要调整其他两个
            others = [k for k in values if k != changed]
            other_sum = values[others[0]] + values[others[1]]
            if other_sum == 0:
                # 其他两个都是0，当前最大只能到100
                values[changed] = 100
                values[others[0]] = 0
                values[others[1]] = 0
            else:
                # 按比例缩减
                excess = total - 100
                for k in others:
                    reduction = excess * (values[k] / other_sum) if other_sum > 0 else 0
                    values[k] = max(0, values[k] - reduction)
            # 重新赋值
            self.solar_pct.set(values['solar'])
            self.wind_pct.set(values['wind'])
            self.thermal_pct.set(values['thermal'])
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

    def update_price_display(self):
        """更新电价显示"""
        try:
            if self.use_realtime_price.get():
                val = self.realtime_price.get()
                src = self.price_source.get()
            else:
                factors = getattr(self, 'factors', {'solar':0,'wind':0,'thermal':1})
                val = sum(ENERGY_SOURCES[s]['cost'] * factors[s] for s in factors)
                src = "本地加权均值"
            self.price_display.set(f"当前电价: {val:.2f} €/kWh (来源: {src})")
        except Exception as e:
            # 兜底显示手动输入值
            val = self.realtime_price.get()
            self.price_display.set(f"当前电价: {val:.2f} €/kWh (来源: 默认值)")
            print("更新电价显示时出错:", e)
    
    def update_energy_mix(self, *args):
        """更新能源构成比例和显示"""
        s = self.solar_pct.get()
        w = self.wind_pct.get()
        t = self.thermal_pct.get()
        total = s + w + t
        if total == 0:
            self.factors = {'solar':0, 'wind':0, 'thermal':1.0}
            total_display = 0
        else:
            self.factors = {'solar': s/total, 'wind': w/total, 'thermal': t/total}
            total_display = total
        self.solar_val_label.config(text=f"{s:.0f}%")
        self.wind_val_label.config(text=f"{w:.0f}%")
        self.thermal_val_label.config(text=f"{t:.0f}%")
        if abs(total_display-100) > 0.1:
            self.energy_sum_label.config(text=f"合计: {total_display:.0f}% (请调整为100%)", foreground=COLORS["negative"])
        else:
            self.energy_sum_label.config(text=f"合计: {total_display:.0f}%", foreground=COLORS["positive"])
        
        # 更新动态显示的能源构成和电价
        self.energy_mix_display.set(f"太阳能: {s:.0f}%, 风能: {w:.0f}%, 火力: {t:.0f}%")
        self.update_price_display()
        
        self.calculate_and_update()
    
    def calculate_metrics(self, cover_reuse_pct, impeller_reuse_pct, housing_reuse_pct, recycle_pct, energy_mix_type, factors):
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
        
        # Add recycling cost factor - 100% recycling increases cost by 30%
        recycling_cost_factor = 1 + (recycle_pct / 100) * 0.3
        total_component_cost = (cover_cost + impeller_cost + housing_cost) * recycling_cost_factor
        
        # Linear interpolation between new and reused energy based on weighted average reuse
        energy = base_energy - (weighted_avg_reuse / 100) * (base_energy - reused_energy)
        
        # CO2 is affected by energy consumption and energy mix
        # Add recycling factor that reduces CO2 by up to 50%
        # 计算 CO₂ 强度（kgCO2/kWh）
        avg_co2 = sum(ENERGY_SOURCES[src]['co2'] * factors[src] for src in factors) / 1000

        # —— 这里开始，按模式取平均电价 —— #
        if self.use_realtime_price.get():
            # 实时模式：只用从 API 或手动输入框读取的值
            avg_cost = self.realtime_price.get()   # 单位：€/kWh
        else:
            # 本地模式：按滑杆比例加权 ENERGY_SOURCES 中各源的静态成本
            avg_cost = sum(ENERGY_SOURCES[src]['cost'] * factors[src]
                           for src in factors)
        # —— 这里结束 —— #

        co2 = energy * avg_co2 * (1 - recycle_pct/100 * 0.5)

        # 计算能源成本
        energy_cost = energy * avg_cost     
        
        # Calculate materials with new formula
        # Reuse can reduce by 80% max, recycling by 20% max
        
        # Base materials per unit
        base_brass = REF_BRASS
        base_plastic = REF_PLASTIC
        
        # Recycling factor (applies to material portion affected by recycling)
        recycle_factor = 1 - (recycle_pct / 100)
        
        # Brass calculation - housing only influences brass
        housing_reuse_factor = 1 - (housing_reuse_pct / 100)  # 0% reuse = 100% new material
        brass = base_brass * housing_reuse_factor * 0.8 + base_brass * 0.2 * recycle_factor
        
        # Plastic calculation - cover and impeller influence plastic
        # Plastic is influenced by cover (100%) and impeller (30%)
        cover_influence = MATERIAL_INFLUENCE["cover_to_plastic"] * (1 - (cover_reuse_pct / 100))
        impeller_influence = MATERIAL_INFLUENCE["impeller_to_plastic"] * (1 - (impeller_reuse_pct / 100))
        
        # Normalize influence factors (total should be 1.0)
        total_influence = MATERIAL_INFLUENCE["cover_to_plastic"] + MATERIAL_INFLUENCE["impeller_to_plastic"]
        normalized_cover_influence = MATERIAL_INFLUENCE["cover_to_plastic"] / total_influence
        normalized_impeller_influence = MATERIAL_INFLUENCE["impeller_to_plastic"] / total_influence
        
        # Calculate weighted plastic usage
        plastic_usage_factor = (normalized_cover_influence * cover_influence) + (normalized_impeller_influence * impeller_influence)
        
        # Apply 80/20 rule for reuse/recycling
        plastic = base_plastic * plastic_usage_factor * 0.8 + base_plastic * 0.2 * recycle_factor
        
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
            
            material_recycling = float(self.material_recycling_var.get())
            
            # 强制 baseline 为 0% reuse/recycle + 100% thermal
            baseline_factors = {'solar': 0.0, 'wind': 0.0, 'thermal': 1.0}
            baseline_metrics = self.calculate_metrics(0, 0, 0, 0, None, baseline_factors)
            
            # Calculate current metrics
            current_metrics = self.calculate_metrics(cover_reuse, impeller_reuse, housing_reuse, material_recycling, None, self.factors)
            
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
            
            # Record a data point for the live graph if auto-record is enabled
            if self.auto_record_var.get():
                self.record_data_point()
            
        except Exception as e:
            print(f"Error in calculation: {e}")
    
    def record_data_point(self):
        """Manually record a data point for the time series graph"""
        # Get current metrics
        cover_reuse = float(self.cover_var.get())
        impeller_reuse = float(self.impeller_var.get())
        housing_reuse = float(self.housing_var.get())
        material_recycling = float(self.material_recycling_var.get())
        
        # Calculate current metrics
        current_metrics = self.calculate_metrics(cover_reuse, impeller_reuse, housing_reuse, material_recycling, None, self.factors)
        
        # Add to time series chart
        self.timeseries_chart.add_data_point(
            current_metrics['energy'],
            current_metrics['co2'],
            current_metrics['brass'],
            current_metrics['plastic'],
            current_metrics['component_cost'] + current_metrics['energy_cost']
        )
    
    def clear_timeseries_data(self):
        """Clear all data points from the time series graph"""
        # Clear the data collections
        self.timeseries_chart.time_points.clear()
        self.timeseries_chart.energy_points.clear()
        self.timeseries_chart.co2_points.clear()
        self.timeseries_chart.brass_points.clear()
        self.timeseries_chart.plastic_points.clear()
        self.timeseries_chart.cost_points.clear()
        
        # Redraw the chart
        self.timeseries_chart.update_chart()
    
    def update_timeseries(self):
        """Check if it's time to update the time series graph"""
        current_time = time.time()
        
        # Auto-record a data point every 0.5 seconds
        if self.auto_record_var.get() and (current_time - self.last_update_time >= 0.5):
            self.record_data_point()
            self.last_update_time = current_time
        
        # Schedule the next check
        self.root.after(100, self.update_timeseries)  # Check more frequently for smoother updates




    def fetch_realtime_price(self):
        """按当地时区取德国日内 24 小时平均电价，并更新界面"""
        try:
            # ——— 1) 计算当地“昨天00:00→次日00:00”并转 UTC ———
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

            # ——— 2) 发请求 ———
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
            # —— 调试输出 —— 
            #print("Request URL:", resp.url)
            #print("Status Code:", resp.status_code)
            #print("Raw Response:\n", resp.text)
            resp.raise_for_status()

            # ——— 3) 解析 XML + 命名空间 + 容错 ———
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






# Create the main window and dashboard application
def main():
    root = tk.Tk()
    app = CircularEconomyDashboard(root)
    root.mainloop()

if __name__ == "__main__":
    main()