"""Scheduled machine-shifts for the whole period.

24/5 with three shifts, Saturday first-shift overtime in the Q4 peak at the
plants the config names, holidays off. Los Angeles starts in July 2025.
"""

from __future__ import annotations

import datetime as dt
import random

from .config import Config
from .model import Shift


def build_shifts(cfg: Config, rng: random.Random) -> list[Shift]:
    shifts: list[Shift] = []
    overtime_plants = set(cfg.overtime["plants"])
    overtime_months = set(cfg.overtime["months"])
    overtime_p = float(cfg.overtime["probability"])

    day = cfg.period_start
    while day <= cfg.period_end:
        weekday = day.weekday()  # Monday is 0
        is_holiday = day in cfg.holidays
        for plant in cfg.plants:
            if day < plant.data_start or is_holiday:
                continue
            if weekday < 5:
                defs = cfg.shift_defs
                overtime = False
            elif weekday == 5 and plant.code in overtime_plants and day.month in overtime_months:
                # One draw per plant-Saturday so both Atlanta machines work the same day.
                if rng.random() >= overtime_p:
                    continue
                defs = cfg.shift_defs[:1]
                overtime = True
            else:
                continue
            for machine in cfg.machines_at(plant.code):
                for sd in defs:
                    shifts.append(
                        Shift(
                            machine_code=machine.code,
                            plant_code=plant.code,
                            shift_date=day,
                            shift_no=sd.shift_no,
                            start=dt.datetime.combine(day, sd.start),
                            scheduled_minutes=sd.minutes,
                            is_overtime=overtime,
                        )
                    )
        day += dt.timedelta(days=1)
    return shifts


def month_key(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def quarter_key(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def is_winter(d: dt.date) -> bool:
    return d.month in (12, 1, 2)


def is_summer(d: dt.date) -> bool:
    return d.month in (6, 7, 8)
